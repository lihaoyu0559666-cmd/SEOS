"""Restricted teaching subset of GB/T 50145 table 4.0.8."""
from fractions import Fraction

from seos.validation import InputError, number

CLASSES = ("CL", "CH", "ML", "MH")
TEST_METHODS = ("disk", "cone_76g_30deg_17mm")
FIELDS = (
    "fine_mass_pct", "oversize_mass_pct", "organic_mass_pct",
    "liquid_limit_pct", "plastic_limit_pct", "liquid_limit_method", "source",
)


def classify(sample):
    if not isinstance(sample, dict):
        raise InputError("soil sample must be an object")
    missing = [name for name in FIELDS if sample.get(name) is None]
    if missing:
        return {"status": "MISSING_DATA", "fields": missing}
    if not isinstance(sample["source"], str) or not sample["source"].strip():
        raise InputError("soil sample source is required")
    amounts = {}
    for key in FIELDS[:-2]:
        amounts[key] = Fraction(str(number(sample[key], key)))
    fine, oversize, organic, ll, pl = amounts.values()
    if any(x > 100 for x in (fine, oversize, organic)) or fine + oversize > 100 or pl > ll:
        raise InputError("inconsistent grain, organic or Atterberg test values")
    if (fine <= 75 or oversize != 0 or organic >= 5 or not 0 < ll <= 110
            or sample["liquid_limit_method"] not in TEST_METHODS):
        return {"status": "UNSUPPORTED_MODEL", "reason": "outside reviewed fine-soil teaching subset"}
    pi = ll - pl
    a_line = Fraction(73, 100) * (ll - 20)
    if pi > 60:
        return {"status": "UNSUPPORTED_MODEL", "reason": "outside reviewed plasticity chart"}
    if ll == 50 or pi in (4, 7) or pi == a_line:
        return {"status": "REVIEW_REQUIRED", "reason": "limit value, see clause 4.0.11"}
    if pi >= a_line and 4 <= pi <= 7:
        return {"status": "REVIEW_REQUIRED", "reason": "CL-ML transition requires use review"}
    prefix = "C" if pi >= a_line and pi >= 7 else "M"
    return {
        "status": "CLASSIFIED", "soil_class": prefix + ("H" if ll > 50 else "L"),
        "plasticity_index_pct": float(pi), "a_line_pct": float(a_line),
        "source": sample["source"], "rule": "GB/T 50145-2007 (2026 amendment), table 4.0.8",
        "scope": "synthetic teaching classification",
    }
