"""Shared strict JSON protocol for CLI and generated browser teaching page."""
import argparse
import json
from pathlib import Path
from seos.modules.optimizer import solve
from seos.validation import validate_json_tree, failure, InputError


def run_teaching(data):
    try:
        validate_json_tree(data)
        if not isinstance(data, dict) or data.get('mode', 'teaching') != 'teaching':
            raise ValueError('Supported teaching mode required')
        if any(key not in data for key in ['supply', 'demand', 'costs']):
            raise ValueError('supply, demand and costs are required')
        return solve(data['supply'], data['demand'], data['costs'], data.get('allowed'))
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return failure(error)


def run(data):
    try:
        validate_json_tree(data)
        if isinstance(data, dict) and data.get('mode') == 'engineering':
            from seos.engineering import prepare
            if data.get('action', 'prepare') == 'optimize':
                from seos.engineering_optimizer import optimize_engineering
                return optimize_engineering(data)
            if data.get('action', 'prepare') != 'prepare':
                raise ValueError('Unsupported engineering action')
            return prepare(data)
        result = run_teaching(data)
        if result['status'] == 'INVALID_INPUT':
            return result
        return {'schema_version': '0.3', 'status': result['status'], 'input': data, 'optimizer': result,
                'engineering_modules': {'status': 'BLOCKED', 'decisions': ['DEC-004', 'DEC-005', 'Q-07'], 'scope': 'physical data still required'}}
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return failure(error)


def run_browser(data):
    result = run(data)
    return result.get('optimizer', result)


def parse_json_number(text):
    from decimal import Decimal
    value = float(text)
    mantissa = text.lower().split('e')[0]
    if value == 0 and any(c in '123456789' for c in mantissa):
        raise InputError('JSON numeric underflow is unsupported', 'NUMERIC_RANGE')
    from seos.validation import number
    number(abs(value), 'JSON number')
    if Decimal(text) != Decimal(str(value)):
        raise InputError('JSON decimal cannot roundtrip through supported float input', 'NUMERIC_PRECISION')
    return value


def reject_nonfinite(value):
    raise ValueError(f'Nonstandard JSON numeric constant: {value}')


def main():
    parser = argparse.ArgumentParser(description='SEOS 3x3 teaching LP')
    parser.add_argument('--input', type=Path, default=Path(__file__).resolve().parents[1]/'data/earthwork_example.json')
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding='utf-8-sig'), parse_constant=reject_nonfinite, parse_float=parse_json_number)
        result = run(data)
        payload = json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError) as error:
        result = failure(error)
        payload = json.dumps(result, ensure_ascii=True, allow_nan=False)
    print(payload)
    return 0 if result['status'] == 'OPTIMAL' else 2


if __name__ == '__main__':
    raise SystemExit(main())
