import json
from pathlib import Path

import pytest

from seos.g2 import run
from seos.report_analysis import analyze, analyze_json
from test_g2 import natural_lp

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def report_case():
    return json.loads((ROOT / "data/g2_teaching.json").read_text(encoding="utf8"))


def test_sweep_uses_same_lp_and_keeps_original(report_case):
    result = analyze(report_case)
    plan = result["modules"]["M3"]
    assert result["modules"] == run(report_case)["modules"]
    for point in result["sensitivity"]["points"]:
        data = report_case["transport"]
        rates = [row.copy() for row in data["haul_rate_cny_per_m3_km"]]
        rates[2][2] = point["rate"]
        direct = natural_lp(dict(data, haul_rate_cny_per_m3_km=rates), plan["allowed"])
        assert direct.success and point["synthetic_cny"] == pytest.approx(direct.fun)
    assert report_case["transport"]["haul_rate_cny_per_m3_km"][2][2] == 2


def test_disabled_sweep_is_flat(report_case):
    report_case["sensitivity_route"] = [0, 1]
    result = analyze(report_case)
    assert not result["sensitivity"]["route_allowed"]
    assert {p["synthetic_cny"] for p in result["sensitivity"]["points"]} == {160}


def test_loose_ratio_only_affects_conversion(report_case):
    baseline = analyze(report_case)
    for ratio in [1.08, 1.12]:
        report_case["loose_volume_ratio"] = [ratio, None, None]
        report = analyze(report_case)
        assert report["modules"]["M2"]["states"]["bank"][0]["target_volume_m3"] == pytest.approx(10 * ratio)
        for key in ("M1", "M3", "M4", "M5"):
            assert report["modules"][key] == baseline["modules"][key]
        assert report["sensitivity"] == baseline["sensitivity"]
    assert report_case["loose_dry_density_kg_m3"][0] == 800


@pytest.mark.parametrize("key,value", [
    ("loose_volume_ratio", [0, None, None]),
    ("loose_volume_ratio", [True, None, None]),
    ("sensitivity_route", [3, 0]),
    ("sensitivity_route", [True, 0]),
])
def test_bad_report_fields(report_case, key, value):
    report_case[key] = value
    assert analyze(report_case)["status"] == "INVALID_INPUT"


def test_precision_and_real_gate(report_case):
    text = json.dumps(report_case).replace('"discount_pct": 5', '"discount_pct": 5.000000000000000001')
    assert analyze_json(text)["error_code"] == "NUMERIC_PRECISION"
    report_case["dataset"]["kind"] = "real"
    report_case["loose_volume_ratio"] = [0, None, None]
    assert analyze(report_case)["status"] == "SOURCE_REVIEW_REQUIRED"


def test_soil_reference_is_editable_without_invented_physical_effect(report_case):
    baseline = analyze(report_case)
    report_case["soil_reference"] = [
        {"natural_water_pct": 18.5, "optimum_water_pct": 14.2,
         "lab_max_dry_density_kg_m3": 1920, "reported_compaction_ratio": 0.95},
        {}, {},
    ]
    report = analyze(report_case)
    assert report["soil_reference"][0]["water_difference_pp"] == 4.3
    assert report["soil_reference"][0]["reported_compaction_ratio"] == 0.95
    assert report["modules"] == baseline["modules"]
    assert report["sensitivity"] == baseline["sensitivity"]
