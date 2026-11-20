"""DEC-007 development verification, independent exact dual proof and HiGHS.

The reference checks never import the production solver or feasibility routine.
The candidate is exercised through its actual JSON CLI.
"""
from fractions import Fraction as F
from pathlib import Path
import copy
import hashlib
import json
import subprocess
import sys
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[1]


def certify(data, result, manifest):
    x = [[F(value) for value in row] for row in result['matrix_exact']]
    s = list(map(lambda value: F(str(value)), data['bank_volumes_m3']))
    b = list(map(lambda value: F(str(value)), data['compacted_volumes_m3']))
    rho = list(map(lambda value: F(str(value)), data['bank_dry_density_kg_m3']))
    target = list(map(lambda value: F(str(value)), data['compacted_dry_density_kg_m3']))
    prices = [[F(str(data['haul_rate_cny_per_m3_km'][i][j])) * F(str(data['distance_km'][i][j]))
               for j in range(3)] for i in range(3)]
    row_residuals = [sum(x[i]) - s[i] for i in range(3)]
    mass_residuals = [sum(rho[i] * x[i][j] for i in range(3)) - target[j] * b[j] for j in range(3)]
    assert all(value == 0 for value in row_residuals + mass_residuals)
    assert all(value >= 0 for row in x for value in row)
    assert all(x[i][j] == 0 for i in range(3) for j in range(3) if not data['allowed'][i][j])
    u = list(map(F, manifest['independent_proof']['source_potentials_cny_per_bank_m3']))
    v = list(map(F, manifest['independent_proof']['destination_potentials_cny_per_kg']))
    reduced = [[prices[i][j] - u[i] - rho[i] * v[j] for j in range(3)] for i in range(3)]
    assert all(value >= 0 for row in reduced for value in row)
    primal = sum(prices[i][j] * x[i][j] for i in range(3) for j in range(3))
    dual = sum(u[i] * s[i] for i in range(3)) + sum(v[j] * target[j] * b[j] for j in range(3))
    assert primal == dual == F(result['objective_exact'])
    assert all(x[i][j] * reduced[i][j] == 0 for i in range(3) for j in range(3))
    return {'primal_exact': str(primal), 'dual_exact': str(dual), 'gap_exact': str(primal-dual),
            'supply_residuals_exact_m3': list(map(str, row_residuals)),
            'demand_residuals_exact_kg': list(map(str, mass_residuals)),
            'reduced_costs_exact': [[str(value) for value in row] for row in reduced],
            'u_cny_per_bank_m3': list(map(str, u)), 'v_cny_per_kg': list(map(str, v))}


def verify():
    manifest = json.loads((ROOT/'engineering/teaching_case_v1.json').read_text(encoding='utf8'))
    source = ROOT/manifest['input_file']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == manifest['input_sha256']
    data = json.loads(source.read_text(encoding='utf8'))
    original = copy.deepcopy(data)
    assert data['dataset_kind'] == 'synthetic'
    assert all(item['origin'] == 'SYNTHETIC' for item in manifest['parameter_sources'].values())
    command = [sys.executable, '-X', 'utf8', '-B', '-m', 'seos.main', '--input', str(source)]
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding='utf8')
    result = json.loads(process.stdout)
    assert process.returncode == 0 and not process.stderr and result['status'] == 'OPTIMAL'
    assert result['dataset_kind'] == 'synthetic' and result['currency_result'] is None
    proof = certify(data, result, manifest)
    # A second independent formulation uses natural-volume variables directly.
    rho = data['bank_dry_density_kg_m3']
    equations = [[int(k//3 == i) for k in range(9)] for i in range(3)]
    equations += [[rho[k//3] if k%3 == j else 0 for k in range(9)] for j in range(3)]
    rhs = data['bank_volumes_m3'] + [data['compacted_dry_density_kg_m3'][j]*data['compacted_volumes_m3'][j] for j in range(3)]
    costs = [data['haul_rate_cny_per_m3_km'][i][j]*data['distance_km'][i][j] for i in range(3) for j in range(3)]
    reference = linprog(costs, A_eq=equations, b_eq=rhs,
                        bounds=[(0, None if data['allowed'][i][j] else 0) for i in range(3) for j in range(3)], method='highs')
    assert reference.success and abs(reference.fun - float(F(proof['primal_exact']))) <= 1e-9
    assert original == data
    return {'status': 'PASS', 'scope': 'Developer evidence, not Antigravity acceptance',
            'case_id': manifest['case_id'], 'input_sha256': manifest['input_sha256'],
            'input': data, 'command': command, 'cwd': str(ROOT), 'exit_code': process.returncode,
            'stdout': process.stdout, 'stderr': process.stderr, 'exact_certificate': proof,
            'highs': {'success': bool(reference.success), 'objective': float(reference.fun),
                      'matrix': reference.x.reshape(3,3).tolist()},
            'formal_teaching_acceptance': 'NOT TESTED', 'real_engineering': 'BLOCKED'}


if __name__ == '__main__':
    result = verify()
    out = ROOT/'verification/dec007/TEACHING_CASE_PROOF.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
    print(json.dumps({'status': result['status'], 'certificate': result['exact_certificate']}, ensure_ascii=False))
