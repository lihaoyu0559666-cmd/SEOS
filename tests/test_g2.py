import copy
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest
from scipy.optimize import linprog

from seos.g2 import run
from seos.modules.soil_classifier import classify

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case():
    return json.loads((ROOT / "data/g2_teaching.json").read_text(encoding="utf8"))


def schema(name, data):
    standard = json.loads((ROOT / f"schemas/g2_{name}.schema.json").read_text(encoding="utf8"))
    Draft202012Validator.check_schema(standard)
    Draft202012Validator(standard).validate(data)


@pytest.mark.parametrize("ll,pl,expected", [
    (40, 20, "CL"), (60, 25, "CH"), (35, 25, "ML"), (60, 40, "MH"),
    (25, 20, "REVIEW_REQUIRED"), (50, 20, "REVIEW_REQUIRED"),
    (40, 25.4, "REVIEW_REQUIRED"), (120, 35, "UNSUPPORTED_MODEL"),
])
def test_table_408_reference(case, ll, pl, expected):
    result = classify(dict(case["samples"][0], liquid_limit_pct=ll, plastic_limit_pct=pl))
    assert result.get("soil_class", result["status"]) == expected


@pytest.mark.parametrize("field,value,expected", [
    ("liquid_limit_pct", None, "MISSING_DATA"), ("fine_mass_pct", 49, "UNSUPPORTED_MODEL"),
    ("organic_mass_pct", 5, "UNSUPPORTED_MODEL"), ("oversize_mass_pct", 1, "UNSUPPORTED_MODEL"),
    ("plastic_limit_pct", 41, "INVALID_INPUT"),
])
def test_failed_classification_stops_downstream(case, field, value, expected):
    case["samples"][0][field] = value
    result = run(case)
    assert result["status"] == expected
    assert "M3" not in result.get("modules", {})
    schema("output", result)


