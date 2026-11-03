"""Compatibility and boundary tests for the isolated general-purpose tool routes."""
import asyncio
import base64
import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from auth import Principal, principal_scope, OwnershipStore, AccessDenied
from isolation import network, WorkspaceAccess, supervisor
from isolation.provider_policy import validate
from isolation.network_client import install
from isolation.embeddings import calculate as embed


class CompatibilityTests(unittest.TestCase):
    def test_pipeline_scratch_counts_links_without_exporting_or_following_them(self):
        from isolation.files import inventory, scratch_usage
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); scratch = base / 'scratch'; scratch.mkdir()
            outside = base / 'outside'; outside.mkdir()
            (outside / 'large').write_bytes(b'x' * 10000)
            (scratch / 'link').symlink_to(outside, target_is_directory=True)
            (scratch / 'data').write_bytes(b'x' * 10)
            self.assertEqual(scratch_usage(scratch, max_bytes=1000), (scratch / 'link').lstat().st_size + 10)
            with self.assertRaisesRegex(ValueError, 'budget'): scratch_usage(scratch, max_bytes=1)
            with self.assertRaisesRegex(ValueError, 'entries'): scratch_usage(scratch, max_bytes=1000, max_files=1)
            with self.assertRaisesRegex(ValueError, 'regular'): inventory(scratch)

    def test_registry_matches_local_tools_without_host_filesystem(self):
        from tools.registry import build_all_tools
        with patch.dict(os.environ, {'AGENT_WORKER_BACKEND': 'local'}):
            local = {tool.name for tool in build_all_tools('unused')}
        with patch.dict(os.environ, {'AGENT_WORKER_BACKEND': 'docker'}):
            self.assertEqual({tool.name for tool in build_all_tools('unused')}, local)

    def test_provider_methods_and_destinations_are_restricted(self):
        accepted = [
            ('ncbi_retrieval', 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=protein', 'GET', None, ''),
            ('alphafold_download', 'https://alphafold.ebi.ac.uk/files/AF-P69905-F1-model_v6.cif', 'GET', None, ''),
            ('database_lookup', 'https://search.rcsb.org/rcsbsearch/v2/query', 'POST', '{}', 'application/json'),
            ('blast_search', 'https://blast.ncbi.nlm.nih.gov/Blast.cgi', 'POST', 'CMD=Put&QUERY=ACGT', 'application/x-www-form-urlencoded'),
        ]
        for name, url, method, body, kind in accepted:
            validate(name, urlsplit(url), method, body, kind)
            with self.assertRaises(ValueError): validate(name, urlsplit(url.replace('https:', 'http:')), method, body, kind)
            with self.assertRaises(ValueError): validate(name, urlsplit('https://example.org/'), method, body, kind)
        for method in ('DELETE', 'PUT'):
            with self.assertRaises(ValueError):
                network.fetch({'url': accepted[0][1], 'method': method}, 'ncbi_retrieval')
        with self.assertRaises(ValueError):
            network.fetch({'url': 'https://127.0.0.1/', 'method': 'GET'}, 'ncbi_retrieval')
        with self.assertRaises(ValueError):
            network.fetch({'url': accepted[0][1], 'method': 'POST', 'body': 'x' * 131073}, 'ncbi_retrieval')

    def test_requests_transport_preserves_json_streams_and_status(self):
        import requests
        replies = [
            {'status': 200, 'headers': {'Content-Type': 'application/json'}, 'body': base64.b64encode(b'{"value": 1}').decode()},
            {'status': 404, 'headers': {}, 'body': base64.b64encode(b'missing').decode()},
        ]
        writer = io.BytesIO()
        with patch.object(requests.sessions.Session, 'request'):
            install(None, 'database_lookup', io.BytesIO(b''.join(json.dumps(r).encode() + b'\n' for r in replies)), writer)
            result = requests.get('https://rest.uniprot.org/uniprotkb/search', params={'query': 'one two'}, headers={'Authorization': 'must-not-cross'})
            self.assertEqual(result.json(), {'value': 1})
            self.assertEqual(b''.join(result.iter_content(3)), b'{"value": 1}')
            result.close()
            with self.assertRaises(requests.HTTPError): requests.get('https://rest.uniprot.org/uniprotkb/search').raise_for_status()
        messages = [json.loads(line)['network_request'] for line in writer.getvalue().splitlines()]
        self.assertIn('query=one+two', messages[0]['url'])
        self.assertNotIn('must-not-cross', writer.getvalue().decode())

    def test_embedding_access_is_bounded_and_not_given_to_code(self):
        from models.config import DEFAULT_EMBEDDING_MODEL
        with patch('tools.infrastructure.tool_support.embeddings.embed_texts', return_value=[[1., 0.]]) as call:
            self.assertEqual(embed({'texts': ['fixture'], 'model': DEFAULT_EMBEDDING_MODEL}, 'evidence_retrieve'), {'vectors': [[1., 0.]]})
            for payload, name in [({'texts': ['fixture']}, 'python_execute'), ({'texts': ['x'] * 65}, 'evidence_index'), ({'texts': ['x'], 'model': 'unapproved'}, 'evidence_index')]:
                with self.assertRaises(ValueError): embed(payload, name)
            self.assertEqual(call.call_count, 1)

    def test_knowledge_crawler_uses_pinned_broker_in_isolated_mode(self):
        from tools.infrastructure.knowledge.crawlers import get_crawler, HttpCrawler
        from tools.infrastructure.knowledge.crawlers.http import fetch_page
        reply = {'status': 200, 'headers': {'Content-Type': 'text/plain'}, 'body': base64.b64encode(b'Public fixture').decode()}
        with patch.dict(os.environ, {'AGENT_WORKER_BACKEND': 'docker', 'AGENT_KNOWLEDGE_CRAWLER': 'scrapy'}), patch.object(network, 'fetch', return_value=reply) as fetch:
            self.assertIsInstance(get_crawler(), HttpCrawler)
            self.assertEqual(asyncio.run(fetch_page('https://example.org/', allowed_domains=['example.org']))[1], 'Public fixture')
            fetch.assert_called_once_with('https://example.org/', 'web_fetch')
            with self.assertRaises(ValueError): asyncio.run(fetch_page('https://other.org/', allowed_domains=['example.org']))

    def test_capabilities_report_configuration_and_keep_unavailable_entries(self):
        from auth import ExecutionUnavailable
        from tools.capabilities import describe
        pipelines = [{'name': name, 'engine': engine} for name, engine in [('template_shell', 'shell'), ('template_wdl', 'wdl'), ('unregistered_workflow', 'shell')]]
        with patch.dict(os.environ, {'AGENT_WORKER_BACKEND': 'docker', 'OPENROUTER_API_KEY': ''}), patch.object(supervisor, 'ensure_available'), patch('tools.infrastructure.pipeline_engine.broker._configured', side_effect=ValueError('missing')):
            value = describe(pipelines)
            self.assertEqual(value['tools']['ncbi_retrieval']['status'], 'available')
            self.assertEqual(value['tools']['evidence_retrieve']['status'], 'needs_configuration')
            self.assertEqual(value['tools']['knowledge_status']['status'], 'available')
            self.assertEqual(value['pipelines']['template_shell']['status'], 'available')
            self.assertEqual(value['pipelines']['template_wdl']['status'], 'needs_configuration')
            self.assertEqual(value['pipelines']['unregistered_workflow']['status'], 'unsupported')
            self.assertEqual(len(value['quick_starts']), 6)
            with patch.object(supervisor, 'ensure_available', side_effect=ExecutionUnavailable('stale image')):
                value = describe(pipelines)
                self.assertEqual(value['tools']['pdb_download']['status'], 'needs_configuration')
                self.assertEqual(value['pipelines']['template_shell']['status'], 'needs_configuration')


@unittest.skipUnless(os.getenv('AGENT_TEST_DOCKER') == '1', 'Set AGENT_TEST_DOCKER=1')
class ContainerCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'AGENT_WORKER_BACKEND': 'docker', 'AGENT_AUTH_MODE': 'multiuser'})
        self.env.start(); self.addCleanup(self.env.stop)
        scope = principal_scope(Principal('compat')); scope.__enter__(); self.addCleanup(scope.__exit__, None, None, None)
        self.access = WorkspaceAccess(OwnershipStore(self.base / 'metadata'), self.base / 'sessions')
        self.access.ownership.claim('session')
        self.root = self.access.workspace('session'); self.root.mkdir(parents=True)
        self.metadata = {'session_id': 'session', 'owner_user_id': 'compat', 'session_dir': str(self.root), 'workspace_dir': str(self.root / 'outputs')}

    def run_tool(self, module, name, arguments, replies):
        handler = importlib.import_module(module)._operation
        def response(parsed, *args, **kwargs):
            value = replies.pop(0)
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            return {'status': 200, 'headers': {'Content-Type': 'application/json'}, 'body': base64.b64encode(raw).decode()}
        with patch.object(network, '_addresses', return_value=['93.184.216.34']), patch.object(network, '_exchange', side_effect=response):
            result = asyncio.run(supervisor.calculate(handler, arguments, self.metadata, name, access=self.access))
        self.assertEqual(replies, [])
        return result

    def test_alphafold_download(self):
        data = b'data_fixture\n_entry.id fixture\n'
        value = self.run_tool('tools.function_tools.biology.alphafold_download', 'alphafold_download', {'accession': 'P69905', 'file_format': 'cif'}, [[{'entryId': 'AF-P69905-F1', 'cifUrl': 'https://alphafold.ebi.ac.uk/files/AF-P69905-F1-model_v6.cif'}], data])
        self.assertEqual((self.root / value['data']['structure_path']).read_bytes(), data)

    def test_ncbi_download_and_metadata(self):
        # A deleted chat must not prevent this owned worker publishing its files.
        self.access.ownership.claim('deleted-chat')
        self.access.ownership.delete('deleted-chat')
        value = self.run_tool('tools.function_tools.biology.ncbi_retrieval', 'ncbi_retrieval',
                             {'accessions': ['NM_000518'], 'max_records': 1}, [
            {'esearchresult': {'count': '1', 'querykey': '1', 'webenv': 'fixture'}},
            b'>fixture synthetic sequence\nACGTACGT\n',
            b'<GBSet><GBSeq><GBSeq_primary-accession>FIXTURE</GBSeq_primary-accession><GBSeq_length>8</GBSeq_length><GBSeq_organism>synthetic construct</GBSeq_organism></GBSeq></GBSet>',
        ])
        self.assertEqual(value['data']['downloaded_count'], 1)
        for key in ('fasta_paths', 'metadata_paths'):
            self.assertEqual(len(value['data'][key]), 1)
            self.assertTrue(Path(value['data'][key][0]).is_file())

    def test_blast_submission_and_poll(self):
        common = {'sequence': 'ACGTACGT', 'rid': None, 'program': 'blastn', 'database': 'nt', 'hitlist_size': 1, 'expect': 10., 'wait': False, 'timeout_seconds': 5}
        value = self.run_tool('tools.function_tools.biology.blast_search', 'blast_search', common, [b'RID = FIXTURE-1\nRTOE = 1\n'])
        self.assertEqual(value['data']['rid'], 'FIXTURE-1')
        value = self.run_tool('tools.function_tools.biology.blast_search', 'blast_search', {**common, 'sequence': None, 'rid': 'FIXTURE-1'}, [b'Status=READY\n', {'BlastOutput2': [{'report': {'results': {'search': {'hits': []}}}}]}])
        self.assertEqual(value['data']['state'], 'READY')

    def test_database_sources(self):
        cases = [('uniprot', 'hemoglobin', None, {'results': []}), ('interpro', 'IPR000001', None, {'results': []}),
                 ('quickgo', 'GO:0008150', None, {'results': []}), ('kegg', 'hsa:10458', 'get', b'ENTRY       hsa:10458\n///\n'),
                 ('pdb', '1A3N', None, {'struct': {'title': 'Fixture'}}), ('alphafold', 'P69905', None, [{'entryId': 'AF-P69905-F1'}])]
        for source, query, operation, payload in cases:
            with self.subTest(source=source):
                value = self.run_tool('tools.function_tools.biology.database_lookup', 'database_lookup', {'database': source, 'query': query, 'operation': operation, 'max_results': 2, 'taxid': None}, [payload])
                self.assertEqual(value['data']['database'], source)

    def test_evidence_index_and_retrieval_use_host_embeddings(self):
        from tools.infrastructure.tool_support.evidence_models import EvidenceRecord
        item = EvidenceRecord(id='fixture-source', source='web', title='Fixture', url='https://example.org/', text='A synthetic document about widgets.', retrieved_at='2026-11-03T00:00:00Z')
        (self.root / 'evidence.json').write_text(json.dumps({'schema_version': 1, 'sources': [item.model_dump(mode='json')]}))
        index = importlib.import_module('tools.function_tools.knowledge.evidence_index')._operation
        retrieve = importlib.import_module('tools.function_tools.knowledge.evidence_retrieve')._operation
        with patch('tools.infrastructure.tool_support.embeddings.embed_texts', side_effect=lambda texts, **kw: [[1., 0.] for _ in texts]) as embedding:
            value = asyncio.run(supervisor.calculate(index, {'evidence_paths': ['evidence.json'], 'chunk_chars': 1000, 'overlap': 100}, self.metadata, 'evidence_index', access=self.access))
            result = asyncio.run(supervisor.calculate(retrieve, {'question': 'widgets', 'evidence_paths': None, 'top_k': 2, 'index_path': value['data']['index_path']}, self.metadata, 'evidence_retrieve', access=self.access))
        self.assertGreaterEqual(embedding.call_count, 2)
        self.assertEqual(result['data']['returned'], 1)
        self.assertTrue((self.root / result['data']['evidence_path']).is_file())


