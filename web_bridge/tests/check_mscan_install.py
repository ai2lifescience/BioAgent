"""Verify the MSCAN installer against original ZIPs without touching the running checkout."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile


def main():
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archives', type=Path, default=repo / 'resource')
    parser.add_argument('--destination', type=Path, help='Keep an installed clean checkout for build checks; must not exist')
    args = parser.parse_args()
    temporary = None if args.destination else tempfile.TemporaryDirectory(prefix='mscan-clean-install-')
    root = args.destination.resolve() if args.destination else Path(temporary.name) / 'mscan'
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    try:
        baseline = {}
        for name in ('mscan', 'mscan-app'):
            with zipfile.ZipFile(args.archives / (name + '.zip')) as archive:
                for entry in archive.infolist():
                    if entry.is_dir():
                        continue
                    relative = Path(entry.filename)
                    if relative.is_absolute() or '..' in relative.parts:
                        raise ValueError('Unsafe archive member')
                    if relative.parts[0] == name:
                        relative = Path(*relative.parts[1:])
                    path = root / name / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    content = archive.read(entry)
                    path.write_bytes(content)
                    baseline[path.relative_to(root)] = content
        command = [sys.executable, str(repo / 'web_bridge/adapters/mscan/install.py'), str(root)]
        subprocess.run(command, check=True)
        changed = {str(path) for path, content in baseline.items() if (root / path).read_bytes() != content}
        expected = {'mscan/src/App.vue', 'mscan/src/views/sampleProgramResults/index.vue'}
        assert changed == expected, f'Unexpected original-file changes: {changed}'
        installed = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
        source = repo / 'web_bridge/adapters/mscan'
        for feature in ('connection', 'data_transfer', 'result_importers', 'resources'):
            for java in (source / feature).glob('*.java'):
                assert (root / 'mscan-app/mscan-admin/src/main/java/com/mscan/web/controller/common' / java.name).read_bytes() == java.read_bytes()
        subprocess.run(command, check=True)
        assert installed == {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}, 'Reinstallation changed files'
        print('PASS clean ZIP installation: exactly two original files modified, original line endings preserved, repeat installation identical')
        if args.destination:
            print('Clean installed checkout:', root)
    finally:
        if temporary:
            temporary.cleanup()


if __name__ == '__main__':
    main()
