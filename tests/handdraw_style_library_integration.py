import copy
import json
import sys
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from handdraw_style_library import Library


class HanddrawLibraryTests(unittest.TestCase):
    def setUp(self):
        self.library = Library()
        fixture = ROOT / 'fixtures/handdraw-style-library'
        self.item = json.loads((fixture / 'content-item.json').read_text(encoding='utf-8'))
        self.request = json.loads((fixture / 'prompt-request.json').read_text(encoding='utf-8'))

    def prompt(self):
        return self.library.prompt(self.item, 'notes', self.request)

    def test_gallery_overlay_preserves_pinned_source_and_navigation(self):
        from handdraw_gallery_adapter import materialize
        from handdraw_style_library import digest
        source = self.library.checked(self.library.prefix + 'gallery/index.html')
        before = digest(source)
        with tempfile.TemporaryDirectory(prefix='handdraw-test-') as directory:
            result = materialize(self.library, Path(directory))
            self.assertEqual(result, materialize(self.library, Path(directory)))
            page = Path(result['styles']).read_text(encoding='utf-8')
            self.assertIn(Path(result['layouts']).as_uri(), page)
            self.assertIn(source.parent.as_uri() + '/', page)
            self.assertNotIn('\ncheckRepositoryUpdate();', page)
            self.assertNotIn('href="assets.html"', page)
            self.assertNotIn('href="tutorials.html"', page)
        self.assertEqual(before, digest(source))
        self.library.checked(self.library.prefix + 'gallery/index.html')

    def test_gallery_overlay_does_not_overwrite_changed_cache(self):
        from handdraw_gallery_adapter import materialize
        with tempfile.TemporaryDirectory(prefix='handdraw-test-') as directory:
            result = materialize(self.library, Path(directory))
            target = Path(result['styles'])
            target.write_text('preserve this review evidence', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'cache changed'):
                materialize(self.library, Path(directory))
            self.assertEqual('preserve this review evidence', target.read_text(encoding='utf-8'))

    def test_all_numbered_reference_assets_resolve_and_are_pinned(self):
        resolver = self.library.module('resolve_reference')
        self.assertEqual(280, len(self.library.styles))
        for style in self.library.styles:
            result = resolver.resolve('unregistered-model', style['number'])
            self.assertTrue(result['use_reference_image'])
            path = Path(result['reference_path'])
            self.library.checked(path.relative_to(self.library.root).as_posix())

    def test_layouts_and_colors_have_all_local_assets(self):
        prefix = self.library.prefix
        reader = self.library.module('layout_library')
        for layout in self.library.layouts:
            path = self.library.checked(prefix + 'references/' + layout['prompt_file'])
            self.assertEqual({'zh', 'en'}, set(reader.read_prompt(path)))
            self.library.checked(prefix + 'gallery/' + layout['image'])
        for color in self.library.colors:
            self.library.checked(prefix + 'gallery/' + color['image'])

    def test_preserves_frozen_text_subject_and_input(self):
        original = copy.deepcopy(self.item)
        result = self.prompt()
        self.assertEqual(original, self.item)
        self.assertFalse(result['image_generated'])
        for language in ('zh', 'en'):
            self.assertIn(self.request['theme'][language], result['prompts'][language])
            self.assertIn('先整理，再决定', result['prompts'][language])
            self.assertNotIn('SC-001', result['prompts'][language])
        self.assertIsNotNone(result['layout_reference'])
        self.assertEqual('candidate-only', result['status'])

    def test_changed_content_invalidates_binding(self):
        before = self.prompt()['content_sha256']
        self.item['title'] = 'new body version'
        self.assertNotEqual(before, self.prompt()['content_sha256'])

    def test_no_upstream_free_copy_rewrite_suffix(self):
        prompts = self.prompt()['prompts']
        self.assertNotIn('文案由你来升华', ''.join(prompts.values()))

    def test_calibration_is_not_promoted_to_local_measurement(self):
        self.request['model'] = 'gpt-image-2'
        result = self.prompt()
        self.assertEqual(1, len(result['referenced_image_paths']))
        self.assertIn('not_locally_verified', result['model_calibration'])

    def test_invalid_selection_rejected(self):
        for key, value in [('style_number', '999'), ('layout_id', 'SC-999'), ('color_ids', ['C-99'])]:
            with self.subTest(key=key):
                old = self.request[key]
                self.request[key] = value
                with self.assertRaisesRegex(ValueError, 'Unknown'):
                    self.prompt()
                self.request[key] = old

    def test_frozen_or_evidence_slot_rejected(self):
        slot = self.item['visual']['article_visual_plan']['slots'][0]
        slot['status'] = 'selected'
        with self.assertRaises(ValueError):
            self.prompt()
        slot['status'] = 'planned'
        slot['media_role'] = 'evidence'
        with self.assertRaises(ValueError):
            self.prompt()

    def test_no_silent_render_route_change(self):
        self.item['visual']['article_visual_plan']['slots'][0]['route'] = 'diagram'
        with self.assertRaisesRegex(ValueError, 'explicit generated-image'):
            self.prompt()

    def test_dynamic_layout_requires_resolved_composition(self):
        self.request['layout_id'] = 'SC-021'
        self.request.pop('composition')
        with self.assertRaisesRegex(ValueError, 'confirmed composition'):
            self.prompt()

    def test_source_manifest_drift_rejected(self):
        config = copy.deepcopy(self.library.config)
        config['manifest_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'drifted'):
            Library(config)

    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(ValueError, 'escapes'):
            self.library.checked('../not-in-package')

    def test_missing_theme_not_invented(self):
        del self.request['theme']['en']
        with self.assertRaisesRegex(ValueError, 'confirmed theme'):
            self.prompt()

    def test_explicit_palette_not_auto_replaced(self):
        self.request.pop('color_ids')
        self.request['palette'] = {'zh': '已确认的灰蓝与暖白', 'en': 'Approved gray-blue and warm white'}
        result = self.prompt()
        self.assertIn('Approved gray-blue', result['prompts']['en'])
        self.assertEqual([], result['color_ids'])


if __name__ == '__main__':
    unittest.main()