def natural_lp(t, allowed):
    densities = t["bank_dry_density_kg_m3"]
    coefficients = [a * b for ar, br in zip(t["haul_rate_cny_per_m3_km"], t["distance_km"])
                    for a, b in zip(ar, br)]
    equations = [[int(k // 3 == i) for k in range(9)] for i in range(3)]
    equations += [[densities[k // 3] if k % 3 == j else 0 for k in range(9)] for j in range(3)]
    rhs = t["bank_volumes_m3"] + [a * b for a, b in
         zip(t["compacted_volumes_m3"], t["compacted_dry_density_kg_m3"])]
    bounds = [(0, None if e else 0) for row in allowed for e in row]
    return linprog(coefficients, A_eq=equations, b_eq=rhs, bounds=bounds, method="highs")


def test_integrated_cli_and_independent_natural_lp(case):
    schema("input", case)
    completed = subprocess.run([sys.executable, "-B", "main.py"], cwd=ROOT, check=True,
                               capture_output=True, text=True, encoding="utf8")
    output = json.loads(completed.stdout)
    assert output == run(case)
    schema("output", output)
    assert output["currency_result"] is None
    modules = output["modules"]
    assert [r["soil_class"] for r in modules["M1"]["samples"]] == ["CL", "CH", "ML"]
    assert modules["M1"]["material_allowed"] == [[True, True, False], [True]*3, [True, False, True]]
    assert [r["target_volume_m3"] for r in modules["M2"]["states"]["bank"]] == [12.5, 25, 37.5]
    assert [r["dry_mass_exact_kg"] for r in modules["M2"]["states"]["bank"]] == ["10000", "30000", "60000"]
    expect = [[True, False, False], [True]*3, [True, False, True]]
    assert modules["M3"]["allowed"] == expect
    assert natural_lp(case["transport"], expect).fun == pytest.approx(160)
    assert modules["M3"]["objective_exact"] == "160"
    assert modules["M3"]["dry_mass_residuals_kg"] == [0, 0, 0]


def test_material_and_road_change_lp(case):
    # Reclassifying source 1 as ML still cannot make a destination policy accept it.
    case["samples"][0]["plastic_limit_pct"] = 30
    case["material_policy"]["accepted_classes"][0].remove("ML")
    result = run(case)
    assert result["modules"]["M1"]["samples"][0]["soil_class"] == "ML"
    assert result["status"] == "INFEASIBLE"
    assert "M5" not in result["modules"]


def test_perturb_cost_recomputed_against_highs(case):
    case["transport"]["haul_rate_cny_per_m3_km"][2][2] = 12
    result = run(case)["modules"]["M3"]
    reference = natural_lp(case["transport"], result["allowed"])
    assert reference.success
    assert result["objective"] == pytest.approx(reference.fun)
    assert result["objective"] != 160


def test_projection_separates_growth_and_discount(case):
    before = run(case)["modules"]["M4"]
    assert before["series"][0]["shortfall_kg"] == 10000
    assert before["series"][1]["cumulative_net_deficit_kg"] == 31000
    assert before["first_shortfall_year"] == 1
    factor = Fraction(20, 21)
    assert before["present_value_synthetic_cny"] == pytest.approx(float(160 * sum(factor**i for i in range(1, 6))))
    case["prediction"].update(years=8, discount_pct=0)
    after = run(case)["modules"]["M4"]
    assert after["series"][:5] == before["series"]
    assert len(after["series"]) == 8
    assert after["present_value_synthetic_cny"] == 1280
    assert after["accuracy_evidence"] == "NOT TESTED"


def reference_service(caps, allowed):
    # Independent direct flow LP, using inequality rows and columns.
    supply_rows = [[int(k // 3 == i) for k in range(9)] for i in range(3)]
    demand_rows = [[int(k % 3 == j) for k in range(9)] for j in range(3)]
    limits = [(0, None if allowed[i][j] else 0) for i in range(3) for j in range(3)]
    lp = linprog([-1] * 9, A_ub=supply_rows + demand_rows,
                 b_ub=caps + [20000, 20000, 60000], bounds=limits, method="highs")
    assert lp.success
    return -lp.fun


def test_risk_independent_flow_and_expected_metrics(case):
    evaluated = run(case)["modules"]["M5"]["alternatives"]
    assert len(evaluated) == 2
    for alternative, enable in zip(evaluated, (False, True)):
        edges = [[True, enable, False], [True]*3, [True, False, True]]
        for i, caps in enumerate(([5000, 30000, 60000], [10000, 15000, 60000], [10000, 30000, 60000])):
            if i == 2:
                edges[0][0] = False
            served = reference_service(caps, edges)
            assert alternative["events"][i]["served_kg_equivalent"] == pytest.approx(served)
    baseline, backup = evaluated
    assert baseline["events"][2]["service"] == 0.9
    assert backup["events"][2]["service"] == 1
    assert backup["events"][2]["full_service_cost_synthetic_cny"] == pytest.approx(
        natural_lp(case["transport"], [[False, True, False], [True]*3, [True, False, True]]).fun
    ) == pytest.approx(240)
    assert backup["metrics"] == pytest.approx(dict(worst_service=.85, horizon_service=.985,
        original_plan_service=.90, full_service_share=1/3, cost_retention=2/9))
    assert backup["weighted_score"] == pytest.approx(sum(backup["metrics"].values()) / 5)
    assert backup["weighted_score"] > baseline["weighted_score"]


def test_no_implicit_weights_or_density(case):
    del case["risk"]["weights"]
    assert run(case)["modules"]["M5"]["alternatives"][0]["weighted_score"] is None
    old = copy.deepcopy(case)
    case["loose_dry_density_kg_m3"][0] = None
    assert run(case)["status"] == "MISSING_DATA"
    assert old["loose_dry_density_kg_m3"][0] == 800
    assert case["loose_dry_density_kg_m3"][0] is None


@pytest.mark.parametrize("path,value", [
    (("prediction", "discount_pct"), True),
    (("prediction", "years"), 11),
    (("risk", "horizon_days"), 1),
    (("risk", "weights", "worst_service"), 0.8),
    (("risk", "events", 0, "supply_available", 0), 1.1),
    (("transport", "allowed", 0, 1), "false"),
])
def test_reject_invalid_assumptions(case, path, value):
    node = case
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    result = run(case)
    assert result["status"] == "INVALID_INPUT"
    schema("output", result)


def test_real_and_relabelled_data_blocked(case):
    case["dataset"]["kind"] = "real"
    real = run(case)
    assert real["status"] == "SOURCE_REVIEW_REQUIRED"
    assert real["currency_result"] is None
    case["dataset"]["kind"] = "synthetic"
    case["transport"]["dataset_kind"] = "real"
    assert run(case)["status"] == "INVALID_INPUT"
