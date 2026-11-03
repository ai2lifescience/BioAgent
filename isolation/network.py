"""Credential-free public HTTP broker for isolated evidence tools.

Resolve once, reject every non-global address, and connect to that exact IP.
Redirects return to the broker for validation; environment proxies and cookies
are never inherited. An operator's AGENT_PROXY may transport the pinned IP.
"""
from __future__ import annotations

import http.client
import ipaddress
import base64
import json
import os
import re
import socket
import ssl
from urllib.parse import urlsplit, urlencode

MAX_BYTES = 4 * 1024 * 1024
from .provider_policy import PROVIDER_TOOLS, validate as validate_provider
NETWORK_TOOLS = frozenset({'web_fetch', 'web_search', 'pubmed_search', 'pdb_download'}) | PROVIDER_TOOLS


def _proxy():
    if os.getenv('AGENT_DISABLE_PROXY', '').lower() in {'1', 'true', 'yes'}:
        return ''
    return os.getenv('AGENT_PROXY', '')


def _addresses(host, port):
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        pass
    # Proxy deployments may have a filtered local DNS resolver. Resolve through
    # TLS-authenticated DNS, then still validate and pin the resulting addresses.
    mode = os.getenv('AGENT_PUBLIC_DNS', 'google' if _proxy() else 'system')
    if mode == 'system':
        return [item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
    if mode != 'google':
        raise ValueError('AGENT_PUBLIC_DNS must be system or google.')
    url = urlsplit('https://dns.google/resolve?' + urlencode({'name': host, 'type': 'A'}))
    reply = _exchange(url, 'dns.google', 443, '8.8.8.8')
    if reply['status'] != 200:
        raise ValueError('Public DNS lookup failed.')
    payload = json.loads(base64.b64decode(reply['body']))
    return [item['data'] for item in payload.get('Answer', []) if item.get('type') == 1]


def destination(url: str):
    if not isinstance(url, str) or len(url) > 12000 or any(ord(c) < 33 for c in url):
        raise ValueError('Invalid public URL.')
    parsed = urlsplit(url)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or '%' in parsed.hostname):
        raise ValueError('Only public HTTP(S) URLs without credentials are allowed.')
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if port not in {80, 443}:
        raise ValueError('Public retrieval supports ports 80 and 443 only.')
    host = parsed.hostname.encode('idna').decode('ascii')
    addresses = _addresses(host, port)
    def permitted(address):
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            return False
        if ip.version == 6:
            return (ip in ipaddress.ip_network('2000::/3') and not ip.sixtofour
                    and not ip.teredo and not ip.ipv4_mapped)
        return True
    if not addresses or not all(permitted(address) for address in addresses):
        raise ValueError('Private and special-purpose addresses are not permitted.')
    return parsed, host, port, addresses[0]


def fetch(url: str | dict, tool: str) -> dict:
    if tool not in NETWORK_TOOLS:
        raise ValueError('This tool has no network capability.')
    method, body, content_type = 'GET', None, ''
    if isinstance(url, dict):
        if tool not in PROVIDER_TOOLS or set(url) - {'url', 'method', 'body', 'content_type'}:
            raise ValueError('Invalid provider request.')
        method, body, content_type = url.get('method', 'GET'), url.get('body'), url.get('content_type', '')
        url = url.get('url')
        if method not in {'GET', 'POST'} or (body is not None and (not isinstance(body, str) or len(body.encode()) > 128 * 1024)):
            raise ValueError('Provider request exceeds its method or body limit.')
        if method == 'GET' and body is not None:
            raise ValueError('GET requests cannot carry a body.')
    parsed, host, port, address = destination(url)
    if tool in PROVIDER_TOOLS:
        validate_provider(tool, parsed, method, body, content_type)
    if tool == 'pdb_download' and (parsed.scheme != 'https' or port != 443 or host != 'files.rcsb.org'
            or not re.fullmatch(r'/download/[A-Z0-9]{4}\.(?:cif|pdb|bcif)', parsed.path)
            or parsed.query):
        raise ValueError('PDB retrieval permits only RCSB structure download URLs.')
    if tool == 'web_search' and (host != 'html.duckduckgo.com' or parsed.path != '/html/'):
        raise ValueError('Search endpoint is not permitted.')
    if tool == 'pubmed_search' and (host != 'eutils.ncbi.nlm.nih.gov'
            or parsed.path not in {'/entrez/eutils/esearch.fcgi', '/entrez/eutils/efetch.fcgi'}):
        raise ValueError('Literature endpoint is not permitted.')
    if method == 'POST':
        return _exchange(parsed, host, port, address, method=method, body=body, content_type=content_type)
    return _exchange(parsed, host, port, address)


def _exchange(parsed, host, port, address, *, method='GET', body=None, content_type=''):
    sock = None
    connection = http.client.HTTPConnection(host, port, timeout=20)
    try:
        proxy = _proxy()
        if proxy:
            import socks
            gateway = urlsplit(proxy)
            if gateway.scheme not in {'socks', 'socks5', 'socks5h'} or not gateway.hostname:
                raise ValueError('Public retrieval requires a SOCKS5 AGENT_PROXY or a direct connection.')
            sock = socks.create_connection((address, port), timeout=20, proxy_type=socks.SOCKS5,
                proxy_addr=gateway.hostname, proxy_port=gateway.port or 1080, proxy_rdns=False,
                proxy_username=gateway.username, proxy_password=gateway.password)
        else:
            sock = socket.create_connection((address, port), timeout=20)
        if parsed.scheme == 'https':
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        connection.sock = sock
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        headers = {'User-Agent': 'Pipeline2Agent/1.0', 'Accept-Encoding': 'identity', 'Connection': 'close'}
        if host == 'www.ebi.ac.uk' and parsed.path.startswith('/QuickGO/services/'):
            headers['Accept'] = 'application/json'
        if body is not None:
            headers['Content-Type'] = content_type
        connection.request(method, path, body=body.encode() if body is not None else None, headers=headers)
        response = connection.getresponse()
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Public response exceeds 4 MiB.')
        if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
            raise ValueError('Compressed public responses are not supported.')
        # No Set-Cookie, authentication headers, or other ambient capabilities.
        return {'status': response.status, 'headers': {key: response.getheader(key, '')
                for key in ('Content-Type', 'Location')}, 'body': base64.b64encode(data).decode('ascii')}
    finally:
        connection.close()
        if sock is not None:
            sock.close()
