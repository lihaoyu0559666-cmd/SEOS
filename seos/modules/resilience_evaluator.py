"""Evaluate teaching disruptions using a bipartite cut and the audited LP."""
from fractions import Fraction
from itertools import product

from seos.validation import InputError, number

METRICS = ("worst_service", "horizon_service", "original_plan_service",
           "full_service_share", "cost_retention")


def mask(value):
    if (not isinstance(value, list) or len(value) != 3
            or any(not isinstance(row, list) or len(row) != 3
                   or any(type(x) is not bool for x in row) for row in value)):
        raise InputError("route mask must be a 3x3 boolean matrix")
    return value


def intersect(a, b):
    return [[x and y for x, y in zip(ar, br)] for ar, br in zip(a, b)]


def decimal(value):
    return Fraction(str(value))


def event_service(supply, demand, routes):
    """Exact max flow as the least finite cut of the three-source network."""
    return min(
        sum(supply[i] for i in range(3) if not side[i])
        + sum(demand[j] for j in range(3) if any(side[i] and routes[i][j] for i in range(3)))
        for side in product((False, True), repeat=3)
    )


def evaluate(plan, supply, demand, densities, scenario, reoptimize):
    total = sum(demand)
    if total <= 0:
        raise InputError("risk service requires positive dry-mass demand")
    horizon = number(scenario["horizon_days"], "horizon_days", positive=True)
    base_cost = Fraction(plan["objective_exact"])
    flows = [[Fraction(x) * densities[i] for x in row]
             for i, row in enumerate(plan["matrix_exact"])]
    events = scenario["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= 30:
        raise InputError("one to thirty risk events are required")
    rows = []
    ids = set()
    for event in events:
        name = event["id"]
        if not isinstance(name, str) or not name.strip() or name in ids:
            raise InputError("risk event ids must be nonempty and unique")
        ids.add(name)
        kind = event["kind"]
        if kind not in ("rain", "equipment_failure", "road_closure"):
            raise InputError("unsupported risk event kind")
        days = number(event["duration_days"], "duration_days", positive=True)
        if days > horizon:
            raise InputError("event duration exceeds analysis horizon")
        factors = event["supply_available"]
        if not isinstance(factors, list) or len(factors) != 3:
            raise InputError("three explicit supply availability fractions required")
        if any(number(f, "supply availability") > 1 for f in factors):
            raise InputError("supply availability cannot exceed 1")
        caps = [s * decimal(f) for s, f in zip(supply, factors)]
        routes = intersect(scenario["allowed"], mask(event["routes_open"]))
        served = event_service(caps, demand, routes)
        fixed = sum(sum(flows[i][j] for j in range(3) if routes[i][j]) * decimal(factors[i])
                    for i in range(3))
        coverage = served / total
        existing = fixed / total
        after_recovery = 1 - (1 - coverage) * decimal(days) / decimal(horizon)
        cost = None
        retained = Fraction(0)
        if served == total:
            result = reoptimize(routes)
            if result["status"] != "OPTIMAL":
                raise InputError("risk cut and LP disagree on full service", "INTEGRATION_CHECK")
            cost = Fraction(result["objective_exact"])
            retained = Fraction(1) if cost == 0 else min(Fraction(1), base_cost / cost)
        rows.append((coverage, after_recovery, existing, int(served == total), retained, {
            "id": name, "kind": kind, "duration_days": days, "served_kg_equivalent": float(served),
            "unserved_kg_equivalent": float(total - served), "service": float(coverage),
            "original_plan_service": float(existing), "horizon_service": float(after_recovery),
            "full_service_cost_synthetic_cny": None if cost is None else float(cost),
        }))
    columns = list(zip(*rows))
    values = [min(columns[0]), sum(columns[1]) / len(rows), sum(columns[2]) / len(rows),
              Fraction(sum(columns[3]), len(rows)), sum(columns[4]) / len(rows)]
    weights = scenario.get("weights")
    score = None
    if weights is not None:
        source = scenario.get("weight_source")
        if not isinstance(source, str) or not source.strip() or not isinstance(weights, dict) or set(weights) != set(METRICS):
            raise InputError("explicit weights and their source are required for all five metrics")
        factors = [decimal(number(weights[key], key)) for key in METRICS]
        if sum(factors) != 1:
            raise InputError("weights must sum to exactly one")
        score = float(sum(v * w for v, w in zip(values, factors)))
    return {"status": "EVALUATED", "events": list(columns[5]), "weights": weights,
            "weight_source": scenario.get("weight_source"),
            "metrics": {key: float(v) for key, v in zip(METRICS, values)}, "weighted_score": score}
