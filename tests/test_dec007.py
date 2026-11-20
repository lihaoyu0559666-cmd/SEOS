"""DEC-007 scope isolation and complete, traceable teaching-case regression."""
from pathlib import Path
from fractions import Fraction
import copy
import hashlib
import json
import pytest
from seos.main import run
from scripts.verify_teaching_case import certify

CASE = json.loads(Path('engineering/teaching_case_v1.json').read_text(encoding='utf8'))
DATA = json.loads(Path(CASE['input_file']).read_text(encoding='utf8'))


def test_teaching_input_is_complete_and_wholly_explicit_synthetic():
    assert hashlib.sha256(Path(CASE['input_file']).read_bytes()).hexdigest() == CASE['input_sha256']
    assert CASE['verification_track'] == 'TEACHING_ENGINEERING'
    assert CASE['data_origin'] == 'SYNTHETIC'
    for key, provenance in CASE['parameter_sources'].items():
        assert key in DATA and provenance['origin'] == 'SYNTHETIC'
        assert provenance['unit'] and provenance['basis']
    assert len(CASE['material_assumptions']) == 4
    assert all(row['kind'] == 'TEACHING_ASSUMPTION' for row in CASE['material_assumptions'])
    assert CASE['formal_acceptance_status'] == 'NOT TESTED'


def test_exact_independent_physical_and_optimality_certificate():
    result = run(DATA)
    proof = certify(DATA, result, CASE)
    assert Fraction(proof['gap_exact']) == 0
    assert result['currency_result'] is None
    assert result['dataset_kind'] == 'synthetic'


@pytest.mark.parametrize('row', range(3))
def test_certificate_detects_modified_transport_row(row):
    result = copy.deepcopy(run(DATA))
    result['matrix_exact'][row][row] = str(Fraction(result['matrix_exact'][row][row]) + Fraction(1, 10**12))
    with pytest.raises(AssertionError):
        certify(DATA, result, CASE)


@pytest.mark.parametrize('key', ['bank_dry_density_kg_m3', 'compacted_dry_density_kg_m3',
                                 'distance_km', 'haul_rate_cny_per_m3_km'])
def test_missing_engineering_parameters_are_not_filled_from_teaching_fixture(key):
    data = copy.deepcopy(DATA)
    del data[key]
    original = copy.deepcopy(data)
    result = run(data)
    assert result['status'] == 'MISSING_DATA'
    assert result['currency_result'] is None and data == original and key not in data


def test_synthetic_numbers_never_unlock_real_track():
    data = copy.deepcopy(DATA)
    data['dataset_kind'] = 'real'
    assert run(data)['status'] == 'SOURCE_REVIEW_REQUIRED'
    assert run(data)['currency_result'] is None


def test_no_implicit_data_conversion_or_mutation():
    before = copy.deepcopy(DATA)
    result = run(DATA)
    assert DATA == before
    assert result['matrix_unit'] == 'm3 bank'
    assert result['objective_unit'] == 'synthetic CNY'
