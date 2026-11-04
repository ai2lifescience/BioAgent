"""Durable website conversation links and provenance, independent of host schemas."""
import json
import hashlib
import secrets
import time
from uuid import uuid4

from .ports import get_host
from .config import text_id
from .bridge import get_bridge, _now


class WebsiteAccounts:
    def __init__(self):
        self.bridge = get_bridge()
        with self.bridge.db(True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS website_sessions (session_id TEXT PRIMARY KEY, site_id TEXT, owner_user_id TEXT, scope_key TEXT, created_at TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS website_heads (site_id TEXT, owner_user_id TEXT, scope_key TEXT, session_id TEXT, PRIMARY KEY(site_id,owner_user_id,scope_key))')
            db.execute('CREATE TABLE IF NOT EXISTS website_run_context (run_id TEXT PRIMARY KEY, session_id TEXT, context TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS website_imports (upload_id TEXT PRIMARY KEY, session_id TEXT, site_id TEXT, resource_id TEXT, revision TEXT, file TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS website_downloads (digest TEXT PRIMARY KEY, site_id TEXT, owner_user_id TEXT, session_id TEXT, path TEXT, expires REAL)')

    def download_ticket(self, site_id, session_id, path):
        self.require(site_id, session_id)
        path = get_host().relative_file_path(path)
        token = secrets.token_urlsafe(32)
        with self.bridge.db(True) as db:
            db.execute('DELETE FROM website_downloads WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO website_downloads VALUES (?,?,?,?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), site_id, get_host().current_user().user_id, session_id, path, time.time()+60))
        return {'token': token, 'expires_in': 60}

    def consume_download(self, token):
        if len(token)>256:
            raise get_host().auth_error('Invalid download ticket.')
        with self.bridge.db(True) as db:
            digest=hashlib.sha256(token.encode()).hexdigest()
            row=db.execute('SELECT * FROM website_downloads WHERE digest=? AND expires>?', (digest,time.time())).fetchone()
            if not row: raise get_host().auth_error('Download ticket expired or already used.')
            db.execute('DELETE FROM website_downloads WHERE digest=?', (digest,))
        get_host().require_user(row['owner_user_id'])
        return dict(row)

    def conversation(self, site_id, scope_key='workspace', *, new=False):
        scope_key = text_id(scope_key, 'conversation scope')
        owner = get_host().current_user().user_id
        with self.bridge.db(True) as db:
            row = db.execute('SELECT session_id FROM website_heads WHERE site_id=? AND owner_user_id=? AND scope_key=?', (site_id, owner, scope_key)).fetchone()
            if row and not new:
                try:
                    get_host().require_session(row['session_id'])
                    return row['session_id']
                except get_host().access_denied:
                    pass
            identifier = str(uuid4())
            get_host().ensure_session(identifier)
            db.execute('INSERT INTO website_sessions VALUES (?,?,?,?,?)', (identifier, site_id, owner, scope_key, _now()))
            db.execute('INSERT OR REPLACE INTO website_heads VALUES (?,?,?,?)', (site_id, owner, scope_key, identifier))
            return identifier

    def require(self, site_id, session_id):
        with self.bridge.db() as db:
            row = db.execute('SELECT * FROM website_sessions WHERE site_id=? AND session_id=? AND owner_user_id=?', (site_id, session_id, get_host().current_user().user_id)).fetchone()
        if not row:
            raise get_host().access_denied('Website conversation not found.')
        get_host().require_session(session_id)
        return dict(row)

    def record_run(self, run_id, session_id, binding):
        row = self.bridge._binding(binding['binding_id'], binding['token'])
        with self.bridge.db(True) as db:
            db.execute('INSERT OR REPLACE INTO website_run_context VALUES (?,?,?)', (run_id, session_id, row['context']))
        target=json.loads(row['context']).get('delivery_target')
        if isinstance(target,dict) and target:
            from .delivery import Deliveries
            Deliveries().schedule(row['site_id'],run_id,target,baseline=get_host().list_files(session_id))

    def results(self, site_id, scope_key='workspace'):
        with self.bridge.db() as db:
            sessions = db.execute('SELECT * FROM website_sessions WHERE site_id=? AND owner_user_id=? AND scope_key=? ORDER BY created_at DESC', (site_id, get_host().current_user().user_id, scope_key)).fetchall()
            contexts = {r['run_id']: json.loads(r['context']) for r in db.execute('SELECT c.* FROM website_run_context c JOIN website_sessions s ON s.session_id=c.session_id WHERE s.site_id=? AND s.owner_user_id=? AND s.scope_key=?', (site_id, get_host().current_user().user_id, scope_key))}
        result = []
        for session in sessions:
            try:
                get_host().require_session(session['session_id'])
            except get_host().access_denied:
                continue
            runs = []
            for job in get_host().list_runs(session['session_id']):
                value = job.get('result') or {}
                runs.append({**{k: job.get(k) for k in ('run_id', 'status', 'created_at', 'updated_at')},
                             'answer': value.get('answer', ''), 'context': contexts.get(job['run_id'], {}),
                             'artifacts': value.get('artifacts', value.get('files', []))})
            result.append({'session_id': session['session_id'], 'created_at': session['created_at'],
                           'runs': runs, 'files': get_host().list_files(session['session_id'])})
        return {'conversations': result}
