"""The only backend adapter that knows BioAgent account, session and storage APIs."""
from contextlib import contextmanager
import secrets
import tempfile
from pathlib import Path

from auth import AuthError, AccessDenied, Principal, current_principal, principal_scope
from auth.store import AuthStore, database, password_hash


class Accounts:
    def __init__(self, db):
        self.db = db

    def execute(self, sql, parameters=()):
        return self.db.execute(sql, parameters)

    def user(self, user_id):
        row = self.db.execute('SELECT user_id,username,disabled FROM users WHERE user_id=?', (user_id,)).fetchone()
        return dict(row) if row else None

    def named_user(self, username):
        row = self.db.execute('SELECT user_id,username,disabled FROM users WHERE username=?', (username,)).fetchone()
        if not row or row['disabled']:
            raise ValueError('No such active user.')
        return Principal(row['user_id'], row['username'])

    def create_user(self, user_id, username):
        self.db.execute('INSERT INTO users(user_id,username,password_hash) VALUES (?,?,?)',
                        (user_id, username, password_hash(secrets.token_urlsafe(48))))

    def sync_username(self, user_id, username):
        collision = self.db.execute('SELECT user_id FROM users WHERE username=?', (username,)).fetchone()
        if collision and collision['user_id'] != user_id:
            raise ValueError('Website username is already assigned to another account.')
        self.db.execute('UPDATE users SET username=? WHERE user_id=?', (username, user_id))

    def create_login(self, digest, user_id, expires):
        self.db.execute('INSERT INTO logins VALUES (?,?,?)', (digest, user_id, expires))

    def revoke_login(self, digest):
        self.db.execute('DELETE FROM logins WHERE token_hash=?', (digest,))


class BioAgentHost:
    auth_error = AuthError
    access_denied = AccessDenied
    current_user = staticmethod(current_principal)
    principal = staticmethod(Principal)

    def user_scope(self, user_id):
        return principal_scope(Principal(user_id))

    @contextmanager
    def identity_transaction(self):
        # Keep bridge identity rows in the existing auth database, allowing
        # grant consumption and login creation in a single atomic transaction.
        with database(AuthStore().path) as db:
            yield Accounts(db)

    def require_user(self, user_id):
        with self.identity_transaction() as accounts:
            user = accounts.user(user_id)
        if not user or user['disabled']:
            raise AuthError('Account unavailable.')

    def ensure_session(self, session_id):
        from harness.runtime import STATE_STORE
        with STATE_STORE.locked_session(session_id) as (session, _):
            return dict(session.metadata.get('website_binding') or {})

    def require_session(self, session_id):
        from harness.runtime import STATE_STORE
        STATE_STORE.ownership.require(session_id)

    def get_run(self, run_id):
        from interfaces.api import get_run
        return get_run(run_id)

    def list_runs(self, session_id):
        from interfaces.api import list_runs
        return list_runs(session_id)

    def list_files(self, session_id):
        from interfaces.api import list_workspace_files
        return list_workspace_files(session_id).get('files', [])

    def resolve_transfer_files(self, session_id, paths):
        self.require_session(session_id)
        available = {f.get('workspace_path') or f.get('path'): f for f in self.list_files(session_id)}
        selected = {}
        for path in dict.fromkeys(paths):
            if path.startswith('pipeline-bundles/'):
                from harness.sandbox import execution_access
                from tools.infrastructure.pipeline_engine.broker import bundle_transfer_files
                access = execution_access()
                files = bundle_transfer_files(access.workspace(session_id), path, access=access)
            elif path.startswith('outputs/pipelines/'):
                from harness.sandbox import execution_access
                from tools.infrastructure.pipeline_engine.broker import published_transfer_file
                access = execution_access()
                files = [published_transfer_file(access.workspace(session_id), path, access=access)]
            elif path in available:
                files = [available[path]]
            else:
                raise ValueError('Selected file is not available in this session: ' + path)
            for file in files:
                file_path = file.get('workspace_path') or file['path']
                if file_path.startswith(('pipeline-artifacts/', 'outputs/pipelines/')):
                    file = {**file, 'kind': 'pipeline_output'}
                selected[file_path] = file
        return list(selected.values())

    def relative_file_path(self, path):
        from harness.sandbox import relative_file_path
        return str(relative_file_path(path))

    def uploads(self):
        from interfaces.uploads import Uploads
        from harness.sandbox import execution_access
        return Uploads(execution_access())

    def publish_text(self, session_id, filename, data, access=None):
        from harness.sandbox import execution_access
        from isolation.storage import publish
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'export'
            source.write_bytes(data)
            return publish(access or execution_access(), session_id, filename, source, len(data), stable_name=False)

    def login_cookie(self, token):
        from auth import COOKIE_NAME
        from interfaces.auth import secure_cookie
        return f'{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=28800' + ('; Secure' if secure_cookie() else '')

    def serve_file(self, handler, session_id, path):
        from urllib.parse import urlencode
        handler.path = '/workspace/file?' + urlencode({'session_id': session_id, 'path': path})
        handler._handle_workspace_file()
