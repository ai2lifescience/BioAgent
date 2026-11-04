"""Owner-scoped commands. Site backends poll; no browser or model-held credentials."""
import json
import secrets
import time
from uuid import uuid4
from ..bridge import get_bridge
from ..ports import get_host
from ..identity import Federation
from ..config import clients


class Transfers:
    def __init__(self):
        self.bridge = get_bridge()
        with self.bridge.db(True) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS website_commands (
                id TEXT PRIMARY KEY, site TEXT, owner TEXT, subject TEXT, session_id TEXT,
                operation TEXT, payload TEXT, state TEXT, lease TEXT, expires REAL,
                result TEXT, created REAL, attempts INTEGER DEFAULT 0)''')
            db.execute('CREATE TABLE IF NOT EXISTS website_connectors (site TEXT PRIMARY KEY, capabilities TEXT, last_seen REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS website_command_uploads (upload_id TEXT PRIMARY KEY, command_id TEXT)')

    def connections(self):
        Federation()
        with get_host().identity_transaction() as db:
            rows = db.execute('SELECT site_id,subject FROM external_identities WHERE user_id=?', (get_host().current_user().user_id,)).fetchall()
        configured = clients()
        with self.bridge.db() as db:
            backends = {r['site']:r for r in db.execute('SELECT * FROM website_connectors').fetchall()}
        return [{'site_id': r['site_id'], 'external_subject': r['subject'],
                 'capabilities':json.loads(backends[r['site_id']]['capabilities']) if r['site_id'] in backends else {},
                 'backend_last_seen':backends[r['site_id']]['last_seen'] if r['site_id'] in backends else None}
                for r in rows if r['site_id'] in configured]

    def create(self, session, site, operation, payload):
        get_host().require_session(session)
        links = [r for r in self.connections() if r['site_id'] == site]
        if len(links) != 1:
            raise ValueError('Website must have exactly one explicitly linked account for this user.')
        if operation not in {'search', 'pull', 'push'}:
            raise ValueError('Unsupported transfer operation.')
        payload = dict(payload)
        if operation == 'push':
            paths = payload.pop('paths', [])
            if not paths or len(paths) > 100:
                raise ValueError('Select between 1 and 100 files to push.')
            payload['files'] = get_host().resolve_transfer_files(session, paths)
        if len(json.dumps(payload)) > 512*1024: raise ValueError('Transfer manifest is too large.')
        identifier = uuid4().hex
        with self.bridge.db(True) as db:
            db.execute('INSERT INTO website_commands VALUES (?,?,?,?,?,?,?,?,?,?,?, ?,0)',
                       (identifier, site, get_host().current_user().user_id, links[0]['external_subject'], session,
                        operation, json.dumps(payload), 'queued', '', 0, '{}', time.time()))
        return self.status(identifier)

    def status(self, identifier):
        with self.bridge.db() as db:
            row = db.execute('SELECT * FROM website_commands WHERE id=? AND owner=?', (identifier, get_host().current_user().user_id)).fetchone()
        if not row: raise get_host().access_denied('Transfer not found.')
        get_host().require_session(row['session_id'])
        return {'transfer_id': row['id'], 'site_id': row['site'], 'operation': row['operation'], 'state': row['state'], 'result': json.loads(row['result'])}

    def pending(self, site, capabilities=None, exclude_ids=None):
        if capabilities is not None and (not isinstance(capabilities,dict) or len(json.dumps(capabilities))>32768):
            raise ValueError('Invalid connector capabilities.')
        exclude_ids = [] if exclude_ids is None else exclude_ids
        if not isinstance(exclude_ids, list) or len(exclude_ids) > 1000 or any(
                not isinstance(value, str) or len(value) != 32 or any(c not in '0123456789abcdef' for c in value)
                for value in exclude_ids):
            raise ValueError('Invalid active command IDs.')
        excluded = ' AND id NOT IN (' + ','.join('?' for _ in exclude_ids) + ')' if exclude_ids else ''
        items = []
        with self.bridge.db(True) as db:
            if capabilities is not None:
                db.execute('INSERT INTO website_connectors VALUES (?,?,?) ON CONFLICT(site) DO UPDATE SET capabilities=excluded.capabilities,last_seen=excluded.last_seen', (site,json.dumps(capabilities),time.time()))
            else: db.execute('UPDATE website_connectors SET last_seen=? WHERE site=?',(time.time(),site))
            rows = db.execute("SELECT * FROM website_commands WHERE site=? AND (state='queued' OR (state='running' AND expires<?)) " + excluded + " ORDER BY created LIMIT 1", (site,time.time(),*exclude_ids)).fetchall()
            for row in rows:
                try:
                    get_host().require_user(row['owner'])
                    with get_host().user_scope(row['owner']): get_host().require_session(row['session_id'])
                except (get_host().auth_error, get_host().access_denied):
                    db.execute("UPDATE website_commands SET state='failed',result=? WHERE id=?", (json.dumps({'error':'Account or session unavailable.'}),row['id']))
                    continue
                if row['attempts'] >= 5:
                    db.execute("UPDATE website_commands SET state='failed',result=? WHERE id=?", (json.dumps({'error':'Backend lease expired repeatedly.'}),row['id']))
                    continue
                lease = secrets.token_urlsafe(32)
                db.execute("UPDATE website_commands SET state='running',lease=?,expires=?,attempts=attempts+1 WHERE id=?", (lease,time.time()+120,row['id']))
                items.append({'id':row['id'],'subject':row['subject'],'session_id':row['session_id'],'operation':row['operation'],'payload':json.loads(row['payload']),'lease':lease,'created_at':row['created']})
        return {'commands':items}

    def service_command(self, site, identifier, lease=None):
        with self.bridge.db() as db:
            row = db.execute('SELECT * FROM website_commands WHERE id=? AND site=?', (identifier,site)).fetchone()
        if not row or row['state'] != 'running' or row['expires'] < time.time() or (lease is not None and not secrets.compare_digest(row['lease'],lease)):
            raise get_host().access_denied('Transfer lease is unavailable.')
        get_host().require_user(row['owner'])
        return dict(row)

    def heartbeat(self, site, body):
        row = self.service_command(site, body.get('id',''), body.get('lease',''))
        with self.bridge.db(True) as db:
            db.execute("UPDATE website_commands SET expires=? WHERE id=? AND lease=? AND state='running'", (time.time()+120,row['id'],row['lease']))
        return {'renewed':True}

    def retry(self, identifier):
        value = self.status(identifier)
        if value['state'] != 'failed': raise ValueError('Only failed transfers can be retried; running transfers resume automatically.')
        with self.bridge.db(True) as db:
            db.execute("UPDATE website_commands SET state='queued',attempts=0,result='{}' WHERE id=? AND state='failed'",(identifier,))
        return self.status(identifier)

    def acknowledge(self, site, body):
        row = self.service_command(site, body.get('id',''), body.get('lease',''))
        result = body.get('result') or {}
        if len(json.dumps(result)) > 512*1024: raise ValueError('Transfer result is too large.')
        if body.get('ok') and row['operation'] == 'pull':
            file = result.get('file') or {}
            with get_host().user_scope(row['owner']):
                saved = next((f for f in get_host().list_files(row['session_id']) if (f.get('workspace_path') or f.get('path')) == file.get('path')), None)
            if not saved: raise ValueError('Backend has not published the pulled file into the session.')
        with self.bridge.db(True) as db:
            changed = db.execute("UPDATE website_commands SET state=?,result=? WHERE id=? AND lease=? AND state='running'", ('succeeded' if body.get('ok') else 'failed',json.dumps(result),row['id'],row['lease'])).rowcount
        if not changed: raise ValueError('Transfer lease changed.')
        return {'acknowledged':True}

    def artifact(self, site, identifier, path):
        row = self.service_command(site,identifier)
        payload = json.loads(row['payload'])
        if row['operation'] != 'push' or path not in {f.get('workspace_path') or f.get('path') for f in payload['files']}:
            raise get_host().access_denied('File is outside this transfer.')
        return row

    def authorize_upload(self, site, identifier, session):
        row = self.service_command(site, identifier)
        if row['operation'] != 'pull' or row['session_id'] != session or row['owner'] != get_host().current_user().user_id:
            raise get_host().access_denied('Upload is outside this transfer.')
        get_host().require_session(session)

    def bind_upload(self, identifier, upload):
        with self.bridge.db(True) as db:
            db.execute('INSERT OR REPLACE INTO website_command_uploads VALUES (?,?)',(upload,identifier))

    def upload_command(self, upload):
        with self.bridge.db() as db:
            row=db.execute('SELECT command_id FROM website_command_uploads WHERE upload_id=?',(upload,)).fetchone()
        return row['command_id'] if row else None
