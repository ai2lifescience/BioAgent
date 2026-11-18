"""Exercise the MSCAN-owned Spring logout check against the built backend."""
from pathlib import Path
import argparse
import os
import subprocess
import tempfile
import zipfile


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mscan-root', type=Path, default=root.parent / 'mscan-app')
    args = parser.parse_args()
    jar_path = args.mscan_root / 'mscan-admin/target/mscan-admin.jar'
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        with zipfile.ZipFile(jar_path) as jar:
            for name in jar.namelist():
                if name.startswith(('BOOT-INF/lib/', 'BOOT-INF/classes/')):
                    jar.extract(name, directory)
        classpath = os.pathsep.join([str(directory), str(directory/'BOOT-INF/classes'), str(directory/'BOOT-INF/lib/*')])
        test = args.mscan_root / 'mscan-admin/src/test/java/com/mscan/web/controller/common/LogoutProbe.java'
        subprocess.run(['javac', '-cp', classpath, '-d', str(directory), str(test)], check=True)
        subprocess.run(['java', '-cp', classpath, 'com.mscan.web.controller.common.LogoutProbe'], check=True)


if __name__ == '__main__': main()
