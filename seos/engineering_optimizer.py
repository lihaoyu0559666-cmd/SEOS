"""DEC-004/005/006 restricted mass-conserving LP; synthetic validation only.
No verified real dataset has yet been registered for this project.
"""
from fractions import Fraction
from itertools import combinations
from math import isfinite
from seos.modules.optimizer import linear_solve
from seos.engineering import prepare
from seos.validation import validate_json_tree, failure, InputError


def verify_engineering_plan(x, data, allowed):
    f = lambda v: Fraction(str(v))
    supply = list(map(f, data['bank_volumes_m3']))
    demand = list(map(f, data['compacted_volumes_m3']))
    rb = list(map(f, data['bank_dry_density_kg_m3']))
    rc = list(map(f, data['compacted_dry_density_kg_m3']))
    return (all(v >= 0 for row in x for v in row)
            and all(x[i][j] == 0 for i in range(3) for j in range(3) if not allowed[i][j])
            and all(sum(x[i]) == supply[i] for i in range(3))
            and all(sum(rb[i]*x[i][j] for i in range(3)) == rc[j]*demand[j] for j in range(3)))


def optimize_engineering(data):
    try:
        validate_json_tree(data)
        prepared = prepare(data)
        if prepared['status'] != 'READY_FOR_MODEL_REVIEW':
            return prepared
        if data['billing_volume_state'] != 'bank':
            raise InputError('DEC-006 requires bank volume billing')
        if data.get('dataset_kind') not in ['synthetic', 'real']:
            raise InputError('dataset_kind must explicitly identify synthetic or real')
        for key in ['density_source', 'distance_source', 'rate_source']:
            if not isinstance(data.get(key), str) or not data[key].strip():
                return {'status':'MISSING_DATA', 'missing_fields':[key], 'currency_result':None}
        conditions = data.get('scenario_conditions')
        keys = ['compatible_material', 'zero_dry_mass_loss', 'closed_balance']
        if not isinstance(conditions, dict) or any(conditions.get(k) is not True for k in keys):
            return {'status':'UNSUPPORTED_MODEL', 'error_code':'MODEL_CONDITIONS',
                    'message':'Explicit compatible material, zero dry mass loss and closed balance required; no borrow/disposal', 'currency_result':None}
        # A source label is not source verification. No real project measurements
        # or material suitability records have been supplied and reviewed yet.
        if data['dataset_kind'] == 'real':
            return {'status':'SOURCE_REVIEW_REQUIRED', 'error_code':'UNVERIFIED_PROJECT_DATA',
                    'message':'No verified project dataset registered; provenance and physical conditions need review', 'currency_result':None}
        allowed = data.get('allowed', [[True]*3 for _ in range(3)])
        if not isinstance(allowed,list) or len(allowed)!=3 or any(not isinstance(r,list) or len(r)!=3 or any(type(v) is not bool for v in r) for r in allowed):
            raise InputError('allowed must be a 3x3 boolean matrix')
        f = lambda v: Fraction(str(v))
        rb = list(map(f, data['bank_dry_density_kg_m3']))
        rc = list(map(f, data['compacted_dry_density_kg_m3']))
        s = [f(v)*rho for v,rho in zip(data['bank_volumes_m3'],rb)]
        d = [f(v)*rho for v,rho in zip(data['compacted_volumes_m3'],rc)]
        prices = [[f(data['haul_rate_cny_per_m3_km'][i][j])*f(data['distance_km'][i][j]) for j in range(3)] for i in range(3)]
        if sum(s)!=sum(d):
            return {'status':'UNBALANCED','error_code':'MASS_UNBALANCED','dry_mass_gap_kg':float(sum(s)-sum(d)), 'currency_result':None}
        # y_ij = rho_bank_i*x_ij. Positive rho gives a bijection to a
        # standard mass transportation LP with cost prices_ij/rho_bank_i.
        equations = [[int(k//3==i) for k in range(9)] for i in range(3)]
        equations += [[int(k%3==j) for k in range(9)] for j in range(2)]
        best = None
        for basis in combinations(range(9),5):
            values = linear_solve([[r[k] for k in basis] for r in equations],s+d[:2])
            if values is None or any(v<0 for v in values):
                continue
            y = [Fraction(0)]*9
            for k,v in zip(basis,values):
                y[k]=v
            x = [[y[3*i+j]/rb[i] for j in range(3)] for i in range(3)]
            if not verify_engineering_plan(x,data,allowed):
                continue
            objective = sum(prices[i][j]*x[i][j] for i in range(3) for j in range(3))
            if best is None or objective<best[0]:
                best=objective,x
        if best is None:
            return {'status':'INFEASIBLE','error_code':'INFEASIBLE','currency_result':None}
        score,x = best
        if not verify_engineering_plan(x,data,allowed):
            return {'status':'NUMERIC_ERROR','error_code':'FEASIBILITY_CHECK','currency_result':None}
        matrix = [[float(v) for v in row] for row in x]
        rows = [sum(matrix[i])-data['bank_volumes_m3'][i] for i in range(3)]
        cols = [sum(float(rb[i])*matrix[i][j] for i in range(3))-float(d[j]) for j in range(3)]
        row_tol = [1e-12+1e-12*abs(v) for v in data['bank_volumes_m3']]
        mass_tol = [1e-12+1e-12*abs(float(v)) for v in d]
        if (not all(isfinite(v) for row in matrix for v in row)
            or not isfinite(float(score))
            or any(abs(v)>t for v,t in zip(rows,row_tol))
            or any(abs(v)>t for v,t in zip(cols,mass_tol))):
            return {'status':'NUMERIC_ERROR','error_code':'OUTPUT_PRECISION','currency_result':None}
        return {'status':'OPTIMAL','schema_version':'0.4','dataset_kind':'synthetic',
                'scope':'Synthetic compatible-material zero-loss closed-balance model; no real engineering conclusion',
                'billing_volume_state':'bank','matrix_unit':'m3 bank','objective_unit':'synthetic CNY',
                'matrix':matrix,'matrix_exact':[[str(v) for v in row] for row in x],
                'objective':float(score),'objective_exact':str(score),'synthetic_cost_cny':float(score),
                'currency_result':None,'feasibility_verified':True,
                'bank_volume_residuals_m3':rows,'dry_mass_residuals_kg':cols,
                'route_price_cny_per_bank_m3':[[float(v) for v in row] for row in prices],
                'decisions':['DEC-004','DEC-005','DEC-006']}
    except (ValueError,TypeError,OverflowError,RecursionError) as error:
        return dict(failure(error),currency_result=None)
