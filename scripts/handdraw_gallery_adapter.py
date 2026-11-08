"""Materialize a small local gallery overlay; never change pinned upstream files."""
from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

try:  # The installed public package ships studio_paths; keep a source-tree fallback.
    from studio_paths import STUDIO_ROOT
except ModuleNotFoundError:  # pragma: no cover - isolated source/test trees
    STUDIO_ROOT = Path(__file__).resolve().parents[1]

RESOURCE_ROOT = Path(STUDIO_ROOT).resolve()
UPSTREAM_CREDIT = 'yang0'
UPSTREAM_REPOSITORY = 'https://github.com/yang0/handraw-style'
ATTRIBUTION_ID = 'handdraw-source-attribution'

MANUAL_COPY = """<script>
function handdrawManualCopy(text) {
  document.querySelector('#handdraw-copy-fallback')?.remove();
  const box=document.createElement('dialog');box.id='handdraw-copy-fallback';
  box.style.cssText='box-sizing:border-box;width:min(560px,90vw);max-height:85vh;padding:20px;overflow:auto';
  const label=document.createElement('p'), area=document.createElement('textarea'), close=document.createElement('button');
  const en=document.documentElement.lang==='en';
  label.textContent=en?'Automatic copy failed. Select and copy the text below.':'自动复制失败，请选中下面的文字手动复制。';
  area.value=text;area.readOnly=true;area.setAttribute('aria-label',en?'Text to copy':'待复制文字');
  area.style.cssText='display:block;box-sizing:border-box;width:100%;height:180px;margin:12px 0';
  close.textContent=en?'Close':'关闭';close.type='button';close.onclick=()=>box.close();
  box.append(label,area,close);document.body.append(box);
  box.addEventListener('close',()=>box.remove(),{once:true});box.showModal();area.focus();area.select();
}
</script>"""


