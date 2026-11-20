import random
import pytest
from scipy.optimize import linprog
from research.model_candidates import convert_by_dry_density, dry_density_from_bulk
from seos.modules.optimizer import solve
from seos.main import run


def test_mass_conversion_round_trip():
    # Synthetic algebra test, not project engineering input.
    forward = convert_by_dry_density(100, 1500, 1800)
    backward = convert_by_dry_density(forward['target_volume_m3'], 1800, 1500)
    assert forward['dry_mass_kg'] == 150000
    assert backward['target_volume_m3'] == pytest.approx(100)
    assert forward['status'] == 'PROVISIONAL'


def test_moisture_percent():
    assert dry_density_from_bulk(1800, 20) == pytest.approx(1500)


@pytest.mark.parametrize('data', [None, [], {}, {'supply': [1, 2, 3]}])
def test_protocol_missing_data(data):
    assert run(data)['status'] == 'INVALID_INPUT'


@pytest.mark.parametrize('density', [0, -1, float('nan'), float('inf'), True])
def test_invalid_density(density):
    with pytest.raises(ValueError):
        convert_by_dry_density(100, density, 1800)


@pytest.mark.parametrize('seed', range(20))
def test_restricted_network_independently(seed):
    rng = random.Random(seed)
    supply = [5, 3, 2]
    demand = [4, 3, 3]
    costs = [[rng.random()*10 for _ in range(3)] for _ in range(3)]
    allowed = [[rng.random() > 0.35 for _ in range(3)] for _ in range(3)]
    actual = solve(supply, demand, costs, allowed)
    constraints = [[int(k//3 == i) for k in range(9)] for i in range(3)]
    constraints += [[int(k%3 == j) for k in range(9)] for j in range(3)]
    bounds = [(0, None) if allowed[k//3][k%3] else (0, 0) for k in range(9)]
    reference = linprog(sum(costs, []), A_eq=constraints, b_eq=supply+demand, bounds=bounds, method='highs')
    if reference.success:
        assert actual['status'] == 'OPTIMAL'
        assert actual['objective'] == pytest.approx(reference.fun)
    else:
        assert reference.status == 2 and actual['status'] == 'INFEASIBLE'
