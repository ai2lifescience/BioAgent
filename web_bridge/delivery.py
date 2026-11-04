"""Durable, site-scoped result handoff. Receivers pull, persist, then acknowledge.

Only explicitly selected runs or runs started on a sample page enter this queue.
No browser or model receives the site's service credential.
"""
import hashlib
import json
import secrets
import time
from uuid import uuid4
from .ports import get_host
from .bridge import get_bridge, _now
from .config import clients


class Deliveries:
    def __init__(self):
        self.bridge = get_bridge()
        with self.bridge.db(True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS website_deliveries (id TEXT PRIMARY KEY, site_id TEXT, subject TEXT, owner TEXT, run_id TEXT, session_id TEXT, target TEXT, baseline TEXT, manifest TEXT, state TEXT, attempts INTEGER DEFAULT 0, retry_at REAL DEFAULT 0, error TEXT, receipt TEXT, created_at TEXT, UNIQUE(site_id,run_id,target))')
            db.execute('CREATE TABLE IF NOT EXISTS website_shares (digest TEXT PRIMARY KEY, site_id TEXT, owner TEXT, run_id TEXT, expires REAL)')

    def sites(self):
        owner=get_host().current_user().user_id
        from .identity import Federation
        Federation()
        with get_host().identity_transaction() as db:
            rows=db.execute('SELECT site_id FROM external_identities WHERE user_id=?',(owner,)).fetchall()
        return [{'site_id':r['site_id'], 'origin':clients()[r['site_id']]['origins'][0], 'origins':clients()[r['site_id']]['origins']} for r in rows if clients().get(r['site_id'],{}).get('origins')]

    def schedule(self, site, run_id, target, *, baseline=None):
        if not isinstance(target,dict) or not target or len(json.dumps(target,allow_nan=False).encode())>16384:
            raise ValueError('Choose a valid website destination.')
        target=json.loads(json.dumps(target,allow_nan=False))
        job=get_host().get_run(run_id)
        owner=get_host().current_user().user_id
        with get_host().identity_transaction() as db:
            identities=db.execute('SELECT subject FROM external_identities WHERE site_id=? AND user_id=?',(site,owner)).fetchall()
        if len(identities)!=1: raise ValueError('Destination needs one unambiguous linked website identity.')
        encoded=json.dumps(target,sort_keys=True)
        with self.bridge.db(True) as db:
            db.execute('INSERT OR IGNORE INTO website_deliveries (id,site_id,subject,owner,run_id,session_id,target,baseline,state,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (uuid4().hex,site,identities[0]['subject'],owner,run_id,job['session_id'],encoded,json.dumps(baseline),'waiting',_now()))
            return dict(db.execute('SELECT id,state FROM website_deliveries WHERE site_id=? AND run_id=? AND target=?',(site,run_id,encoded)).fetchone())

    def share(self, site, run_id):
        if site not in {s['site_id'] for s in self.sites()}: raise ValueError('Website account is not linked.')
        job=get_host().get_run(run_id)
        if job['status']!='succeeded': raise ValueError('Choose a completed successful run.')
        code=secrets.token_urlsafe(32)
        with self.bridge.db(True) as db:
            db.execute('DELETE FROM website_shares WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO website_shares VALUES (?,?,?,?,?)',(hashlib.sha256(code.encode()).hexdigest(),site,get_host().current_user().user_id,run_id,time.time()+600))
        return {'code':code,'expires_in':600}

    def redeem(self, site, code, target):
        digest=hashlib.sha256(str(code).encode()).hexdigest()
        with self.bridge.db() as db:
            row=db.execute('SELECT * FROM website_shares WHERE digest=? AND site_id=? AND owner=? AND expires>?',(digest,site,get_host().current_user().user_id,time.time())).fetchone()
        if not row: raise ValueError('Share expired or belongs to another account.')
        # Idempotent schedule, then consume the one-use share.
        value=self.schedule(site,row['run_id'],target)
        with self.bridge.db(True) as db: db.execute('DELETE FROM website_shares WHERE digest=?',(digest,))
        return value

    def pending(self, site):
        with self.bridge.db() as db:
            rows=db.execute("SELECT * FROM website_deliveries WHERE site_id=? AND state IN ('waiting','retry','delivering') AND retry_at<=? ORDER BY created_at",(site,time.time())).fetchall()
        items=[]
        for row in rows:
            if len(items)>=20: break
            with get_host().user_scope(row['owner']):
                try:
                    get_host().require_user(row['owner'])
                    job=get_host().get_run(row['run_id'])
                    if job['status'] in ('queued','running','pending_approval'): continue
                    if job['status']!='succeeded':
                        with self.bridge.db(True) as db: db.execute("UPDATE website_deliveries SET state='not_delivered',error=? WHERE id=?",('Run '+job['status'],row['id']))
                        continue
                    manifest=json.loads(row['manifest']) if row['manifest'] else self.manifest(row,job)
                    if not manifest['files']:
                        with self.bridge.db(True) as db: db.execute("UPDATE website_deliveries SET state='not_delivered',error=? WHERE id=?",('Run produced no output artifacts.',row['id']))
                        continue
                    lease=secrets.token_urlsafe(24)
                    with self.bridge.db(True) as db:
                        changed=db.execute("UPDATE website_deliveries SET state='delivering',manifest=?,attempts=attempts+1,retry_at=?,receipt=? WHERE id=? AND retry_at<=? AND state IN ('waiting','retry','delivering')",(json.dumps(manifest),time.time()+1800,lease,row['id'],time.time())).rowcount
                    if changed: items.append({**manifest,'lease':lease})
                except Exception as exc:
                    with self.bridge.db(True) as db: db.execute("UPDATE website_deliveries SET state='retry',error=?,retry_at=? WHERE id=?",(str(exc)[:500],time.time()+30,row['id']))
        return {'deliveries':items}

    def manifest(self, row, job):
        original=json.loads(row['baseline'])
        baseline={f.get('workspace_path') or f.get('path'):f for f in (original or [])}
        result=job.get('result') or {}
        explicit=set()
        for f in (result.get('evidence') or {}).get('files',[]) + result.get('artifacts',[]):
            path=f if isinstance(f,str) else f.get('workspace_path') or f.get('path')
            if path: explicit.add(path)
        files=[]
        for f in get_host().list_files(job['session_id']):
            path=f.get('workspace_path') or f.get('path','')
            if not path or path.startswith('uploads/'): continue
            if path not in explicit and (original is None or f==baseline.get(path)): continue
            files.append(f)
        return {'id':row['id'],'run_id':row['run_id'],'session_id':row['session_id'],'subject':row['subject'],
                'target':json.loads(row['target']),'answer':(job.get('result') or {}).get('answer',''), 'files':files,'created_at':row['created_at'],'completed_at':job.get('updated_at',row['created_at'])}

    def acknowledge(self, site, body):
        with self.bridge.db(True) as db:
            row=db.execute('SELECT * FROM website_deliveries WHERE id=? AND site_id=?',(body.get('id'),site)).fetchone()
            if not row or row['state']!='delivering' or not secrets.compare_digest(row['receipt'] or '',str(body.get('lease',''))):
                raise ValueError('Delivery lease is invalid or expired.')
            ok=body.get('ok') is True
            db.execute('UPDATE website_deliveries SET state=?,retry_at=?,error=?,receipt=? WHERE id=?',
                       ('delivered' if ok else 'retry',time.time()+min(3600,30*2**min(row['attempts'],6)),'' if ok else str(body.get('error','Delivery failed'))[:500],json.dumps(body.get('receipt',{})),row['id']))
        return {'state':'delivered' if ok else 'retry'}

    def artifact(self, site, delivery_id, path):
        with self.bridge.db() as db: row=db.execute('SELECT * FROM website_deliveries WHERE id=? AND site_id=?',(delivery_id,site)).fetchone()
        if not row or not row['manifest']: raise ValueError('Delivery not found.')
        if path not in {(f.get('workspace_path') or f.get('path')) for f in json.loads(row['manifest'])['files']}: raise ValueError('Artifact not in delivery.')
        return dict(row)

    def status(self, run_id):
        get_host().get_run(run_id)
        with self.bridge.db() as db:
            return {'deliveries':[{'id':r['id'],'site_id':r['site_id'],'state':r['state'],'target':json.loads(r['target']),'error':r['error']} for r in db.execute('SELECT * FROM website_deliveries WHERE run_id=? AND owner=?',(run_id,get_host().current_user().user_id))]}
