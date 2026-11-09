"""Server-to-server website identities and single-use browser login grants."""
from __future__ import annotations

import hashlib
import os
import secrets
import time
from uuid import uuid4

from .ports import get_host
from .config import clients, text_id, check_site


class Federation:
    def __init__(self):
        with get_host().identity_transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS external_identities (site_id TEXT, subject TEXT, user_id TEXT NOT NULL, PRIMARY KEY(site_id,subject))')
            db.execute('CREATE TABLE IF NOT EXISTS website_grants (digest TEXT PRIMARY KEY, site_id TEXT, origin TEXT, user_id TEXT, session_id TEXT, expires REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS website_logins (digest TEXT PRIMARY KEY, site_id TEXT, user_id TEXT)')

    def identity(self, site_id, subject, identity=None):
        text_id(subject, 'external subject')
        shared_user_id = clients().get(site_id, {}).get('identity_mode') == 'shared_user_id'
        username = None
        if identity is not None:
            if not isinstance(identity, dict) or identity.get('user_id') != subject:
                raise ValueError('Website identity does not match the authenticated subject.')
            username = text_id(identity.get('username'), 'external username')
        with get_host().identity_transaction() as db:
            mapping = db.execute('SELECT user_id FROM external_identities WHERE site_id=? AND subject=?', (site_id, subject)).fetchone()
            row = db.user(mapping['user_id']) if mapping else None
            if shared_user_id and not mapping and identity is None:
                raise ValueError('Shared website identities require a verified user_id and username.')
            if row:
                if row['disabled']:
                    raise get_host().auth_error('This account is disabled.')
                if username and row['username'] != username:
                    sync = getattr(db, 'sync_username', None)
                    if sync:
                        sync(row['user_id'], username)
                return get_host().principal(row['user_id'], username or row['username'])
            identifier = subject if shared_user_id else uuid4().hex
            row = db.user(identifier)
            if row:
                if row['disabled']:
                    raise get_host().auth_error('This account is disabled.')
            else:
                account_name = username if shared_user_id and username else 'website_' + identifier
                db.create_user(identifier, account_name)
                row = {'user_id': identifier, 'username': account_name, 'disabled': 0}
            db.execute(
                'INSERT INTO external_identities VALUES (?,?,?) '
                'ON CONFLICT(site_id,subject) DO UPDATE SET user_id=excluded.user_id',
                (site_id, subject, identifier),
            )
            return get_host().principal(row['user_id'], row['username'])

    def link(self, site_id, subject, username):
        if site_id not in clients():
            raise ValueError('Configure the website client first.')
        text_id(subject, 'external subject')
        with get_host().identity_transaction() as db:
            principal = db.named_user(username)
            row = db.execute('SELECT user_id FROM external_identities WHERE site_id=? AND subject=?', (site_id, subject)).fetchone()
            if row and row['user_id'] != principal.user_id:
                raise ValueError('Identity already linked; automatic reassignment is not supported.')
            db.execute('INSERT OR IGNORE INTO external_identities VALUES (?,?,?)', (site_id, subject, principal.user_id))

    def grant(self, site_id, origin, principal, session_id):
        check_site(site_id, origin)
        code = secrets.token_urlsafe(32)
        with get_host().identity_transaction() as db:
            db.execute('DELETE FROM website_grants WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO website_grants VALUES (?,?,?,?,?,?)',
                       (hashlib.sha256(code.encode()).hexdigest(), site_id, origin, principal.user_id, session_id, time.time() + 60))
        return {'code': code, 'site_id': site_id, 'origin': origin, 'expires_in': 60}

    def exchange(self, code, site_id, origin):
        check_site(site_id, origin)
        if not isinstance(code, str) or len(code) > 256:
            raise get_host().auth_error('Invalid website login grant.')
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(code.encode()).hexdigest()
        with get_host().identity_transaction() as db:
            row = db.execute('SELECT * FROM website_grants WHERE digest=?', (digest,)).fetchone()
            user = db.user(row['user_id']) if row else None
            if not row or row['expires'] < time.time() or row['site_id'] != site_id or row['origin'] != origin or not user or user['disabled']:
                raise get_host().auth_error('Invalid, expired, or consumed website login grant.')
            db.execute('DELETE FROM website_grants WHERE digest=?', (digest,))
            ttl = max(30, min(int(os.getenv('AGENT_WEBSITE_LOGIN_TTL_SECONDS', '120')), 300))
            db.create_login(hashlib.sha256(token.encode()).hexdigest(), row['user_id'], time.time() + ttl)
            db.execute('INSERT INTO website_logins VALUES (?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), site_id, row['user_id']))
            return token, {
                'user': {'id': row['user_id'], 'name': user['username']},
                'session_id': row['session_id'], 'site_id': site_id, 'expires_in': ttl,
            }

    def revoke(self, site_id, principal):
        with get_host().identity_transaction() as db:
            for login in db.execute('SELECT digest FROM website_logins WHERE site_id=? AND user_id=?', (site_id, principal.user_id)).fetchall():
                db.revoke_login(login['digest'])
            db.execute('DELETE FROM website_logins WHERE site_id=? AND user_id=?', (site_id, principal.user_id))
            db.execute('DELETE FROM website_grants WHERE site_id=? AND user_id=?', (site_id, principal.user_id))
        from .conversations import WebsiteAccounts
        with WebsiteAccounts().bridge.db(True) as db:
            db.execute('UPDATE bindings SET revoked=1 WHERE site_id=? AND owner_user_id=?', (site_id, principal.user_id))
            db.execute('DELETE FROM website_downloads WHERE site_id=? AND owner_user_id=?', (site_id, principal.user_id))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Explicitly link a trusted website identity to an existing BioAgent account.')
    parser.add_argument('site_id'); parser.add_argument('subject'); parser.add_argument('username')
    args = parser.parse_args()
    Federation().link(args.site_id, args.subject, args.username)
    print('Website identity linked.')
