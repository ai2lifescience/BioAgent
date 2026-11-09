"""Run MSCAN-owned boundary checks against a built mscan-app checkout."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile


def main():
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=repo.parent / 'mscan-app')
    args = parser.parse_args()
    root = args.root.resolve()
    archive = root / 'mscan-admin/target/mscan-admin.jar'
    if not archive.is_file():
        parser.error('Build MSCAN with mvn package before running this check.')
    with tempfile.TemporaryDirectory(prefix='mscan-adapter-check-') as temp:
        directory = Path(temp)
        dependencies = directory / 'lib'
        dependencies.mkdir()
        classes = directory / 'classes'
        classes.mkdir()
        with zipfile.ZipFile(archive) as jar:
            for name in jar.namelist():
                if name.startswith('BOOT-INF/lib/') and name.endswith('.jar') and not Path(name).name.startswith('mscan-'):
                    with jar.open(name) as source, (dependencies / Path(name).name).open('wb') as target:
                        shutil.copyfileobj(source, target)
        classpath = ':'.join([str(p) for p in root.glob('*/target/classes')] + [str(dependencies / '*')])
        tests = root / 'mscan-admin/src/test/java/com/mscan/web/controller/common'
        subprocess.run(['javac', '-cp', classpath, '-d', str(classes), *[str(tests / (name + '.java')) for name in ('NativeFilesBoundaryCheck', 'QcImportFormatCheck', 'ResultImportCheck', 'ResultArtifactCheck', 'DownloadSecurityCheck', 'TransferConcurrencyCheck')]], check=True)
        for name in ('NativeFilesBoundaryCheck', 'QcImportFormatCheck', 'ResultImportCheck', 'ResultArtifactCheck', 'DownloadSecurityCheck', 'TransferConcurrencyCheck'):
            name = 'com.mscan.web.controller.common.' + name
            subprocess.run(['java', '-cp', str(classes) + ':' + classpath, name], check=True)


if __name__ == '__main__':
    main()
