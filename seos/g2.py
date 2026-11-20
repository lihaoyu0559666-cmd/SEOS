"""G2 teaching entry point. The existing G0/G1 interface stays available."""
from argparse import ArgumentParser
from fractions import Fraction
import json
from pathlib import Path

from seos.engineering_optimizer import optimize_engineering
from seos.main import parse_json_number, reject_nonfinite
from seos.modules.earthwork_calculator import convert_state
from seos.modules.predictor import project
from seos.modules.resilience_evaluator import evaluate, intersect, mask
from seos.modules.soil_classifier import CLASSES, classify
from seos.validation import InputError, failure, validate_json_tree


def three(values, label):
    if not isinstance(values, list) or len(values) != 3:
        raise InputError(f"{label} requires three entries")
    return values


def link_volumes(transport, loose):
    """Use audited conversions and retain exact mass for downstream checks."""
    groups = {}
    for state in ("bank", "compacted"):
        volumes = three(transport[f"{state}_volumes_m3"], state)
        density = three(transport[f"{state}_dry_density_kg_m3"], state)
        targets = loose if state == "bank" else density
        target_state = "loose" if state == "bank" else "compacted"
        rows = []
        for volume, source, target in zip(volumes, density, targets):
            result = convert_state(volume, source, target)
            if result["status"] != "CALCULATED":
                return {"status": result["status"], "state": state, "detail": result}
            rows.append(dict(result, source_state=state, target_state=target_state,
                             source_volume_m3=volume,
                             dry_mass_exact_kg=str(Fraction(str(volume)) * Fraction(str(source)))))
        groups[state] = rows
    return {"status": "CALCULATED", "states": groups}


def teaching(data):
    result = {"schema_version": "g2.1", "dataset_kind": "synthetic", "currency_result": None,
              "modules": {}}
    modules = result["modules"]
    dataset = data["dataset"]
    for key in ("id", "source"):
        if not isinstance(dataset[key], str) or not dataset[key].strip():
            raise InputError(f"dataset {key} is required")
    result["dataset"] = dataset
    samples = [classify(s) for s in three(data["samples"], "samples")]
    unresolved = next((r["status"] for r in samples if r["status"] != "CLASSIFIED"), None)
    modules["M1"] = {"status": unresolved or "CLASSIFIED", "samples": samples}
    if unresolved:
        return dict(result, status=unresolved)

    policy = data["material_policy"]
    if not isinstance(policy["source"], str) or not policy["source"].strip():
        raise InputError("teaching material policy source is required")
    classes = three(policy["accepted_classes"], "destination class policy")
    if any(not isinstance(group, list) or any(c not in CLASSES for c in group) for group in classes):
        raise InputError("destination class policy contains an unsupported class")
    material = [[s["soil_class"] in group for group in classes] for s in samples]
    modules["M1"].update(material_allowed=material, policy_source=policy["source"])

    transport = data["transport"]
    if not isinstance(transport, dict) or transport.get("dataset_kind") != "synthetic":
        raise InputError("transport must explicitly identify synthetic teaching data")
    modules["M2"] = link_volumes(transport, three(data["loose_dry_density_kg_m3"], "loose density"))
    if modules["M2"]["status"] != "CALCULATED":
        return dict(result, status=modules["M2"]["status"])
    masses = modules["M2"]["states"]
    supply, demand = ([Fraction(r["dry_mass_exact_kg"]) for r in masses[state]]
                      for state in ("bank", "compacted"))

    def optimize(routes):
        return optimize_engineering(dict(transport, allowed=routes))

    roads = mask(transport["allowed"])
    allowed = intersect(material, roads)
    plan = optimize(allowed)
    modules["M3"] = dict(plan, allowed=allowed)
    if plan["status"] != "OPTIMAL":
        return dict(result, status=plan["status"])
    if [sum(Fraction(v) for v in row) * Fraction(str(rho))
        for row, rho in zip(plan["matrix_exact"], transport["bank_dry_density_kg_m3"])] != supply:
        raise InputError("M2 and M3 mass checks disagree", "INTEGRATION_CHECK")
    modules["M4"] = project(sum(supply), sum(demand), data["prediction"])

    risk = data["risk"]
    if not isinstance(risk["source"], str) or not risk["source"].strip():
        raise InputError("risk scenario source is required")
    densities = [Fraction(str(x)) for x in transport["bank_dry_density_kg_m3"]]
    variants = risk["alternatives"]
    if not isinstance(variants, list) or len(variants) > 8:
        raise InputError("at most eight explicit route alternatives are supported")
    evaluations = [{"id": "baseline", "base_synthetic_cny": plan["synthetic_cost_cny"],
                    **evaluate(plan, supply, demand, densities, dict(risk, allowed=allowed), optimize)}]
    ids = {"baseline"}
    for variant in variants:
        name = variant["id"]
        if not isinstance(name, str) or not name.strip() or name in ids:
            raise InputError("alternative ids must be nonempty and unique")
        ids.add(name)
        alternative = intersect(material, mask(variant["allowed"]))
        alt_plan = optimize(alternative)
        if alt_plan["status"] != "OPTIMAL":
            evaluations.append({"id": name, "status": alt_plan["status"]})
            continue
        evaluations.append({"id": name, "base_synthetic_cny": alt_plan["synthetic_cost_cny"],
                            **evaluate(alt_plan, supply, demand, densities,
                                       dict(risk, allowed=alternative), optimize)})
    modules["M5"] = {"status": "EVALUATED", "source": risk["source"], "alternatives": evaluations}
    return dict(result, status="CALCULATED")


def run(data):
    try:
        validate_json_tree(data)
        if not isinstance(data, dict) or data.get("schema_version") != "g2.1":
            raise InputError("g2.1 input required")
        dataset = data.get("dataset")
        if not isinstance(dataset, dict):
            raise InputError("dataset must be an object")
        if dataset.get("kind") == "real":
            return {"status": "SOURCE_REVIEW_REQUIRED", "dataset_kind": "real",
                    "currency_result": None}
        if dataset.get("kind") != "synthetic":
            raise InputError("G2 requires explicit synthetic dataset kind")
        return teaching(data)
    except KeyError as error:
        return {"status": "MISSING_DATA", "message": f"required field {error.args[0]}",
                "currency_result": None}
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return dict(failure(error), currency_result=None)


def main():
    parser = ArgumentParser(description="SEOS G2 integrated teaching pipeline")
    parser.add_argument("--input", type=Path, default=Path(__file__).resolve().parents[1] / "data/g2_teaching.json")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8-sig"),
                          parse_float=parse_json_number, parse_constant=reject_nonfinite)
        result = run(data)
        payload = json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
        result = dict(failure(error), currency_result=None)
        payload = json.dumps(result, ensure_ascii=True, allow_nan=False)
    print(payload)
    return 0 if result["status"] == "CALCULATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
