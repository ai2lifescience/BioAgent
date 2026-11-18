"""Configure BioAgent's MSCAN client or start the BioAgent web server."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=['init', 'agent'])
    parser.add_argument('--config', type=Path, default=root / 'runtime/website-integration/clients.json')
    parser.add_argument('--origins', default='http://localhost:8848,http://127.0.0.1:8848',
                        help='Comma-separated exact MSCAN browser origins (init only).')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    config = args.config.resolve()
    if args.component == 'init':
        from urllib.parse import urlsplit
        origins = [value.strip() for value in args.origins.split(',') if value.strip()]
        for origin in origins:
            url = urlsplit(origin)
            if url.scheme not in ('http', 'https') or not url.netloc or url.path or url.query or url.fragment or url.username:
                parser.error('Origins must be exact HTTP(S) origins without paths or credentials.')
        if not origins: parser.error('At least one origin is required.')
        config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        clients = json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        client = clients.setdefault('mscan', {})
        client.setdefault('secret', secrets.token_urlsafe(48))
        client.setdefault('signing_secret', secrets.token_urlsafe(48))
        client['identity_mode'] = 'shared_user_id'
        client['origins'] = origins
        temporary = config.with_suffix('.tmp')
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
            json.dump(clients, stream, indent=2)
        temporary.chmod(0o600)
        os.replace(temporary, config)
        print(f'Configured {config}; existing keys preserved. No credentials printed.')
        return
    if not config.exists(): parser.error('Run the init command first.')
    env = os.environ.copy()
    env['AGENT_WEBSITE_CLIENTS_FILE'] = str(config)
    env.pop('AGENT_WEBSITE_CLIENTS', None)
    command = [sys.executable, '-B', '-m', 'interfaces.web', '--host', args.host, '--port', str(args.port)]
    os.chdir(root)
    os.execvpe(command[0], command, env)


if __name__ == '__main__':
    main()