class KnowledgeBrokerTests(unittest.TestCase):
    def test_durable_ingest_status_retrieve_and_cross_user_denial(self):
        from harness import runtime
        from harness.sessions import SessionMetadataStore
        from tools.infrastructure.knowledge import broker, worker, KnowledgeService
        from tools.infrastructure.knowledge.models import KnowledgePage
        from unittest.mock import AsyncMock
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            environment = {'AGENT_AUTH_MODE': 'multiuser', 'AGENT_WORKER_BACKEND': 'docker',
                           'AGENT_METADATA_DIR': str(base / 'metadata'), 'AGENT_KNOWLEDGE_DB': str(base / 'knowledge.sqlite3')}
            with patch.dict(os.environ, environment), principal_scope(Principal('alice')):
                store = SessionMetadataStore(base / 'metadata')
                access = WorkspaceAccess(store.ownership, base / 'sessions')
                access.ownership.claim('owned-session')
                root = access.workspace('owned-session')
                metadata = {'session_id': 'owned-session', 'owner_user_id': 'alice', 'session_dir': str(root), 'workspace_dir': str(root / 'outputs')}
                with patch.object(runtime, 'STATE_STORE', store), patch.object(KnowledgeService, 'dispatch'):
                    arguments = {'request': 'Index fixture widgets', 'collection_id': None, 'seed_urls': ['https://example.org/'],
                                 'allowed_domains': ['example.org'], 'max_pages': 1, 'max_depth': 0, 'refresh': False}
                    job = asyncio.run(broker.calculate('knowledge_ingest', arguments, metadata, access=access))['data']
                    service = KnowledgeService()
                    page = KnowledgePage('https://example.org/', 'Widgets', 'Widget documentation with one synthetic fact.')
                    with patch.object(worker, 'crawl', AsyncMock(return_value=[page])), patch.object(worker, 'embed_texts', side_effect=lambda texts, **kw: [[1., 0.] for _ in texts]):
                        self.assertEqual(worker.execute(service, job['job_id']), 0)
                    status = asyncio.run(broker.calculate('knowledge_status', {'job_id': job['job_id']}, metadata, access=access))
                    self.assertEqual(status['data']['status'], 'succeeded')
                    with patch('tools.function_tools.knowledge.knowledge_retrieve.embed_texts', return_value=[[1., 0.]]):
                        result = asyncio.run(broker.calculate('knowledge_retrieve', {'collection_id': job['collection_id'], 'question': 'Widget', 'top_k': 2}, metadata, access=access))
                    self.assertEqual(result['data']['returned'], 1)
                    self.assertTrue((root / result['data']['evidence_path']).is_file())
                    with principal_scope(Principal('bob')), self.assertRaises(AccessDenied):
                        asyncio.run(broker.calculate('knowledge_status', {'job_id': job['job_id']}, metadata, access=access))

