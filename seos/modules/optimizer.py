"""Exact rational teaching transport LP, all six constraints checked separately."""
from fractions import Fraction
from itertools import combinations
from math import isfinite
from seos.validation import number, failure


def linear_solve(matrix, rhs):
    rows = [[Fraction(v) for v in row] + [value] for row, value in zip(matrix, rhs)]
    for col in range(len(rhs)):
        pivot = next((r for r in range(col, len(rhs)) if rows[r][col]), None)
        if pivot is None:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        factor = rows[col][col]
        rows[col] = [v/factor for v in rows[col]]
        for r in range(len(rhs)):
            if r != col:
                factor = rows[r][col]
                rows[r] = [v-factor*p for v, p in zip(rows[r], rows[col])]
    return [row[-1] for row in rows]


def verify_plan(matrix, supply, demand, allowed):
    return (all(v >= 0 for row in matrix for v in row)
            and all(matrix[i][j] == 0 for i in range(3) for j in range(3) if not allowed[i][j])
            and all(sum(matrix[i]) == supply[i] for i in range(3))
            and all(sum(matrix[i][j] for i in range(3)) == demand[j] for j in range(3)))


def solve(supply, demand, costs, allowed=None):
    try:
        if len(supply) != 3 or len(demand) != 3 or len(costs) != 3 or any(len(row) != 3 for row in costs):
            raise ValueError('Only 3x3 inputs supported')
        for value in list(supply)+list(demand)+[v for row in costs for v in row]:
            number(value)
        if allowed is None:
            allowed = [[True]*3 for _ in range(3)]
        if len(allowed) != 3 or any(len(row) != 3 or any(type(v) is not bool for v in row) for row in allowed):
            raise ValueError('allowed must be a 3x3 boolean matrix')
    except (TypeError, ValueError, OverflowError) as error:
        return failure(error)
    s = [Fraction(str(v)) for v in supply]
    d = [Fraction(str(v)) for v in demand]
    c = [Fraction(str(v)) for row in costs for v in row]
    if sum(s) != sum(d):
        return {'status': 'UNBALANCED', 'error_code': 'UNBALANCED', 'message': 'Exact decimal totals differ; no implicit borrow/disposal', 'gap': float(sum(s)-sum(d))}
    equations = [[int(k//3 == i) for k in range(9)] for i in range(3)]
    equations += [[int(k%3 == j) for k in range(9)] for j in range(2)]
    rhs = s+d[:2]
    best = None
    count = 0
    # Enumerate full bases to retain zero-valued degenerate variables.
    # Disabled arcs must be exactly zero, including arbitrarily small flows.
    for basis in combinations(range(9), 5):
        values = linear_solve([[row[k] for k in basis] for row in equations], rhs)
        if values is None or any(v < 0 for v in values):
            continue
        flat = [Fraction(0)]*9
        for k, value in zip(basis, values):
            flat[k] = value
        matrix = [flat[i:i+3] for i in range(0, 9, 3)]
        if not verify_plan(matrix, s, d, allowed):
            continue
        count += 1
        objective = sum(v*price for v, price in zip(flat, c))
        if best is None or objective < best[0]:
            best = objective, matrix
    if best is None:
        return {'status': 'INFEASIBLE', 'error_code': 'INFEASIBLE', 'message': 'No feasible transport plan'}
    objective, exact = best
    if not verify_plan(exact, s, d, allowed):
        return {'status': 'NUMERIC_ERROR', 'error_code': 'FEASIBILITY_CHECK', 'message': 'Final feasibility check failed'}
    matrix = [[float(v) for v in row] for row in exact]
    score = float(objective)
    residuals = [sum(matrix[i])-supply[i] for i in range(3)]
    residuals += [sum(matrix[i][j] for i in range(3))-demand[j] for j in range(3)]
    scale = max(list(supply)+list(demand)+[0])
    tolerance = 1e-12+1e-12*scale
    if not isfinite(score) or not all(isfinite(v) for row in matrix for v in row) or max(map(abs, residuals)) > tolerance:
        return {'status': 'NUMERIC_ERROR', 'error_code': 'OUTPUT_PRECISION', 'message': 'Floating output failed finite/residual check'}
    return {'status': 'OPTIMAL', 'matrix': matrix, 'objective': score, 'objective_exact': str(objective),
            'matrix_exact': [[str(v) for v in row] for row in exact], 'max_residual': max(map(abs, residuals)),
            'feasible_bases': count, 'feasibility_verified': True, 'output_tolerance': tolerance,
            'scope': 'Same-basis abstract teaching model; no engineering monetary conclusion'}
