"""Execute an installed local-engine plugin inside a disposable container."""
from pathlib import Path
import shutil
import tempfile

from . import contracts, service
from .store import confined

def _operation(*, record, context):
    if contracts.backend(record['plan']['pipeline_name']) != 'docker':
        raise ValueError('This workflow requires the remote WDL execution backend.')
    source = Path(context.session_dir)
    with tempfile.TemporaryDirectory(dir='/tmp') as directory:
        root = Path(directory)
        for values in record['plan']['inputs'].values():
            for item in values:
                target = confined(root, item['path']); target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(confined(source, item['path']), target)
        # Existing engine code owns interpretation and output validation. Hidden
        # engine caches and its temporary JobStore never enter the user workspace.
        result = service.execute_engine(root, record)
        for item in result['output_records']:
            if not item.get('exists'): continue
            relative = item['workspace_path']
            target = confined(source, relative); target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(confined(root, relative), target)
        def remap(value):
            if isinstance(value, str): return value.replace(str(root), str(source))
            if isinstance(value, list): return [remap(item) for item in value]
            if isinstance(value, dict): return {key: remap(item) for key, item in value.items()}
            return value
        return remap(result)
