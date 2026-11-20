"""Shared report calculations. The five audited modules are imported unchanged."""
from argparse import ArgumentParser
from fractions import Fraction
import json
from pathlib import Path

from seos.engineering_optimizer import optimize_engineering
from seos.g2 import run
from seos.main import parse_json_number, reject_nonfinite
from seos.validation import InputError, failure, number


def sensitivity(data, plan):
    """Repeat the audited LP for one explicit unit-rate sweep."""
    route = data.get("sensitivity_route", [2, 2])
    if (not isinstance(route, list) or len(route) != 2
            or any(type(i) is not int or i not in range(3) for i in route)):
        raise InputError("sensitivity_route must identify a valid 3×3 route (zero based)")
    i, j = route
    transport = data["transport"]
    baseline = transport["haul_rate_cny_per_m3_km"][i][j]
    points = []
    for ratio in (0.5, 0.75, 1, 1.25, 1.5):
        rate = float(Fraction(str(baseline)) * Fraction(str(ratio)))
        if ratio == 1 or baseline == 0 or not plan["allowed"][i][j]:
            point = plan
        else:
            rates = [row.copy() for row in transport["haul_rate_cny_per_m3_km"]]
            rates[i][j] = rate
            point = optimize_engineering(dict(transport, allowed=plan["allowed"],
                                                haul_rate_cny_per_m3_km=rates))
        points.append({"ratio": ratio, "rate": rate, "status": point["status"],
                       "synthetic_cny": point.get("synthetic_cost_cny")})
    return {"route": route, "points": points, "route_allowed": plan["allowed"][i][j]}


def with_loose_ratios(data):
    """Transfer explicit teaching ratios to the audited density-based input."""
    if not isinstance(data, dict) or not isinstance(data.get("dataset"), dict):
        return data
    if data["dataset"].get("kind") != "synthetic" or "loose_volume_ratio" not in data:
        return data
    ratios = data["loose_volume_ratio"]
    if not isinstance(ratios, list) or len(ratios) != 3:
        raise InputError("loose_volume_ratio must have three explicit values or nulls")
    if all(ratio is None for ratio in ratios):
        return data
    transport = data.get("transport")
    if not isinstance(transport, dict):
        raise InputError("transport required for loose volume ratios")
    banks = transport.get("bank_dry_density_kg_m3")
    loose = data.get("loose_dry_density_kg_m3")
    if any(not isinstance(values, list) or len(values) != 3 for values in (banks, loose)):
        raise InputError("three bank and loose density entries are required")
    effective = loose.copy()
    for i, ratio in enumerate(ratios):
        if ratio is not None:
            ratio_value = number(ratio, "loose volume ratio", positive=True)
            bank_value = number(banks[i], "bank dry density", positive=True)
            derived = float(Fraction(str(bank_value)) / Fraction(str(ratio_value)))
            effective[i] = number(derived, "derived loose dry density", positive=True)
    return dict(data, loose_dry_density_kg_m3=effective)


def observations(data):
    """Editable teaching records. These are separate from mass and suitability inputs."""
    references = data.get("soil_reference")
    if references is None:
        return []
    if not isinstance(references, list) or len(references) != 3 or any(
            not isinstance(row, dict) for row in references):
        raise InputError("soil_reference requires one record per source")
    keys = ("natural_water_pct", "optimum_water_pct", "lab_max_dry_density_kg_m3",
            "reported_compaction_ratio")
    records = []
    for i, row in enumerate(references):
        values = {}
        for key in keys:
            raw = row.get(key)
            values[key] = None if raw is None else number(raw, key, positive=key in keys[2:])
        natural, optimum = values[keys[0]], values[keys[1]]
        difference = None if natural is None or optimum is None else float(
            Fraction(str(natural)) - Fraction(str(optimum)))
        records.append(dict(values, source_zone=i + 1, water_difference_pp=difference))
    return records


def analyze(data):
    try:
        effective = with_loose_ratios(data)
        result = run(effective)
        if result["status"] != "CALCULATED":
            return result
        return dict(result, soil_reference=observations(effective),
                    sensitivity=sensitivity(effective, result["modules"]["M3"]),
                    effective_loose_dry_density_kg_m3=effective["loose_dry_density_kg_m3"])
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return dict(failure(error), currency_result=None)


def analyze_json(raw):
    try:
        data = json.loads(raw, parse_float=parse_json_number, parse_constant=reject_nonfinite)
        return analyze(data)
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return dict(failure(error), currency_result=None)


def main():
    parser = ArgumentParser(description="SEOS five-module report with unit-rate sensitivity")
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] / "data/g2_teaching.json")
    args = parser.parse_args()
    try:
        result = analyze_json(args.input.read_text(encoding="utf-8-sig"))
    except OSError as error:
        result = failure(error)
    print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "CALCULATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
