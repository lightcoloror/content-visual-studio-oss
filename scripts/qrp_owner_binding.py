"""Bind the existing QRP package to an explicit source owner; never switch mixed roots."""
import hashlib
import importlib
import importlib.metadata
import os
from pathlib import Path


def default_qrp_root():
    explicit=os.environ.get('CONTENT_STUDIO_QRP_ROOT')
    if explicit:
        return Path(explicit).expanduser().resolve()
    root=Path(__file__).resolve().parents[1]
    workspace=root.parent if (root/'schemas/content-item.schema.json').is_file() else Path.cwd()
    return workspace/'question-research-poc'


def bind_qrp(qrp_root):
    source = Path(qrp_root).resolve() / 'src/question_research_poc'
    if not (source / 'bounded_deep_loop.py').is_file():
        raise ValueError('qrp_source_root_required')
    package = importlib.import_module('question_research_poc')
    actual = Path(package.__file__).resolve().parent
    if actual != source:
        # Installed public packages are valid only when every distributed source
        # resource matches the explicit owner. A version string alone is weak.
        distribution = importlib.metadata.distribution('question-research-poc')
        installed = Path(distribution.locate_file('question_research_poc')).resolve()
        if actual != installed:
            raise ValueError('qrp_module_root_mismatch')
        for path in source.rglob('*'):
            if not path.is_file() or path.suffix not in {'.py', '.json'}:
                continue
            relative = path.relative_to(source)
            target = actual / relative
            if not target.is_file() or hashlib.sha256(target.read_bytes()).digest() != hashlib.sha256(path.read_bytes()).digest():
                raise ValueError('qrp_installed_source_drift:' + relative.as_posix())
    cli = importlib.import_module('question_research_poc.cli')
    core = importlib.import_module('question_research_poc.bounded_deep_loop')
    if any(not Path(module.__file__).resolve().is_relative_to(actual) for module in (cli, core)):
        raise ValueError('qrp_module_root_mismatch')
    return cli.main, core
