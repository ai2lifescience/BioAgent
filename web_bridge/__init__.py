"""Public integration hooks for the independent web bridge module.

Protocol, identity and storage details are private to this package. Account and
workspace operations are supplied by the host adapter configured through ports.
"""
from .bridge import get_bridge, LEGACY_RUN_PREFIX
from .config import configure_local_demo as configure_local_demo
from .ports import configure_host as configure_host


def handle_public(handler, path):
    from .http import handle_public as handle
    return handle(handler, path)


def handle_browser(handler, operation):
    from .http import handle_browser as handle
    return handle(handler, operation)


def response_headers(handler):
    from urllib.parse import quote
    name = getattr(handler, '_website_download_name', None)
    return {'Content-Disposition': "attachment; filename*=UTF-8''" + quote(name, safe=''),
            'Referrer-Policy': 'no-referrer'} if name else {}


def revoke_user(user_id):
    get_bridge().revoke_user(user_id)


def record_run(run_id, session_id, binding):
    from .conversations import WebsiteAccounts
    WebsiteAccounts().record_run(run_id, session_id, binding)


def clean_user_message(text):
    return text.removeprefix(LEGACY_RUN_PREFIX)


def run_instructions(binding):
    return '\n' + LEGACY_RUN_PREFIX.split('\n\nUser request:')[0] if binding else ''
