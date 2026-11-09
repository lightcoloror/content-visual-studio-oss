"""Offline synthetic coverage; no application, network, private data or temp files."""
import copy
import itertools
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = ('non_leading_questions', 'privacy', 'fact_premises', 'spoken_clarity')


def record(categories=CATEGORIES):
    return {
        'schema_version': 'case-interview-guide-review.v1',
        'guide_id': 'synthetic-coverage-guide', 'guide_sha256': '0' * 64,
        'synthetic_only': True, 'reviewer': 'synthetic-fixture-author',
        'reviewed_at': '2026-10-22T00:00:00Z',
        'decision': 'approved_questions_only',
        'authority': 'questions_only_no_recording_or_publication_authority',
        'checks': [{'check_id': category, 'question_id': 'synthetic-question',
                    'question_span': 'Synthetic question only', 'status': 'clear',
                    'reason': 'Synthetic schema coverage check only'} for category in categories],
    }


class InterviewReviewCategoryCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads((ROOT / 'schemas/case-interview-guide-review.v1.schema.json').read_text('utf-8'))
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema, registry=Registry(), format_checker=FormatChecker())

    def assert_rejected(self, value, path, keyword):
        self.assertTrue(any(tuple(e.absolute_path) == path and e.validator == keyword
                            for e in self.validator.iter_errors(value)))

    def test_all_four_categories_in_every_order(self):
        for order in itertools.permutations(CATEGORIES):
            with self.subTest(order=order):
                self.validator.validate(record(order))

    def test_repeated_categories_and_identical_items_are_allowed(self):
        for extra in [CATEGORIES[:1], CATEGORIES, CATEGORIES * 3]:
            with self.subTest(extra=extra):
                self.validator.validate(record(CATEGORIES + extra))

    def test_each_missing_category_rejected_even_with_duplicate_padding(self):
        for missing in CATEGORIES:
            remaining = tuple(c for c in CATEGORIES if c != missing)
            for size in [3, 4, 5, 8, 12]:
                with self.subTest(missing=missing, size=size):
                    categories = tuple(remaining[i % 3] for i in range(size))
                    self.assert_rejected(record(categories), ('checks',), 'contains')

    def test_unknown_category_rejected_even_when_coverage_complete(self):
        value = record(CATEGORIES + ('unknown-category',))
        self.assert_rejected(value, ('checks', 4, 'check_id'), 'enum')

    def test_malformed_extra_item_cannot_hide_behind_complete_coverage(self):
        mutations = [('check_id', None), ('question_span', 'x'), ('status', 'published'),
                     ('reason', 'short'), ('question_id', 7), ('unexpected', True)]
        for key, replacement in mutations:
            with self.subTest(field=key):
                value = record(CATEGORIES + CATEGORIES[:1])
                value['checks'][-1][key] = replacement
                self.assertFalse(self.validator.is_valid(value))
        for key in record()['checks'][0]:
            with self.subTest(missing_field=key):
                value = record(CATEGORIES + CATEGORIES[:1])
                del value['checks'][-1][key]
                self.assert_rejected(value, ('checks', 4), 'required')
        value = record()
        value['checks'].append('not-an-object')
        self.assert_rejected(value, ('checks', 4), 'type')

    def test_authorization_and_record_shape_remain_restricted(self):
        for key, replacement in [('authority', 'recording-authorized'), ('authority', 'publication-authorized'),
                                 ('decision', 'published'), ('synthetic_only', 'true'),
                                 ('reviewed_at', 'not-a-date'), ('guide_sha256', 'bad'),
                                 ('unexpected', True)]:
            with self.subTest(field=key, replacement=replacement):
                value = record()
                value[key] = replacement
                self.assertFalse(self.validator.is_valid(value))

    def test_return_for_revision_with_multiple_checks_still_valid(self):
        value = record(CATEGORIES * 2)
        value['decision'] = 'return_for_revision'
        value['checks'][0]['status'] = 'blocked'
        self.validator.validate(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
