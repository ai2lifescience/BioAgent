"""Website registration, exact origins and server-only credentials."""
import json
import os
import hmac
import secrets
import socket
from pathlib import Path
from .ports import get_host

def clients() -> dict:
    raw = os.getenv('AGENT_WEBSITE_CLIENTS')
    if raw is None and os.getenv('AGENT_WEBSITE_CLIENTS_FILE'):
        raw = Path(os.environ['AGENT_WEBSITE_CLIENTS_FILE']).read_text()
    value = json.loads(raw or '{}')
    if not isinstance(value, dict):
        raise ValueError('AGENT_WEBSITE_CLIENTS must be an object.')
    return value


def signing_secret(site_id):
    value = clients().get(site_id, {}).get('signing_secret') or os.getenv('AGENT_WEBSITE_SECRET', '')
    if not isinstance(value, str) or len(value) < 32:
        raise ValueError('Configure a website signing secret of at least 32 characters.')
    return value


def authenticate_client(site_id: str, credential: str) -> dict:
    config = clients().get(site_id, {})
    secret = config.get('secret', '')
    if not isinstance(secret, str) or len(secret) < 32 or not hmac.compare_digest(secret, credential):
        raise get_host().auth_error('Invalid website client credentials.')
    return config


def text_id(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200 or any(ord(c) < 32 for c in value):
        raise ValueError(f'Invalid {name}.')
    return value


def allowed_sites() -> dict[str, list[str]]:
    try:
        raw = json.loads(os.getenv("AGENT_WEBSITE_SITES", "{}"))
        if 'AGENT_WEBSITE_SITES' in os.environ and raw == {}:
            return {}
        raw = {**{site: config.get('origins', []) for site, config in clients().items()}, **raw}
        return {str(site): [str(origin) for origin in origins] for site, origins in raw.items() if isinstance(origins, list)}
    except json.JSONDecodeError as exc:
        raise ValueError("AGENT_WEBSITE_SITES must be a JSON object") from exc


def check_site(site_id: str, origin: str) -> None:
    if origin not in allowed_sites().get(site_id, []):
        raise ValueError(f"Website origin {origin!r} is not configured for {site_id!r} in AGENT_WEBSITE_SITES.")


def configure_local_demo(port: int, host: str = "127.0.0.1") -> None:
    """Trust the demo's listening addresses; never widen explicit settings.

    The generated signing secret is process-local and inherited by detached
    workers. Real external websites still configure their shared secret and
    origins explicitly. A fresh server invalidates unconsumed demo tickets.
    """
    if "AGENT_WEBSITE_SITES" not in os.environ:
        hosts = {"localhost", "127.0.0.1"}
        if host == "0.0.0.0":
            # Resolve this machine's addresses, not the browser's Host header.
            # The wildcard listen address itself is not a browser origin.
            try:
                addresses = socket.getaddrinfo(socket.gethostname(), port, socket.AF_INET, socket.SOCK_STREAM)
                hosts.update(address[4][0] for address in addresses if address[4][0] != "0.0.0.0")
            except OSError:
                pass  # Explicit AGENT_WEBSITE_SITES also supports unresolved hosts/proxies.
        else:
            hosts.add(host)
        os.environ["AGENT_WEBSITE_SITES"] = json.dumps({"assistant-demo": [
            f"http://{address}:{port}" for address in sorted(hosts)
        ]})
    os.environ.setdefault("AGENT_WEBSITE_SECRET", secrets.token_urlsafe(48))
