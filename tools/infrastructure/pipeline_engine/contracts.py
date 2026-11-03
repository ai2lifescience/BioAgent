"""Manifest-driven dispatch and parameter contracts for installed plugins."""
import math
import re

from isolation.pipeline_policy import require_workflow
from . import service
from .engine.config import _get_runtime_config_value

LOCAL_ENGINES = frozenset({'shell', 'snakemake', 'nextflow'})


def definition(name):
    require_workflow(name)
    directory, manifest, config = service.definition(name)
    engine = manifest.get('engine')
    if engine not in LOCAL_ENGINES | {'wdl'}:
        raise ValueError(f'Unsupported pipeline engine: {engine}.')
    return directory, manifest, config


def backend(name):
    _, manifest, _ = definition(name)
    return 'cromwell' if manifest['engine'] == 'wdl' else 'docker'


def validate_parameters(values, manifest, config):
    specs = manifest.get('param_overrides') or {
        key: {'config_key': 'params.' + key, 'default': value}
        for key, value in config.get('params', {}).items()
    }
    unknown = set(values) - set(specs)
    if unknown:
        raise ValueError('Unknown pipeline parameter(s): ' + ', '.join(sorted(unknown)))
    for name, value in values.items():
        spec = specs[name]
        spec = {'config_key': spec} if isinstance(spec, str) else spec or {}
        key = spec.get('config_key') or spec.get('wdl_key') or spec.get('key') or name
        default = _get_runtime_config_value(config, key, spec.get('default'))
        choices = spec.get('choices')
        if choices and value not in choices:
            raise ValueError(f'{name} must be one of its declared choices.')
        # Deployment-selected images/reference locations must not become an
        # arbitrary image or host-file capability through a model parameter.
        if name.endswith(('_path', '_dir', '_image')) or name in {'image', 'docker', 'container'}:
            if value != default:
                raise ValueError(f'{name} is deployment configuration; use declared input slots for session files.')
            continue
        expected = spec.get('type') or ({bool: 'boolean', int: 'integer', float: 'number', str: 'string', list: 'array'}.get(type(default)))
        valid = {'boolean': type(value) is bool, 'integer': type(value) is int,
                 'number': type(value) in {int, float}, 'string': isinstance(value, str), 'array': isinstance(value, list)}
        if expected in valid and not valid[expected]:
            raise ValueError(f'{name} must have type {expected}.')
        def scalar(item):
            if type(item) is bool: return
            if type(item) in {int, float}:
                if not math.isfinite(item) or not spec.get('minimum', 0) <= item <= spec.get('maximum', 10_000_000):
                    raise ValueError(f'{name} is outside its numeric limits.')
            elif isinstance(item, str):
                if not re.fullmatch(r'[A-Za-z0-9_. -]{0,120}', item):
                    raise ValueError(f'{name} must be plain text without shell syntax or paths.')
            else:
                raise ValueError(f'{name} must be a scalar or a declared array of scalars.')
        if isinstance(value, list):
            if expected != 'array' or len(value) > 1024:
                raise ValueError(f'{name} exceeds its array contract.')
            for item in value: scalar(item)
        else:
            scalar(value)