@unittest.skipUnless(os.getenv('AGENT_TEST_DOCKER') == '1', 'Set AGENT_TEST_DOCKER=1')
class PipelineEngineTests(unittest.TestCase):
    setUp = ContainerCompatibilityTests.setUp

    def test_local_engine_lifecycle_and_owned_results(self):
        import time
        import shlex
        from tools.infrastructure.pipeline_engine import broker, service
        from tools.infrastructure.pipeline_engine.engine.inputs import pipeline_input_specs
        for name in ('template_shell', 'template_snakemake', 'template_nextflow', 'template_bio'):
            with self.subTest(pipeline=name):
                examples = broker.dispatch(self.root, f'agent-pipeline example --pipeline {name}', access=self.access)['files']
                _, manifest, _ = service.definition(name)
                arguments = []
                for slot, spec in pipeline_input_specs(manifest).items():
                    candidates = [item['workspace_path'] for item in examples if any(item['workspace_path'].endswith(ext) for ext in spec['accepts'])]
                    if len(candidates) > 1:
                        candidates = [path for path in candidates if slot in Path(path).stem] or candidates
                    self.assertTrue(candidates, slot)
                    arguments.extend(['--input', shlex.quote(f'{slot}={candidates[0]}')])
                plan = broker.dispatch(self.root, f'agent-pipeline plan --pipeline {name} ' + ' '.join(arguments), access=self.access)
                job = broker.dispatch(self.root, plan['command'], access=self.access)
                self.assertEqual(broker.dispatch(self.root, plan['command'], access=self.access)['job_id'], job['job_id'])
                deadline = time.monotonic() + 185
                while time.monotonic() < deadline:
                    state = broker.dispatch(self.root, f"agent-pipeline status --job-id {job['job_id']}", access=self.access)
                    if state['status'] not in {'queued', 'running'}: break
                    time.sleep(.25)
                self.assertEqual(state['status'], 'succeeded', state)
                result = broker.dispatch(self.root, f"agent-pipeline results --job-id {job['job_id']}", access=self.access)
                self.assertTrue(result['files'])
                for file in result['files']: self.assertTrue((self.root / file['path']).is_file(), file)
                with broker.bundle_stream(self.root, job['job_id'], access=self.access) as stream:
                    self.assertEqual(stream.read(2), b'PK')
                with principal_scope(Principal('other')), self.assertRaises(AccessDenied):
                    broker.dispatch(self.root, f"agent-pipeline status --job-id {job['job_id']}", access=self.access)


