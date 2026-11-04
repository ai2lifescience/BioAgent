"""Configure and run the reference adapter without putting service secrets in shell history."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import sys


def main():
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=['init', 'agent', 'backend', 'frontend'])
    parser.add_argument('--config', type=Path, default=root / 'runtime/website-integration/clients.json')
    parser.add_argument('--mscan-root', type=Path, default=root / 'resource/mscan')
    parser.add_argument('--origins', default='http://localhost:8848,http://127.0.0.1:8848',
                        help='Comma-separated exact MSCAN browser origins (init only).')
    parser.add_argument('--agent-url', default='http://127.0.0.1:8000', help='Agent backend URL reachable by MSCAN.')
    parser.add_argument('--public-url', default='', help='Agent browser URL; default uses the MSCAN browser hostname on port 8000.')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--enable-scheduler', action='store_true', help='Enable MSCAN background workflow polling.')
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
        clients = json.loads(config.read_text()) if config.exists() else {}
        client = clients.setdefault('mscan', {})
        client.setdefault('secret', secrets.token_urlsafe(48))
        client.setdefault('signing_secret', secrets.token_urlsafe(48))
        client['origins'] = origins
        temporary = config.with_suffix('.tmp')
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w') as stream:
            json.dump(clients, stream, indent=2)
        temporary.chmod(0o600)
        os.replace(temporary, config)
        print(f'Configured {config}; existing keys preserved. No credentials printed.')
        return
    if not config.exists(): parser.error('Run the init command first.')
    client = json.loads(config.read_text())['mscan']
    env = os.environ.copy()
    mscan = args.mscan_root.resolve()
    if args.component == 'agent':
        env['AGENT_WEBSITE_CLIENTS_FILE'] = str(config)
        env.pop('AGENT_WEBSITE_CLIENTS', None)
        command = [sys.executable, '-B', '-m', 'interfaces.web', '--host', args.host, '--port', str(args.port)]
        directory = root
    elif args.component == 'backend':
        env.setdefault('BIOAGENT_RESULTS_ROOT', str(root / 'runtime/website-integration/mscan-results'))
        env.update(BIOAGENT_ENABLED='true', BIOAGENT_URL=args.agent_url, BIOAGENT_SECRET=client['secret'],
                   BIOAGENT_ORIGINS=','.join(client['origins']), BIOAGENT_PUBLIC_URL=args.public_url)
        directory = mscan / 'mscan-app'
        jar = directory / 'mscan-admin/target/mscan-admin.jar'
        if not jar.exists(): parser.error('Build MSCAN with Maven first; see web_bridge/adapters/mscan/README.md.')
        command = ['java', '-jar', str(jar), '--spring.profiles.active=druid',
                   '--scheduled.cromwellPoll.enabled=' + str(args.enable_scheduler).lower()]
    else:
        directory = mscan / 'mscan'
        command = ['pnpm', 'dev', '--host', args.host]
    if not shutil.which(command[0]): parser.error(f'{command[0]} is not on PATH. Activate your development environment first.')
    os.chdir(directory)
    os.execvpe(command[0], command, env)


if __name__ == '__main__':
    main()
