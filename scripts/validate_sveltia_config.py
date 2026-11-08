#!/usr/bin/env python3
"""Validate local CMS configuration against the pinned, offline schema only."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable

from jsonschema import ValidationError, validators
from referencing import Registry
from studio_paths import STUDIO_ROOT

ROOT = STUDIO_ROOT
RUNTIME_PATH = ROOT/'config/sveltia-runtime.v1.json'
CONFIG_PATH = ROOT/'admin/config.yml'


def leaf_errors(error: ValidationError) -> Iterable[ValidationError]:
    if not error.context:
        yield error
        return
    for child in error.context:
        yield from leaf_errors(child)


def validate_config(runtime_path=None,config_path=None,schema_root=None) -> list[str]:
    try:
        import yaml
    except ImportError as exc:
        raise ValueError('cms_validation_extra_required: install the declared cms extra') from exc
    runtime=json.loads(Path(runtime_path or RUNTIME_PATH).read_text(encoding='utf-8'))
    if runtime.get('schema_version')!='sveltia-runtime.v1' or runtime.get('package')!='@sveltia/cms' or runtime.get('version')!='0.172.4':
        raise ValueError('unsupported_pinned_cms_runtime')
    ref=runtime.get('local_schema_ref')
    if not isinstance(ref,str) or not ref or ':' in ref or '\\' in ref or Path(ref).is_absolute() or '..' in Path(ref).parts:
        raise ValueError('unsafe_local_schema_ref')
    root=Path(schema_root or ROOT).resolve(strict=True)
    schema_path=(root/ref).resolve(strict=True)
    if not schema_path.is_relative_to(root) or not schema_path.is_file():
        raise ValueError('unsafe_local_schema_ref')
    raw=schema_path.read_bytes()
    expected=runtime.get('schema_sha256')
    if not isinstance(expected,str) or hashlib.sha256(raw).hexdigest()!=expected:
        raise ValueError('cms_schema_hash_drift')
    schema=json.loads(raw)
    validator_type=validators.validator_for(schema,default=None)
    if validator_type is None:
        raise ValueError('unsupported_schema_dialect')
    validator_type.check_schema(schema)
    # Empty Registry: an unprovided remote reference cannot cause a network fetch.
    validator=validator_type(schema,registry=Registry())
    config=yaml.safe_load(Path(config_path or CONFIG_PATH).read_text(encoding='utf-8'))
    messages=[];seen=set()
    for error in sorted(validator.iter_errors(config),key=lambda value:tuple((type(p).__name__,str(p)) for p in value.path)):
        for leaf in leaf_errors(error):
            location='.'.join(str(part) for part in leaf.absolute_path) or '$'
            key=(location,leaf.message)
            if key not in seen:
                seen.add(key);messages.append(f'{location}: {leaf.message}')
    return messages


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,default=RUNTIME_PATH)
    parser.add_argument('--config',type=Path,default=CONFIG_PATH)
    parser.add_argument('--schema-root',type=Path,default=ROOT)
    args=parser.parse_args(argv)
    try:
        errors=validate_config(args.runtime,args.config,args.schema_root)
    except Exception as exc:
        print(f'CMS config validation blocked: {type(exc).__name__}: {exc}')
        return 2
    if errors:
        print('Sveltia config validation failed:')
        for error in errors:print(f'- {error}')
        return 1
    print('Validated local config against pinned Sveltia CMS0.172.4 schema; no CMS bundle, network, login or publication executed.')
    return 0


if __name__=='__main__':raise SystemExit(main())