class PipelineControllerTests(unittest.TestCase):
    setUp = ContainerCompatibilityTests.setUp

    def prepare(self):
        from tools.infrastructure.pipeline_engine import broker
        from tools.infrastructure.pipeline_engine.store import JobStore
        (self.root / 'reads.txt').write_text('ACGTACGT\n')
        (self.root / 'metadata.tsv').write_text('id\tcategory\nsample\tfixture\n')
        plan = broker.dispatch(self.root, 'agent-pipeline plan --pipeline template_shell --input reads=reads.txt --input metadata=metadata.tsv', access=self.access)
        private = self.access.metadata_root / '.pipelines' / 'session'
        store = JobStore(private)
        store.update(plan['plan_id'], status='queued', execution_backend='docker')
        return private, store, plan['plan_id']

    def test_cancellation_stops_worker_and_uses_actual_workspace_for_quota(self):
        from tools.infrastructure.pipeline_engine import isolated_controller as controller
        private, store, identifier = self.prepare()
        stopped = []
        async def worker(*args, **kwargs):
            self.assertEqual(kwargs['quota_access'].workspaces_root, self.access.workspaces_root)
            store.update(identifier, status='cancelling')
            try: await asyncio.Event().wait()
            finally: stopped.append(True)
        with patch.object(supervisor, 'calculate', side_effect=worker):
            asyncio.run(controller.execute(self.access, 'session', identifier))
        self.assertTrue(stopped)
        self.assertEqual(store.get(identifier)['status'], 'cancelled')

    def test_cancel_before_controller_starts(self):
        from tools.infrastructure.pipeline_engine import isolated_controller as controller
        private, store, identifier = self.prepare()
        store.update(identifier, status='cancelling')
        with patch.object(supervisor, 'calculate') as launch:
            asyncio.run(controller.execute(self.access, 'session', identifier))
            launch.assert_not_called()
        self.assertEqual(store.get(identifier)['status'], 'cancelled')

    def test_dead_controller_is_interrupted_without_resubmission(self):
        from tools.infrastructure.pipeline_engine import isolated_controller as controller
        private, store, identifier = self.prepare()
        store.update(identifier, status='running', controller_pid=1234, controller_identity='old')
        with patch.object(controller.service, 'identity', return_value='different'), patch.object(controller.subprocess, 'Popen') as launch:
            self.assertEqual(controller.status(private, identifier)['status'], 'interrupted')
            launch.assert_not_called()


if __name__ == '__main__': unittest.main()
