"""Generic backend connector API. Host credentials never reach browser/model code."""
import json
import os
import hashlib
import hmac
import re
from urllib.parse import parse_qs, urlparse

from .ports import get_host
from .identity import Federation
from .config import authenticate_client, text_id, signing_secret
from .bridge import get_bridge, issue_ticket, check_site
from .conversations import WebsiteAccounts


def handle_service(handler, path):
    if path.startswith('/website/download/') and handler.command == 'GET':
        accounts = WebsiteAccounts()
        row = accounts.consume_download(path.rsplit('/', 1)[-1])
        with get_host().user_scope(row['owner_user_id']):
            accounts.require(row['site_id'], row['session_id'])
            handler._website_download_name = row['path'].rsplit('/', 1)[-1]
            get_host().serve_file(handler, row['session_id'], row['path'])
        return True
    if not path.startswith('/website/service/'):
        return False
    site = handler.headers.get('X-Website-Site', '')
    header = handler.headers.get('Authorization', '')
    authenticate_client(site, header[7:] if header.startswith('Bearer ') else '')
    if handler.headers.get('Origin'):
        raise get_host().auth_error('Website service credentials are for backend requests only.')
    operation = path[len('/website/service/'):]
    body = handler._read_json() if handler.command == 'POST' else {}
    if operation in {'commands', 'command-ack', 'command-artifact', 'command-heartbeat'}:
        from .transfer.service import Transfers
        transfers = Transfers()
        if operation == 'commands' and handler.command == 'POST': result = transfers.pending(site, body.get("capabilities"), body.get("exclude_ids"))
        elif operation == 'command-heartbeat' and handler.command == 'POST': result = transfers.heartbeat(site, body)
        elif operation == 'command-ack' and handler.command == 'POST': result = transfers.acknowledge(site, body)
        elif operation == 'command-artifact' and handler.command == 'GET':
            query = parse_qs(urlparse(handler.path).query)
            file = (query.get('path') or [''])[0]
            row = transfers.artifact(site, (query.get('id') or [''])[0], file)
            with get_host().user_scope(row['owner']):
                get_host().serve_file(handler, row['session_id'], file)
            return True
        else: raise ValueError('Invalid transfer method.')
        handler._send_json(result)
        return True
    if operation in {'deliveries', 'delivery-ack', 'delivery-artifact'}:
        from .delivery import Deliveries
        delivery=Deliveries()
        if operation=='deliveries' and handler.command=='POST': result=delivery.pending(site)
        elif operation=='delivery-ack' and handler.command=='POST': result=delivery.acknowledge(site,body)
        elif operation=='delivery-artifact' and handler.command=='GET':
            query=parse_qs(urlparse(handler.path).query)
            file=(query.get('path') or [''])[0]
            row=delivery.artifact(site,(query.get('id') or [''])[0],file)
            with get_host().user_scope(row['owner']):
                get_host().require_user(row['owner'])
                get_host().serve_file(handler,row['session_id'],file)
            return True
        else: raise ValueError('Invalid delivery method.')
        handler._send_json(result)
        return True
    subject = text_id(body.get('subject') or handler.headers.get('X-Website-Subject'), 'external subject')
    principal = Federation().identity(site, subject, body.get('identity'))
    with get_host().user_scope(principal.user_id):
        accounts = WebsiteAccounts()
        if operation in {'bootstrap', 'ticket'} and handler.command == 'POST':
            origin = body.get('origin', '')
            check_site(site, origin)
            if operation == 'bootstrap':
                session = accounts.conversation(site, body.get('scope_key', 'workspace'))
                result = Federation().grant(site, origin, principal, session)
            else:
                secret = signing_secret(site)
                result = {'token': issue_ticket(secret, site_id=site, origin=origin, subject=principal.user_id)}
        elif operation == 'receive-share' and handler.command == 'POST':
            from .delivery import Deliveries
            result = Deliveries().redeem(site,body.get('code'),body.get('target') or {})
        elif operation == 'results' and handler.command == 'POST':
            result = accounts.results(site, body.get('scope_key', 'workspace'))
        elif operation == 'revoke' and handler.command == 'POST':
            Federation().revoke(site, principal)
            result = {'revoked': True}
        elif operation == 'artifact-ticket' and handler.command == 'POST':
            result = accounts.download_ticket(site, body.get('session_id', ''), body.get('path', ''))
        elif operation == 'artifact' and handler.command == 'GET':
            query = parse_qs(urlparse(handler.path).query)
            session_id = (query.get('session_id') or [''])[0]
            accounts.require(site, session_id)
            get_host().serve_file(handler, session_id, (query.get('path') or [''])[0])
            return True
        elif operation == 'uploads' and handler.command == 'POST':
            from .transfer.service import Transfers
            transfers = Transfers()
            command = body.get('command_id')
            if command: transfers.authorize_upload(site, command, body.get('session_id', ''))
            else: accounts.require(site, body.get('session_id', ''))
            resource = text_id(body.get('resource_id'), 'resource ID')
            revision = text_id(body.get('revision'), 'resource revision')
            with accounts.bridge.db(True) as db:
                previous = db.execute('SELECT * FROM website_imports WHERE session_id=? AND site_id=? AND resource_id=? AND revision=? ORDER BY rowid DESC LIMIT 1',
                                      (body['session_id'], site, resource, revision)).fetchone()
                uploads = get_host().uploads()
                result = None
                if previous:
                    try:
                        saved = uploads.status(previous['upload_id'])
                        if saved['size'] == int(body['size']) and saved['filename'] == body['filename']:
                            result = saved
                    except (ValueError, get_host().access_denied):
                        pass
                if result is None:
                    result = uploads.create(body['session_id'], body['filename'], body['size'])
                    db.execute('INSERT INTO website_imports VALUES (?,?,?,?,?,NULL)', (result['upload_id'], body['session_id'], site, resource, revision))
            if command: transfers.bind_upload(command, result['upload_id'])
        elif operation.startswith('uploads/'):
            parts = operation.split('/')
            identifier = parts[1]
            with accounts.bridge.db() as db:
                row = db.execute('SELECT * FROM website_imports WHERE upload_id=? AND site_id=?', (identifier, site)).fetchone()
            if not row:
                raise get_host().access_denied('Upload not found.')
            from .transfer.service import Transfers
            transfers = Transfers()
            command = transfers.upload_command(identifier)
            if command: transfers.authorize_upload(site, command, row['session_id'])
            else: accounts.require(site, row['session_id'])
            uploads = get_host().uploads()
            if len(parts) == 2 and handler.command == 'PATCH':
                result = uploads.append(identifier, int(handler.headers.get('Upload-Offset', '-1')), handler.rfile, int(handler.headers.get('Content-Length', '0')))
            elif parts[2:] == ['complete'] and handler.command == 'POST':
                expected = body.get('sha256')
                if expected is not None:
                    if not isinstance(expected, str) or not re.fullmatch('[a-fA-F0-9]{64}', expected):
                        raise ValueError('Invalid transfer checksum.')
                    with uploads.locked(identifier) as (folder, saved):
                        if saved.get('file'):
                            actual = saved['file']['sha256']
                        else:
                            with (folder / 'data').open('rb') as stream:
                                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                        if not hmac.compare_digest(actual, expected.lower()):
                            raise ValueError('Transfer checksum mismatch.')
                result = uploads.complete(identifier)
                with accounts.bridge.db(True) as db:
                    db.execute('UPDATE website_imports SET file=? WHERE upload_id=?', (json.dumps(result), identifier))
            elif parts[2:] == ['cancel'] and handler.command == 'POST':
                uploads.cancel(identifier)
                result = {'cancelled': True}
            else:
                raise ValueError('Unknown upload operation.')
        else:
            raise ValueError('Unknown website service operation.')
        handler._send_json(result)
    return True


