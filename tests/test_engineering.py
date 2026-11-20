import json
from pathlib import Path
import pytest
from seos.main import run
from seos.modules.earthwork_calculator import convert_state


def synthetic_input():
    # Arithmetic fixture only. No project density or distance is asserted.
    return {'mode': 'engineering', 'bank_volumes_m3': [10, 20, 30],
            'compacted_volumes_m3': [5, 10, 15], 'bank_dry_density_kg_m3': [1500]*3,
            'compacted_dry_density_kg_m3': [1800]*3,
            'haul_rate_cny_per_m3_km': [[2]*3 for _ in range(3)],
            'distance_km': [[3]*3 for _ in range(3)],
            'density_source': 'synthetic test fixture', 'distance_source': 'synthetic test fixture',
            'billing_volume_state': 'bank'}


def test_template_blocks_engineering():
    data = json.loads(Path('data/engineering_input_template.json').read_text())
    result = run(data)
    assert result['status'] == 'MISSING_DATA'
    assert result['currency_result'] is None
    assert 'bank_dry_density_kg_m3[0]' in result['missing_fields']
    assert 'distance_km[0][0]' in result['missing_fields']


def test_mass_and_rate_dimensions():
    result = run(synthetic_input())
    assert result['status'] == 'READY_FOR_MODEL_REVIEW'
    assert result['supply_dry_mass_kg'] == [15000, 30000, 45000]
    assert result['demand_dry_mass_kg'] == [9000, 18000, 27000]
    assert result['route_price_cny_per_billed_m3'] == [[6]*3 for _ in range(3)]
    assert result['dry_mass_gap_kg'] == 36000
    assert result['currency_result'] is None


@pytest.mark.parametrize('field', ['bank_dry_density_kg_m3', 'compacted_dry_density_kg_m3', 'distance_km', 'density_source', 'distance_source', 'billing_volume_state'])
def test_missing_field_blocks(field):
    data = synthetic_input()
    data[field] = None
    assert run(data)['status'] == 'MISSING_DATA'


@pytest.mark.parametrize('value', [0, -1, float('nan'), float('inf'), True, '1500'])
def test_invalid_density(value):
    data = synthetic_input()
    data['bank_dry_density_kg_m3'][0] = value
    assert run(data)['status'] == 'INVALID_INPUT'


def test_missing_matrix_cell():
    data = synthetic_input()
    data['distance_km'][1][2] = None
    assert 'distance_km[1][2]' in run(data)['missing_fields']


def test_mass_round_trip():
    result = convert_state(100, 1500, 1800)
    assert result['status'] == 'CALCULATED'
    assert result['dry_mass_kg'] == 150000
    assert convert_state(result['target_volume_m3'], 1800, 1500)['target_volume_m3'] == pytest.approx(100)


def test_missing_conversion_density():
    assert convert_state(100, None, 1800)['status'] == 'MISSING_DATA'


def test_overflow_rejected():
    data = synthetic_input()
    data['bank_volumes_m3'][0] = 1e308
    assert run(data)['status'] == 'INVALID_INPUT'
