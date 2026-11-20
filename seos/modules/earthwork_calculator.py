"""Explicit SI dry-solid mass conversion under DEC-004.

Applicable to the same material with no dry-solid loss or addition.
No density, compaction ratio or volume state is inferred from teaching data.
"""
from math import isfinite
from seos.validation import number, failure


def convert_state(volume_m3, source_dry_density_kg_m3, target_dry_density_kg_m3):
    values = [volume_m3, source_dry_density_kg_m3, target_dry_density_kg_m3]
    if any(value is None for value in values):
        return {'status': 'MISSING_DATA', 'message': 'Volume and both dry densities are required'}
    try:
        number(volume_m3, 'volume')
        number(source_dry_density_kg_m3, 'source dry density', positive=True)
        number(target_dry_density_kg_m3, 'target dry density', positive=True)
    except (ValueError, TypeError, OverflowError) as error:
        return failure(error)
    mass = volume_m3 * source_dry_density_kg_m3
    target_volume = mass / target_dry_density_kg_m3
    if not isfinite(mass) or not isfinite(target_volume):
        return {'status': 'INVALID_INPUT', 'message': 'Calculation exceeds finite numeric range'}
    return {'status': 'CALCULATED', 'dry_mass_kg': mass, 'target_volume_m3': target_volume,
            'dry_mass_residual_kg': target_volume * target_dry_density_kg_m3 - mass,
            'conditions': ['same material', 'no dry-solid loss or addition'],
            'decision': 'DEC-004'}
