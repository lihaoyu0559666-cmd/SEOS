"""PROVISIONAL formula experiments. These functions do not approve project data.

Derived from dry-solid mass conservation, no loss, uniform material.
Sources and limitations are documented in engineering_model_review.md.
"""
from math import isfinite
from seos.modules.earthwork_calculator import convert_state


def convert_by_dry_density(volume_m3, source_dry_density_kg_m3, target_dry_density_kg_m3):
    result = convert_state(volume_m3, source_dry_density_kg_m3, target_dry_density_kg_m3)
    if result['status'] != 'CALCULATED':
        raise ValueError(result['message'])
    result['status'] = 'PROVISIONAL'
    return result


def dry_density_from_bulk(bulk_density_kg_m3, water_content_percent):
    values = [bulk_density_kg_m3, water_content_percent]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values):
        raise ValueError('Finite numeric values required')
    if bulk_density_kg_m3 <= 0 or water_content_percent < 0:
        raise ValueError('Positive bulk density and nonnegative water content required')
    return bulk_density_kg_m3 / (1 + water_content_percent / 100)
