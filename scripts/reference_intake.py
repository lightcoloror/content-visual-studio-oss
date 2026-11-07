from studio_paths import STUDIO_ROOT
"""Optional lead constraints for the existing offline capture entry; never fact review."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from saved_research_candidate import atomic_json, sha


INTAKE_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['provider', 'lead_url', 'recorded_at', 'lead_claim', 'author_rating',
                 'rating_system', 'original_sources'],
    'properties': {
        'provider': {'const': 'HowToLiveBetter'},
        'lead_url': {'type': 'string', 'format': 'uri'},
        'recorded_at': {'type': 'string', 'format': 'date-time'},
        'lead_claim': {'type': 'string', 'minLength': 1},
        'author_rating': {'enum': ['A', 'B', 'C', 'not_recorded']},
        'rating_system': {'const': 'author_defined_not_clinical_GRADE'},
        'original_sources': {'type': 'array', 'items': {
            'type': 'object', 'additionalProperties': False,
            'required': ['url', 'kind'], 'properties': {
                'url': {'type': 'string', 'format': 'uri'},
                'kind': {'enum': ['original_paper', 'official_policy']}}}}}}


def assess_reference(index, material=None):
    """Roles are declared, not verified. Exact saved primary support is necessary only."""
    intake = index.get('reference_intake')
    if intake is None:
        return None
    errors = list(Draft202012Validator(INTAKE_SCHEMA, format_checker=FormatChecker()).iter_errors(intake))
    if errors:
        raise ValueError('reference_intake_invalid: ' + errors[0].message)
    saved = {r['url'] for r in index['captures']}
    originals = [r['url'] for r in intake['original_sources']]
    if intake['lead_url'] not in saved:
        raise ValueError('reference_lead_capture_required')
    if intake['lead_url'] in originals or len(originals) != len(set(originals)):
        raise ValueError('reference_original_must_be_distinct')
    reasons = []
    if not originals:
        reasons.append('original_paper_or_official_policy_required')
    missing = sorted(set(originals) - saved)
    if missing:
        reasons.append('original_capture_missing')
    unsupported = []
    if material is not None:
        primary_ids = {s['source_id'] for s in material['sources']
                       if s['canonical_ref'] in originals}
        for claim in material['claims']:
            if not any(e['claim_id'] == claim['claim_id'] and e['source_id'] in primary_ids
                       and e['relation'] == 'supports' for e in material['evidence']):
                unsupported.append(claim['claim_id'])
        if unsupported:
            reasons.append('claim_without_saved_primary_support')
    return {'provider': intake['provider'], 'lead_url': intake['lead_url'],
            'author_rating': intake['author_rating'], 'rating_system': intake['rating_system'],
            'status': 'needs_source' if reasons else 'needs_primary_review',
            'required_originals': intake['original_sources'], 'missing_capture_urls': missing,
            'unsupported_claim_ids': unsupported, 'blocking_reasons': reasons,
            'source_roles_verified': False, 'clinical_GRADE_assessed': False,
            'verified_fact_promotion_allowed': False, 'network_called': False}


def write_reference_handoff(output, index, material, synthesis, result):
    """Use content-fact-card.v0. Excluded candidate claims cannot unlock story work."""
    output, synthesis = Path(output), Path(synthesis)
    fingerprint = sha(synthesis.read_bytes() + json.dumps(index, sort_keys=True).encode('utf-8'))[:16]
    intake = index['reference_intake']
    sources = (material or {}).get('sources', [])
    synthetic = bool(sources) and all(s.get('synthetic') is True for s in sources)
    claims = (material or {}).get('claims', [])
    facts = [{'fact_id': c['claim_id'], 'text': c['text'], 'status': 'excluded',
              'fact_type': 'public-claim', 'evidence_refs': [
                  {'ref_type': 'claim', 'ref_id': str(synthesis) + '#/derived_material/claims/' + str(n),
                   'usage_status': 'background'}]} for n, c in enumerate(claims)]
    if not facts:
        facts = [{'fact_id': 'lead-unverified', 'text': intake['lead_claim'], 'status': 'excluded',
                  'fact_type': 'public-claim', 'evidence_refs': [
                      {'ref_type': 'source', 'ref_id': intake['lead_url'], 'usage_status': 'background'}]}]
    card = {'schema_version': 'content-fact-card.v0',
            'fact_card_id': 'fact-card-reference-' + fingerprint,
            'content_id': 'content.reference-' + fingerprint,
            'synthetic_only': synthetic, 'revision_id': 'fact-rev-reference-' + fingerprint,
            'canonical_status': 'draft',
            'source_precedence': ['Reviewed original paper or official policy before author lead; review pending.'],
            'facts': facts,
            'unknowns': ['Original-source identity, exact support, region, effective date, population, '
                         'causality, contrary evidence and reuse rights require review.',
                         'Author rating: ' + intake['author_rating'] + '; author-defined, not clinical GRADE.'],
            'forbidden_claims': ['Do not present excluded candidates as verified facts or recommendations.',
                                 'Do not convert author A/B/C into clinical GRADE.',
                                 'Do not present synthetic contract validation as real research.'],
            'gates': {'fact': 'blocked', 'privacy': 'pass' if synthetic else 'needs-review',
                      'medical_insurance': 'needs-review', 'authorization': 'needs-review',
                      'rights': 'needs-review'}}
    schema = json.loads((STUDIO_ROOT / 'schemas/content-fact-card.v0.schema.json').read_text('utf-8'))
    Draft202012Validator(schema).validate(card)
    card_path = output / 'reference-fact-card.json'
    _write_bound(card_path, card)
    handoff = {'fact_card_path': str(card_path), 'revision_id': card['revision_id'],
               'fact_card_sha256': sha(card_path.read_bytes()),
               'synthesis_path': str(synthesis), 'synthesis_sha256': sha(synthesis.read_bytes()),
               'candidate_dir': result.get('candidate_dir'),
               'research_output': result.get('research_output'),
               'status': 'blocked_pending_fact_review', 'story_drafting_allowed': False,
               'publish_authorized': False, 'synthetic_only': synthetic,
               'next_step': 'Review primary sources through existing QRP/ARW; create a new fact-card revision '
                            'and rerun the existing verified research-output adapter before story handoff.'}
    _write_bound(output / 'reference-handoff.json', handoff)
    return handoff


def _write_bound(path, value):
    if path.exists():
        if json.loads(path.read_text('utf-8')) != value:
            raise ValueError('reference_handoff_drift: preserve existing output; use a new reviewed revision')
        return
    atomic_json(path, value)
