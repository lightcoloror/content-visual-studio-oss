"""Pinned handraw-style resources behind the existing content-slot interface.

Reuse yang0's resolver and layout reader. No providers, downloads, automatic
recommendations, item mutation, or rendering in this adapter.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

try:  # The installed public package ships studio_paths; keep a source-tree fallback.
    from studio_paths import STUDIO_ROOT
except ModuleNotFoundError:  # pragma: no cover - isolated source/test trees
    STUDIO_ROOT = Path(__file__).resolve().parents[1]

ROOT = Path(STUDIO_ROOT)
CONFIG = ROOT / 'config/handdraw-style-library.v1.json'

LIBRARY_ROOT_ENV = 'CONTENT_STUDIO_HANDDRAW_ROOT'
GALLERY_ROOT_ENV = 'CONTENT_STUDIO_HANDDRAW_GALLERY_ROOT'
MISSING_LIBRARY_ROOT = (
    'Pinned handdraw-style source root is not configured; provide an explicit '
    'source_root, set CONTENT_STUDIO_HANDDRAW_ROOT, or configure a nonempty local_path'
)
MISSING_GALLERY_ROOT = (
    'Gallery output root is not configured; provide output_root or set '
    'CONTENT_STUDIO_HANDDRAW_GALLERY_ROOT outside the pinned source and installed resources'
)
KNOWN_SOURCE_MODULES = frozenset({'style_asset_paths', 'resolve_reference', 'layout_library'})
HELPER_MODULE = 'style_asset_paths'
_AMBIENT_MISSING = object()


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Library:
    def __init__(self, config: dict | None = None, *, source_root=None):
        self.config = config if config is not None else json.loads(CONFIG.read_text(encoding='utf-8'))
        self.root = self._resolve_root(source_root)
        self.manifest_path, self.manifest = self._load_manifest()
        self.prefix = 'skills/handdraw-style-prompter/'
        for name in ('style_asset_paths.py', 'resolve_reference.py', 'layout_library.py'):
            self.checked(self.prefix + 'scripts/' + name)
        self.styles = self.data('styles.json')
        self.colors = self.data('colors.json')
        self.layouts = self.data('layouts.json')
        self.checked(self.prefix + 'references/model_capabilities.json')
        # Installed resource tree, used by the gallery writer to refuse in-tree outputs.
        self.resource_root = Path(ROOT).resolve()

    def _resolve_root(self, source_root) -> Path:
        candidate: Path | None = None
        if source_root is not None:
            candidate = Path(source_root).expanduser()
        if candidate is None:
            env_value = os.environ.get(LIBRARY_ROOT_ENV, '').strip()
            if env_value:
                candidate = Path(env_value).expanduser()
        if candidate is None:
            local_path = self.config.get('local_path')
            if isinstance(local_path, str) and local_path.strip():
                candidate = Path(local_path).expanduser()
                if not candidate.is_absolute():
                    candidate = ROOT / candidate
        if candidate is None:
            raise ValueError(MISSING_LIBRARY_ROOT)
        return candidate.resolve()

    def _load_manifest(self):
        configured = self.config.get('manifest_path')
        expected = self.config.get('manifest_sha256')
        if configured:
            path = Path(configured)
            if not path.is_absolute():
                path = ROOT / path
            path = path.expanduser().resolve()
            if not expected:
                raise ValueError('Library source manifest hash is not configured')
        else:
            # Old explicit configurations may point at an external checkout manifest.
            path = (self.root / 'local-source-manifest.json').resolve()
            if not expected:
                raise ValueError('Source manifest has drifted')
        # Hash the exact buffer that is decoded below; a second read could return
        # bytes that were never checked.
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ValueError('Source manifest has drifted') from exc
        if hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError('Source manifest has drifted')
        manifest = json.loads(payload.decode('utf-8'))
        if manifest['commit'] != self.config['commit']:
            raise ValueError('Source commit binding has drifted')
        return path, manifest

    def _read_verified(self, relative: str):
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('Source path escapes pinned package')
        key = path.relative_to(self.root).as_posix()
        expected = self.manifest['files'].get(key)
        # One read: the buffer that is hash-checked is the buffer the caller uses.
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ValueError(f'Pinned source asset missing or changed: {key}') from exc
        if not expected or hashlib.sha256(payload).hexdigest() != expected:
            raise ValueError(f'Pinned source asset missing or changed: {key}')
        return path, payload

    def checked(self, relative: str) -> Path:
        # Public path API preserved; the returned path was verified by this call.
        return self._read_verified(relative)[0]

    def read_checked(self, relative: str) -> bytes:
        return self._read_verified(relative)[1]

    def _load_pinned_module(self, name: str):
        # Compile and execute only the exact hash-verified buffer: a second read
        # could expose bytes that were never checked, and the import loader would
        # write __pycache__ into the external upstream checkout.
        path, payload = self._read_verified(self.prefix + 'scripts/' + name + '.py')
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ValueError(f'Pinned source module cannot be loaded: {name}')
        module = importlib.util.module_from_spec(spec)
        code = compile(payload, str(path), 'exec')
        exec(code, module.__dict__)
        return module

    def module(self, name: str):
        if not isinstance(name, str) or name not in KNOWN_SOURCE_MODULES:
            raise ValueError(f'Unknown pinned source module: {name!r}')
        previous = sys.modules.get(HELPER_MODULE, _AMBIENT_MISSING)
        try:
            helper = self._load_pinned_module(HELPER_MODULE)
            sys.modules[HELPER_MODULE] = helper
            if name == HELPER_MODULE:
                return helper
            return self._load_pinned_module(name)
        finally:
            if previous is _AMBIENT_MISSING:
                sys.modules.pop(HELPER_MODULE, None)
            else:
                sys.modules[HELPER_MODULE] = previous

    def data(self, name: str):
        return json.loads(self.read_checked(self.prefix + 'references/' + name).decode('utf-8'))

    def gallery(self, output_root=None) -> dict:
        from handdraw_gallery_adapter import materialize
        destination = output_root
        if destination is None:
            env_value = os.environ.get(GALLERY_ROOT_ENV, '').strip()
            if env_value:
                destination = Path(env_value)
        if destination is None:
            raise ValueError(MISSING_GALLERY_ROOT)
        paths = materialize(self, Path(destination))
        return {'status': 'local-reference-library', 'galleries': paths,
                'counts': {'styles': len(self.styles), 'layouts': len(self.layouts), 'colors': len(self.colors)},
                'source': self.config.get('repository'), 'commit': self.config['commit'],
                'attribution': self.config.get('attribution'),
                'license': self.config.get('license'),
                'license_status': self.config.get('license_status', 'not-declared'),
                'asset_rights_status': self.config.get(
                    'asset_rights_status', 'unverified-for-redistribution'),
                'manual_review_required': True,
                'image_generated': False}

    def catalog(self, query: str = '') -> dict:
        words = query.casefold().split()
        def matches(row):
            text = json.dumps(row, ensure_ascii=False).casefold()
            return all(word in text for word in words)
        return {'styles': [row for row in self.styles if matches(row)],
                'layouts': [row for row in self.layouts if matches(row)],
                'colors': [row for row in self.colors if matches(row)],
                'selection': 'browse-or-explicit-selection; no aesthetic scoring'}

    def prompt(self, item: dict, target_id: str, request: dict) -> dict:
        from handdraw_style_brief import target_from_item, read_json, DIRECTIONS
        if item.get('schema_version') != '0.2' or not item.get('content_id'):
            raise ValueError('A versioned content item is required')
        media, slot = target_from_item(item, target_id)
        if media != 'article' or slot.get('route') != 'generated-image':
            raise ValueError('Prompt handoff requires an explicit generated-image article slot')
        if not slot.get('purpose', '').strip():
            raise ValueError('Existing slot purpose is required')
        ds = item.get('visual', {}).get('design_system', {})
        direction = ds.get('design_direction', {})
        definitions = read_json(DIRECTIONS)['directions']
        definition = definitions.get(direction.get('direction_id'), {})
        if (ds.get('media_adapter') != media or not definition
                or definition.get('version') != direction.get('version')
                or not definition.get('routes', {}).get(media, {}).get('status', '').startswith('route-eligible')):
            raise ValueError('Content design direction/media binding is not eligible')
        mode = item['visual'].get('article_visual_plan', {}).get('visual_mode')
        if mode in definition.get('excluded_routes', {}).get('article_visual_modes', []):
            raise ValueError('Design direction excludes this article visual mode')
        number = str(request.get('style_number', '')).zfill(3)
        style = next((x for x in self.styles if x['number'] == number), None)
        if not style:
            raise ValueError('Unknown style number')
        themes = request.get('theme', {})
        if not isinstance(themes, dict) or any(not isinstance(themes.get(k), str) or not themes[k].strip() for k in ('zh', 'en')):
            raise ValueError('Supply confirmed theme.zh and theme.en; no automatic subject invention')
        if request.get('mode', 'pure-image') not in ('pure-image', 'graphic-text'):
            raise ValueError('Unknown prompt mode')
        frozen = request.get('frozen_text', [])
        if not isinstance(frozen, list) or any(not isinstance(x, str) or not x.strip() for x in frozen):
            raise ValueError('frozen_text must contain exact nonempty strings')
        # Treat model calibration as unverified. Reuse the resolver's conservative
        # branch even when a requested model happens to appear in upstream tables.
        resolver = self.module('resolve_reference')
        resolution = resolver.resolve(request.get('model') or 'unknown', number,
                                      {'default': {'name_activation': 'unknown', 'traits_activation': 'unknown'}, 'models': {}})
        asset = Path(resolution['reference_path']).resolve()
        asset, asset_payload = self._read_verified(asset.relative_to(self.root).as_posix())
        layout = None
        composition = request.get('composition', {})
        if request.get('layout_id'):
            identifier = str(request['layout_id']).upper()
            layout = next((x for x in self.layouts if x['id'] == identifier), None)
            if not layout:
                raise ValueError('Unknown layout ID')
            if not isinstance(composition, dict) or any(not isinstance(composition.get(k), str) or not composition[k].strip() for k in ('zh', 'en')):
                raise ValueError('Selected layout requires confirmed composition.zh/en; resolve dynamic choices first')
            prompt_file = self.checked(self.prefix + 'references/' + layout['prompt_file'])
            layout = {**layout, 'source_prompts': self.module('layout_library').read_prompt(prompt_file)}
        colors = []
        color_ids = request.get('color_ids', [])
        if not isinstance(color_ids, list) or len(set(color_ids)) != len(color_ids):
            raise ValueError('color_ids must be a unique list')
        for identifier in color_ids:
            color = next((x for x in self.colors if x['id'] == identifier), None)
            if color is None:
                raise ValueError('Unknown color ID')
            colors.append(color)
        palettes = request.get('palette', {})
        if palettes and (colors or not isinstance(palettes, dict) or any(not isinstance(palettes.get(k), str) or not palettes[k].strip() for k in ('zh', 'en'))):
            raise ValueError('Use either selected colors or a confirmed bilingual palette')
        prompts = {}
        for lang in ('zh', 'en'):
            zh = lang == 'zh'
            parts = [('风格：' if zh else 'Style: ') + style['generation_name'],
                     ('主题（锁定）：' if zh else 'Locked subject: ') + themes[lang]]
            if composition.get(lang):
                parts.append(('构图（已确认）：' if zh else 'Confirmed composition: ') + composition[lang])
            if colors:
                parts.append(('配色：' if zh else 'Palette: ') + ', '.join(x['name_zh' if zh else 'name_en'] for x in colors))
            elif palettes:
                parts.append(('配色：' if zh else 'Palette: ') + palettes[lang])
            else:
                parts.append('沿用当前内容已确认配色，不自行重新推荐。' if zh else 'Retain the existing approved palette; do not select a new palette.')
            parts.append('附图只借鉴线条、笔触、媒介与质感；不复制人物、物件、文字、场景或构图。主题和构图只以本任务为准。'
                         if zh else 'Use the attached image only for linework, brushwork, medium and texture. Do not copy its people, objects, text, scene or composition. This task defines all subject matter and composition.')
            if frozen:
                parts.append(('画中文字只能逐字使用：' if zh else 'Use only this exact visible text: ') + json.dumps(frozen, ensure_ascii=False))
                parts.append('不得增删、润色、翻译文字或数字；文字不准时交给既有排版工具叠字。' if zh else 'Do not add, rewrite or translate text or numbers. Use the existing typesetting tool if lettering is inaccurate.')
            else:
                parts.append('画面不出现文字、数字、水印或编号。' if zh else 'No visible text, numbers, watermarks or identifiers.')
            prompts[lang] = '\n'.join(parts)
        return {'schema_version': 'handdraw-style-prompt.v1', 'status': 'candidate-only',
                'content_id': item['content_id'], 'target_id': target_id, 'purpose': slot['purpose'],
                'content_sha256': hashlib.sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                'source_commit': self.config['commit'], 'style_number': number,
                'style_name': style['generation_name'], 'layout_reference': layout,
                'color_ids': color_ids, 'prompts': prompts, 'frozen_text': frozen,
                'referenced_image_paths': [str(asset)],
                'reference_sha256': hashlib.sha256(asset_payload).hexdigest(),
                'reference_role': 'style-only', 'model': request.get('model') or 'unknown',
                'model_calibration': 'upstream_claim_not_locally_verified; conservative_reference_required',
                'attribution': self.config.get('attribution'), 'image_generated': False,
                'next_step': 'Use existing image tool only on explicit generation request; then visual/text QA.',
                'manual_review_required': True}