def new_conversation(binding_id, token):
    row = get_bridge()._binding(binding_id, token)
    accounts = WebsiteAccounts()
    link = accounts.require(row['site_id'], row['session_id'])
    return {'session_id': accounts.conversation(row['site_id'], link['scope_key'], new=True)}


def handle_browser(handler, operation: str) -> None:
    """Authenticate and proxy the small browser-to-host website protocol."""
    try:
        payload = handler._read_json()
        bridge = get_bridge()
        if operation in {'sites','share','delivery-status'}:
            from .delivery import Deliveries
            delivery=Deliveries()
            run_id=str(payload.get('run_id',''))
            if operation!='sites' and not run_id:
                jobs=get_host().list_runs(str(payload.get('session_id','')))
                run_id=next((j['run_id'] for j in jobs if ((j.get('result') or {}).get('run') or {}).get('run_id')==payload.get('internal_run_id')), '')
                if not run_id: raise ValueError('Completed run not found.')
            if operation=='sites': result={'sites':delivery.sites()}
            elif operation=='share': result=delivery.share(str(payload.get('site_id','')),run_id)
            else: result=delivery.status(run_id)
            handler._send_json(result)
            return
        if operation == 'artifact-ticket':
            handler._send_json(WebsiteAccounts().download_ticket(str(payload.get('site_id', '')), str(payload.get('session_id', '')), str(payload.get('path', ''))))
            return
        if operation == 'conversation':
            handler._send_json(new_conversation(str(payload.get('binding_id', '')), str(payload.get('token', ''))))
            return
        if operation == "demo-token":
            site_id = str(payload.get("site_id", "")).strip()
            origin = str(handler.headers.get("Origin") or "").strip()
            if site_id != "assistant-demo" or not origin:
                raise ValueError("assistant-demo token requires the configured browser origin")
            if urlparse(origin).netloc != handler.headers.get("Host"):
                raise ValueError("Demo tickets are only issued to this server's own host page.")
            check_site(site_id, origin)
            secret = os.getenv("AGENT_WEBSITE_SECRET", "")
            if len(secret) < 32:
                raise ValueError("AGENT_WEBSITE_SECRET must be configured with at least 32 characters")
            result = {"token": issue_ticket(secret, site_id=site_id, origin=origin, subject=get_host().current_user().user_id)}
        elif operation == "connect":
            result = bridge.connect(
                ticket=str(payload.get("ticket", "")), site_id=str(payload.get("site_id", "")),
                origin=str(payload.get("origin", "")), instance_id=str(payload.get("instance_id", "")),
                session_id=str(payload.get("session_id", "")), context=payload.get("context") or {},
                capabilities=[str(x) for x in payload.get("capabilities", [])],
            )
        elif operation == "context":
            result = bridge.context(str(payload.get("binding_id", "")), str(payload.get("token", "")), payload.get("context") or {})
        elif operation == "poll":
            result = {"requests": bridge.pending(str(payload.get("binding_id", "")), str(payload.get("token", "")))}
        elif operation == "respond":
            result = bridge.respond(
                str(payload.get("binding_id", "")), str(payload.get("token", "")), str(payload.get("call_id", "")),
                result=payload.get("result"), error=payload.get("error"), revision=str(payload.get("revision", "")),
            )
        elif operation == "disconnect":
            bridge.disconnect(str(payload.get("binding_id", "")), str(payload.get("token", "")))
            result = {"disconnected": True}
        else:
            handler._send_json({"error": "not found"}, status=404)
            return
        handler._send_json(result)
    except get_host().auth_error:
        raise
    except Exception as exc:
        handler._send_json({"error": str(exc), "error_type": type(exc).__name__}, status=400)



def handle_exchange(handler, path):
    if path != '/auth/website/exchange' or handler.command != 'POST':
        return False
    payload = handler._read_json()
    token, result = Federation().exchange(payload.get('code'), payload.get('site_id'), payload.get('origin'))
    if payload.get('credential_mode') == 'bearer':
        result['access_token'] = token
    else:
        handler._auth_cookie = get_host().login_cookie(token)
    handler._send_json(result)
    return True


def handle_public(handler, path):
    return handle_service(handler, path) or handle_exchange(handler, path)
