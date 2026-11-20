"""Engineering input gate. Missing physical or pricing data block calculation."""
from math import isfinite
from seos.validation import number, failure, validate_json_tree
from seos.modules.earthwork_calculator import convert_state


def prepare(data):
    """Prepare source/destination masses and per-volume route prices.

    Rates retain CNY/(m3 km). Billing volume state must be explicitly supplied.
    This gate does not approve material compatibility, borrow or disposal rules.
    """
    try:
        validate_json_tree(data)
        if not isinstance(data, dict):
            raise ValueError('Engineering input must be an object')
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return dict(failure(error), currency_result=None)
    required = ['bank_volumes_m3', 'compacted_volumes_m3',
                'bank_dry_density_kg_m3', 'compacted_dry_density_kg_m3',
                'haul_rate_cny_per_m3_km', 'distance_km', 'distance_source',
                'density_source', 'billing_volume_state']
    missing = [key for key in required if data.get(key) is None or data.get(key) == '']
    for key in required:
        value = data.get(key)
        if isinstance(value, list):
            for i, item in enumerate(value):
                if item is None:
                    missing.append(f'{key}[{i}]')
                elif isinstance(item, list):
                    missing.extend(f'{key}[{i}][{j}]' for j, cell in enumerate(item) if cell is None)
    if missing:
        return {'status': 'MISSING_DATA', 'missing_fields': missing,
                'decisions': ['DEC-004', 'DEC-005', 'DEC-006'], 'currency_result': None}
    vectors = ['bank_volumes_m3', 'compacted_volumes_m3',
               'bank_dry_density_kg_m3', 'compacted_dry_density_kg_m3']
    matrices = ['haul_rate_cny_per_m3_km', 'distance_km']
    try:
        if any(len(data[key]) != 3 for key in vectors):
            raise ValueError('Engineering prototype requires three supply and three demand nodes')
        if any(len(data[key]) != 3 or any(len(row) != 3 for row in data[key]) for key in matrices):
            raise ValueError('Rate and distance matrices must be 3x3')
        missing_cells = []
        for key in vectors:
            missing_cells.extend(f'{key}[{i}]' for i, value in enumerate(data[key]) if value is None)
        for key in matrices:
            missing_cells.extend(f'{key}[{i}][{j}]' for i, row in enumerate(data[key]) for j, value in enumerate(row) if value is None)
        if missing_cells:
            return {'status': 'MISSING_DATA', 'missing_fields': missing_cells, 'currency_result': None}
        values = [value for key in vectors for value in data[key]]
        values += [value for key in matrices for row in data[key] for value in row]
        for value in values:
            number(value)
        if any(value <= 0 for key in vectors[2:] for value in data[key]):
            raise ValueError('Dry densities must be positive')
        if data['billing_volume_state'] != 'bank':
            raise ValueError('DEC-006 requires bank volume billing')
        if any(not isinstance(data[key], str) or not data[key].strip() for key in ['density_source', 'distance_source']):
            raise ValueError('Density and distance provenance must be nonempty strings')
    except (TypeError, ValueError, OverflowError) as error:
        return dict(failure(error), currency_result=None)
    supply_mass = [convert_state(v, rho, rho) for v, rho in zip(data['bank_volumes_m3'], data['bank_dry_density_kg_m3'])]
    demand_mass = [convert_state(v, rho, rho) for v, rho in zip(data['compacted_volumes_m3'], data['compacted_dry_density_kg_m3'])]
    prices = [[rate * distance for rate, distance in zip(rates, distances)]
              for rates, distances in zip(data['haul_rate_cny_per_m3_km'], data['distance_km'])]
    if any(result['status'] != 'CALCULATED' for result in supply_mass + demand_mass) or any(not isfinite(v) for row in prices for v in row):
        return {'status': 'INVALID_INPUT', 'message': 'Calculation exceeds finite numeric range', 'currency_result': None}
    supply = [result['dry_mass_kg'] for result in supply_mass]
    demand = [result['dry_mass_kg'] for result in demand_mass]
    if not all(isfinite(v) for v in [sum(supply), sum(demand), sum(supply)-sum(demand)]):
        return {'status': 'NUMERIC_ERROR', 'error_code': 'AGGREGATE_RANGE', 'currency_result': None}
    return {'status': 'READY_FOR_MODEL_REVIEW', 'supply_dry_mass_kg': supply,
            'demand_dry_mass_kg': demand, 'dry_mass_gap_kg': sum(supply) - sum(demand),
            'route_price_cny_per_billed_m3': prices,
            'billing_volume_state': data['billing_volume_state'], 'currency_result': None,
            'provenance': {key: data[key] for key in ['density_source', 'distance_source']},
            'pending': ['material compatibility and loss policy', 'mass-variable LP and billed-volume mapping review'],
            'decisions': ['DEC-004', 'DEC-005', 'DEC-006']}
