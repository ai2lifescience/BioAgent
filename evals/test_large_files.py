"""Storage boundary regressions using synthetic data, no external workflows."""
import asyncio
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from auth import OwnershipStore, Principal, principal_scope, AccessDenied
from isolation import WorkspaceAccess
from isolation.files import inventory, stage_files, import_staged
from isolation.storage import reservations, publish, check_quota, reserve, release, usage
from interfaces.uploads import Uploads, multipart


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        env = patch.dict(os.environ, {'AGENT_AUTH_MODE': 'multiuser', 'AGENT_MIN_FREE_DISK_BYTES': '1'})
        env.start(); self.addCleanup(env.stop)
        scope = principal_scope(Principal('alice')); scope.__enter__(); self.addCleanup(scope.__exit__, None, None, None)
        ownership = OwnershipStore(self.root / 'metadata'); ownership.claim('session')
        self.access = WorkspaceAccess(ownership, self.root / 'sessions')
        self.workspace = self.access.workspace('session'); self.workspace.mkdir(parents=True)
        self.uploads = Uploads(self.access)

    def test_resume_interruption_offsets_ownership_and_idempotent_completion(self):
        row = self.uploads.create('session', 'example.txt', 6); identifier = row['upload_id']
        self.uploads.append(identifier, 0, io.BytesIO(b'abc'), 3)
        with self.assertRaises(ValueError): self.uploads.append(identifier, 3, io.BytesIO(b'd'), 3)
        self.assertEqual(self.uploads.status(identifier)['offset'], 3)
        self.assertEqual((self.uploads.root / identifier / 'data').stat().st_size, 3)
        with self.assertRaises(ValueError): self.uploads.append(identifier, 0, io.BytesIO(b'abc'), 3)
        with principal_scope(Principal('bob')):
            for action in (lambda: self.uploads.status(identifier), lambda: self.uploads.complete(identifier), lambda: self.uploads.cancel(identifier)):
                with self.assertRaises(AccessDenied): action()
        Uploads(self.access).append(identifier, 3, io.BytesIO(b'def'), 3)
        file = self.uploads.complete(identifier)
        self.assertEqual((self.workspace / file['path']).read_bytes(), b'abcdef')
        self.assertEqual(self.uploads.complete(identifier), file)
        self.assertFalse(reservations(self.access))

    def test_pending_uploads_count_toward_session_and_account_quotas(self):
        with patch.dict(os.environ, {'AGENT_SESSION_STORAGE_BYTES': '10', 'AGENT_ACCOUNT_STORAGE_BYTES': '12'}):
            row = self.uploads.create('session', 'a', 7)
            with self.assertRaisesRegex(ValueError, 'Session storage'): self.uploads.create('session', 'b', 4)
            self.access.ownership.claim('other')
            with self.assertRaisesRegex(ValueError, 'Account storage'): self.uploads.create('other', 'c', 6)
            self.uploads.cancel(row['upload_id'])
            self.uploads.create('other', 'c', 6)

    def test_deleted_session_does_not_block_active_uploads_or_publication(self):
        self.access.ownership.claim('deleted')
        self.access.ownership.delete('deleted')
        row = self.uploads.create('session', 'result.txt', 3)
        self.uploads.append(row['upload_id'], 0, io.BytesIO(b'abc'), 3)
        file = self.uploads.complete(row['upload_id'])
        self.assertEqual((self.workspace / file['path']).read_bytes(), b'abc')
        check_quota(self.access, 'session', 3)  # Worker publication uses this same check.
        reservation = reserve(self.access, '', 3, kind='multipart')
        release(self.access, reservation)
        with self.assertRaises(AccessDenied): self.access.workspace('deleted')
        with self.assertRaises(AccessDenied): self.uploads.create('deleted', 'forbidden.txt', 1)
        with self.assertRaises(AccessDenied): usage(self.access, 'deleted')

    def test_deleted_storage_still_counts_only_toward_its_owners_quota(self):
        self.access.ownership.claim('deleted')
        retained = self.access.workspace('deleted'); retained.mkdir()
        (retained / 'data').write_bytes(b'1234')
        private = self.access.metadata_root / '.pipelines' / 'deleted'; private.mkdir(parents=True)
        (private / 'snapshot').write_bytes(b'12345')
        self.access.ownership.delete('deleted')
        with principal_scope(Principal('bob')):
            self.access.ownership.claim('bobs-deleted')
            other = self.access.workspace('bobs-deleted'); other.mkdir()
            (other / 'data').write_bytes(b'x' * 100)
            self.access.ownership.delete('bobs-deleted')
        with patch.dict(os.environ, {'AGENT_ACCOUNT_STORAGE_BYTES': '10'}):
            check_quota(self.access, 'session', 1)
            with self.assertRaisesRegex(ValueError, 'Account storage'): check_quota(self.access, 'session', 2)
            with self.assertRaisesRegex(ValueError, 'Account storage'): reserve(self.access, '', 2, kind='multipart')
        with self.assertRaises(AccessDenied): usage(self.access, 'bobs-deleted')
        (retained / 'data').unlink(); retained.rmdir()
        (private / 'snapshot').unlink(); private.rmdir()
        with patch.dict(os.environ, {'AGENT_ACCOUNT_STORAGE_BYTES': '10'}):
            check_quota(self.access, 'session', 10)

    def test_deleted_storage_roots_cannot_redirect_account_scans(self):
        self.access.ownership.claim('deleted')
        retained = self.access.workspace('deleted')
        self.access.ownership.delete('deleted')
        outside = self.root / 'outside'; outside.mkdir()
        retained.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic links'): check_quota(self.access, 'session', 1)
        retained.unlink()
        private = self.access.metadata_root / '.pipelines' / 'deleted'; private.parent.mkdir()
        private.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symbolic links'): check_quota(self.access, 'session', 1)

    def test_streamed_multipart_preserves_boundary_lookalikes_and_rejects_truncation(self):
        data = b'x' * 70000 + b'\r\n--boundaryXYZ' + b'\x00end'
        wire = b'--boundary\r\nContent-Disposition: form-data; name="files"; filename="a.txt"\r\n\r\n' + data + b'\r\n--boundary--\r\n'
        class SmallReads(io.BytesIO):
            def read(self, size=-1):
                if size < 0 or size > 65536: raise AssertionError('unbounded read')
                return super().read(min(size, 997))
        with multipart(SmallReads(wire), len(wire), b'boundary', self.root) as parts:
            self.assertEqual(parts[0]['path'].read_bytes(), data)
        with self.assertRaises(ValueError):
            with multipart(SmallReads(wire[:-5]), len(wire), b'boundary', self.root): pass

    def test_large_preview_and_disk_staging_do_not_use_whole_workspace_limit(self):
        from tools.function_tools.workspace.file_inspection import inspect_bio_file
        (self.workspace / 'selected.txt').write_text('hello\n')
        with (self.workspace / 'large.txt').open('wb') as stream: stream.truncate(40 * 1024 * 1024)
        result = inspect_bio_file(str(self.workspace / 'large.txt'))
        self.assertTrue(result['truncated']); self.assertIsNone(result['line_count'])
        self.assertLessEqual(sum(map(len, result['preview'])), 65536)
        stage = self.root / 'stage'; stage.mkdir()
        before = stage_files(self.workspace, stage, ['selected.txt'])
        self.assertNotIn('large.txt', inventory(stage))
        (stage / 'selected.txt').write_text('changed')
        import_staged(self.workspace, before, stage)
        self.assertEqual((self.workspace / 'selected.txt').read_text(), 'changed')
        self.assertEqual((self.workspace / 'large.txt').stat().st_size, 40 * 1024 * 1024)

    def test_search_larger_than_old_limit_and_reports_scan_budget(self):
        from tools.function_tools.workspace.workspace_search import _search_text
        path = self.workspace / 'large.log'
        with path.open('wb') as stream:
            for _ in range(33): stream.write((b'x' * 4095 + b'\n') * 256)
            stream.write(b'needle\n')
        state = {}
        result = _search_text(path, {'path': 'large.log'}, ['needle'], 'needle', 10, state)
        self.assertEqual(len(result), 1)
        with patch.dict(os.environ, {'AGENT_SEARCH_SCAN_BYTES': '1024'}):
            state = {}; self.assertEqual(_search_text(path, {}, ['needle'], 'needle', 10, state), [])
            self.assertTrue(state['truncated'])


if __name__ == '__main__': unittest.main()
