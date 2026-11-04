"""Exercise the built MSCAN adapter's Spring logout event without modifying its dependencies."""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile
import zipfile


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar', type=Path, default=root / 'resource/mscan/mscan-app/mscan-admin/target/mscan-admin.jar')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        with zipfile.ZipFile(args.jar) as jar:
            for name in jar.namelist():
                if name.startswith(('BOOT-INF/lib/', 'BOOT-INF/classes/')):
                    jar.extract(name, directory)
        classpath = os.pathsep.join([str(directory), str(directory/'BOOT-INF/classes'), str(directory/'BOOT-INF/lib/*')])
        subprocess.run(['javac', '-cp', classpath, '-d', str(directory), str(root/'web_bridge/adapters/mscan/tests/LogoutProbe.java')], check=True)
        subprocess.run(['java', '-cp', classpath, 'LogoutProbe'], check=True)


if __name__ == '__main__': main()
