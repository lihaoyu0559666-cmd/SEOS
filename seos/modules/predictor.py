"""Annual dry-mass scenario projection with separately discounted payments."""
from fractions import Fraction

from seos.validation import InputError, number


def project(supply, demand, config):
    years = config["years"]
    if type(years) is not int or not 3 <= years <= 10:
        raise InputError("prediction years must be an integer from 3 to 10")
    source = config["source"]
    if not isinstance(source, str) or not source.strip():
        raise InputError("prediction scenario source is required")
    rates = []
    for key in ("supply_growth_pct", "demand_growth_pct", "discount_pct"):
        rate = config[key]
        if type(rate) not in (int, float):
            raise InputError(f"{key} must be numeric")
        number(abs(rate), key)
        if not -100 <= rate <= 100 or (key == "discount_pct" and rate < 0):
            raise InputError(f"{key} outside teaching scenario range")
        rates.append(Fraction(str(rate)) / 100)
    sg, dg, discount = rates
    payment = Fraction(str(number(config["annual_payment_synthetic_cny"], "annual payment")))
    cumulative = Fraction(0)
    pv = Fraction(0)
    series = []
    for year in range(1, years + 1):
        # Baseline totals are year 0. The annual input is applied from year 1.
        s = supply * (1 + sg) ** year
        d = demand * (1 + dg) ** year
        cumulative += d - s
        pv += payment / (1 + discount) ** year
        series.append({"year": year, "supply_kg": float(s), "demand_kg": float(d),
                       "shortfall_kg": float(max(0, d - s)),
                       "cumulative_net_deficit_kg": float(max(0, cumulative))})
    return {
        "status": "PROJECTED", "method": "conditional_compound_scenario", "source": source,
        "year_zero": {"supply_kg": float(supply), "demand_kg": float(demand)},
        "series": series, "first_shortfall_year": next((r["year"] for r in series if r["shortfall_kg"] > 0), None),
        "first_cumulative_deficit_year": next((r["year"] for r in series if r["cumulative_net_deficit_kg"] > 0), None),
        "present_value_synthetic_cny": float(pv), "accuracy_evidence": "NOT TESTED",
    }