def _is_within(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _guard_output_root(library, output_root) -> Path:
    """Resolve the operator root and refuse it inside pinned upstream/installed resources."""
    destination = Path(output_root).expanduser().resolve()
    upstream = Path(library.root).resolve()
    resources = Path(getattr(library, 'resource_root', RESOURCE_ROOT)).expanduser().resolve()
    if _is_within(destination, upstream):
        raise ValueError('Gallery output root must stay outside the pinned upstream source tree')
    if _is_within(destination, resources):
        raise ValueError('Gallery output root must stay outside the installed resource tree')
    return destination


def _guard_generated_path(library, intended_root: Path, path: Path, label: str) -> Path:
    """Check the resolved generated path, not just the lexical output root.

    A symlink, junction or resolve alias for the signature directory or a page name
    must not redirect a generated write into the pinned upstream or installed trees.
    """
    resolved = path.resolve()
    if resolved != path:
        raise ValueError(f'Gallery {label} must not resolve through an alias')
    upstream = Path(library.root).resolve()
    resources = Path(getattr(library, 'resource_root', RESOURCE_ROOT)).expanduser().resolve()
    if _is_within(resolved, upstream):
        raise ValueError(f'Gallery {label} must stay outside the pinned upstream source tree')
    if _is_within(resolved, resources):
        raise ValueError(f'Gallery {label} must stay outside the installed resource tree')
    if not _is_within(resolved, intended_root):
        raise ValueError(f'Gallery {label} must stay inside the explicit gallery output root')
    return resolved


def _attribution_text(library) -> str:
    """Visible, HTML-escaped credit: configured attribution plus the required upstream credit."""
    config = getattr(library, 'config', None) or {}
    attribution = str(config.get('attribution') or '').strip()
    repository = str(config.get('repository') or '').strip()
    fixed = f'{UPSTREAM_CREDIT} — {UPSTREAM_REPOSITORY}'
    parts = [fixed]
    if attribution and attribution not in fixed:
        parts.append(attribution)
    if repository and repository != UPSTREAM_REPOSITORY and repository not in attribution:
        parts.append(repository)
    parts.append('Attribution required by the pinned upstream license; local reference overlay only.')
    return html.escape(' | '.join(parts))


def _attribution_block(library) -> str:
    return ('<footer id="' + ATTRIBUTION_ID + '" role="contentinfo" '
            'style="margin:24px 16px;padding:12px 16px;border-top:1px solid #cccccc;'
            'font:14px/1.5 system-ui,sans-serif;color:#333333">'
            + _attribution_text(library) + '</footer>')


def _inject_attribution(text: str, library) -> str:
    if '</body>' not in text:
        raise ValueError('Pinned gallery document shape changed')
    return text.replace('</body>', _attribution_block(library) + '\n</body>', 1)


def _overlay_text(name, text, source_path: Path, destination: Path, library) -> str:
    base = html.escape(source_path.parent.as_uri() + '/', quote=True)
    text = text.replace('<head>', f'<head>\n<base href="{base}">', 1)
    # Relative assets stay bound to the pinned source, while gallery navigation
    # stays inside this overlay, including after switching tabs.
    text = re.sub(r'href="(?:\./)?(index|layouts|colors)\.html"',
                  lambda match: 'href="' + (destination / (match[1] + '.html')).as_uri() + '"', text)
    # Custom-library and tutorial pages are outside this three-gallery bundle.
    # Preserve the header label, but do not leave a link to an absent file.
    text = re.sub(r'href="(?:\./)?(?:assets|tutorials)\.html"',
                  'href="#" aria-disabled="true" onclick="event.preventDefault()" title="Not included in this local reference bundle"', text)
    if name in ('index', 'layouts'):
        button = 'button' if name == 'index' else 'copyButton'
        replacement = ("let copied=false;try{copied=document.execCommand('copy');}catch{}\n"
                       "if(!copied){const payload=area.value;area.remove();"
                       f"{button}.textContent=I18N[currentLang].copyFailed;"
                       "handdrawManualCopy(payload);return;}")
        if text.count("document.execCommand('copy');") != 1:
            raise ValueError('Pinned gallery copy handler shape changed')
        text = text.replace("document.execCommand('copy');", replacement)
        text = text.replace('document.body.append(area);', "(document.querySelector('dialog[open]')||document.body).append(area);")
        text = text.replace('</head>', MANUAL_COPY + '\n</head>', 1)
    if name == 'index':
        # A pinned offline catalog has no reason to check the network for updates.
        text = text.replace('\ncheckRepositoryUpdate();', '\n// Pinned local gallery: update checks disabled.')
    return _inject_attribution(text, library)


def _write_new_page(target: Path, text: str) -> None:
    """Create a new page exclusively; never overwrite a different existing byte set."""
    try:
        with target.open('x', encoding='utf-8') as handle:
            handle.write(text)
    except FileExistsError:
        try:
            existing = target.read_text(encoding='utf-8')
        except OSError as exc:
            raise ValueError('Generated gallery cache changed; preserve it for review') from exc
        if existing != text:
            raise ValueError('Generated gallery cache changed; preserve it for review')


def materialize(library, output_root: Path) -> dict[str, str]:
    intended_root = _guard_output_root(library, output_root)
    relative_sources = {name: library.prefix + f'gallery/{name}.html'
                        for name in ('index', 'layouts', 'colors')}
    payloads = {name: library.read_checked(relative)
                for name, relative in relative_sources.items()}
    original = {name: payload.decode('utf-8') for name, payload in payloads.items()}
    source_paths = {name: (library.root / relative).resolve()
                    for name, relative in relative_sources.items()}
    attribution = _attribution_text(library)
    signature = hashlib.sha256(
        Path(__file__).read_bytes() + ''.join(original.values()).encode()
        + str(library.root).encode() + attribution.encode()).hexdigest()[:20]
    destination = _guard_generated_path(
        library, intended_root, intended_root / signature, 'generated destination')
    targets = {
        name: _guard_generated_path(
            library, intended_root, destination / f'{name}.html', f'{name} page')
        for name in original
    }
    overlays = {name: _overlay_text(name, text, source_paths[name], destination, library)
                for name, text in original.items()}
    destination.mkdir(parents=True, exist_ok=True)
    for name, text in overlays.items():
        _write_new_page(targets[name], text)
    return {key: str(targets[name])
            for key, name in (('styles', 'index'), ('layouts', 'layouts'), ('colors', 'colors'))}
