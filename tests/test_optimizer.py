import json
import random
from pathlib import Path
import pytest
from scipy.optimize import linprog
from seos.modules.optimizer import solve

DATA = json.loads(Path('data/earthwork_example.json').read_text())


@pytest.mark.parametrize('seed', range(20))
def test_independent_highs(seed):
    rng = random.Random(seed)
    witness = [[rng.randint(0, 20) for _ in range(3)] for _ in range(3)]
    supply = [sum(row) for row in witness]
    demand = [sum(witness[i][j] for i in range(3)) for j in range(3)]
    costs = [[rng.random()*20 for _ in range(3)] for _ in range(3)]
    result = solve(supply, demand, costs)
    equations = [[int(k//3 == i) for k in range(9)] for i in range(3)]
    equations += [[int(k%3 == j) for k in range(9)] for j in range(3)]
    reference = linprog(sum(costs, []), A_eq=equations, b_eq=supply+demand, bounds=(0,None), method='highs')
    assert reference.success
    assert result['status']=='OPTIMAL'
    assert result['objective']==pytest.approx(reference.fun)
    assert result['max_residual'] < 1e-7


def test_teaching_and_change():
    base=solve(DATA['supply'], DATA['demand'], DATA['costs'])
    assert base['objective']==pytest.approx(778500)
    changed=[row[:] for row in DATA['costs']]
    changed[0][0]=12
    after=solve(DATA['supply'], DATA['demand'], changed)
    assert after['objective']==pytest.approx(936000)
    assert after['matrix']==base['matrix']


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf'), True, '50'])
def test_invalid(value):
    assert solve([value,30000,20000],DATA['demand'],DATA['costs'])['status']=='INVALID_INPUT'


def test_unbalanced():
    assert solve([1,2,3],DATA['demand'],DATA['costs'])['status']=='UNBALANCED'


def test_closed_routes():
    assert solve(DATA['supply'],DATA['demand'],DATA['costs'],[[False]*3 for _ in range(3)])['status']=='INFEASIBLE'


def test_zero():
    assert solve([0]*3,[0]*3,DATA['costs'])['objective']==0


def test_sparse_network():
    result=solve([1]*3,[1]*3,DATA['costs'],[[i==j for j in range(3)] for i in range(3)])
    assert result['status']=='OPTIMAL'
    assert result['objective']==pytest.approx(22.2)
