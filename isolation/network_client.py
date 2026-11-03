"""Small pipe client installed only in registered public retrieval workers."""
from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import urlencode, urljoin

from .protocol import MAX_WIRE


def install(module, name: str, reader, writer):
    def request(url):
        writer.write(json.dumps({'network_request': url}).encode() + b'\n')
        writer.flush()
        line = reader.readline(MAX_WIRE + 1)
        if len(line) > MAX_WIRE:
            raise ValueError('Broker response exceeds its limit.')
        reply = json.loads(line)
        if 'error' in reply:
            raise ValueError(reply['error'])
        reply['body'] = base64.b64decode(reply['body'], validate=True)
        return reply

    async def search(url, params):
        reply = await asyncio.to_thread(request, url + '?' + urlencode(params))
        body = reply['body'].decode('utf-8', errors='replace')
        if name == 'web_search' and (reply['status'] == 202 or 'challenge-form' in body.lower()):
            raise ValueError('Search provider requires browser verification. Use web_fetch with a known public URL or pubmed_search.')
        if not 200 <= reply['status'] < 300:
            raise ValueError(f"Search endpoint returned HTTP {reply['status']}.")
        return body

    async def page(url):
        for attempt in range(4):
            reply = await asyncio.to_thread(request, url)
            if 300 <= reply['status'] < 400:
                target = reply['headers'].get('Location')
                if not target or attempt == 3:
                    raise ValueError('Web source exceeded three redirects or has no redirect target.')
                url = urljoin(url, target)
                continue
            if not 200 <= reply['status'] < 300:
                raise ValueError(f"Web source returned HTTP {reply['status']}.")
            kind = reply['headers'].get('Content-Type', '').lower()
            if not any(value in kind for value in ('text/html', 'text/plain', 'application/xhtml+xml')):
                raise ValueError('Web source is not HTML or text.')
            if len(reply['body']) > 1_500_000:
                raise ValueError('Web source exceeds 1.5 MB.')
            return url, reply['body'].decode('utf-8', errors='replace')
        raise ValueError('Web source could not be fetched.')

    from .provider_policy import PROVIDER_TOOLS
    if name in PROVIDER_TOOLS:
        import requests

        def provider_request(session, method, url, params=None, data=None, json=None, **kwargs):
            # PreparedRequest handles the provider's query/form encoding. Ambient
            # headers, cookies, proxies and authentication never cross the pipe.
            prepared = requests.Request(method.upper(), url, params=params, data=data, json=json).prepare()
            body = prepared.body
            if isinstance(body, bytes):
                body = body.decode('utf-8')
            for attempt in range(4):
                reply = request({'url': prepared.url, 'method': prepared.method, 'body': body,
                                 'content_type': prepared.headers.get('Content-Type', '')})
                if 300 <= reply['status'] < 400:
                    if prepared.method != 'GET' or attempt == 3 or not reply['headers'].get('Location'):
                        raise ValueError('Provider redirect cannot be followed.')
                    prepared.url = urljoin(prepared.url, reply['headers']['Location'])
                    continue  # Each redirect is independently validated by the broker.
                response = requests.Response()
                response.status_code, response.url = reply['status'], prepared.url
                response.headers.update(reply['headers'])
                response._content, response._content_consumed = reply['body'], True
                response.encoding = 'utf-8'
                return response
            raise ValueError('Provider redirect limit exceeded.')

        requests.sessions.Session.request = provider_request
    elif name == 'pdb_download':
        # This provider's synchronous transport normally uses requests. Replace
        # it inside this disposable worker; every URL is checked by the host
        # broker and the container retains --network=none.
        from tools.infrastructure.providers.pdb import client
        import requests

        def structure_request(method, url, **kwargs):
            if method != 'GET':
                raise ValueError('PDB retrieval permits GET only.')
            reply = request(url)
            if not 200 <= reply['status'] < 300:
                raise ValueError(f"PDB download returned HTTP {reply['status']}.")
            response = requests.Response()
            response.status_code = reply['status']
            response.url = url
            response.headers.update(reply['headers'])
            response._content = reply['body']
            return response

        client.request_http = structure_request
    elif name == 'web_fetch':
        module._fetch = page
    else:
        module.request = search
