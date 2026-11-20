"""Software input domain, independent of engineering parameter approval."""
from math import isfinite
from decimal import Decimal, InvalidOperation

MIN_NONZERO = 1e-12
MAX_INPUT = 1e12


class InputError(ValueError):
    def __init__(self, message, code='INVALID_INPUT'):
        super().__init__(message)
        self.code = code


def number(value, name='value', positive=False):
    if isinstance(value, str):
        # Forms preserve unsupported lexemes as text; numeric strings stay invalid.
        try:
            decimal = Decimal(value)
            floating = float(value)
            if decimal.is_finite() and decimal != 0 and floating == 0:
                raise InputError(f'{name} underflows supported range', 'NUMERIC_RANGE')
            if decimal.is_finite() and isfinite(floating) and Decimal(str(floating)) != decimal:
                raise InputError(f'{name} has unsupported decimal precision', 'NUMERIC_PRECISION')
        except (InvalidOperation, OverflowError):
            pass
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f'{name} must be numeric')
    try:
        valid = isfinite(value)
    except OverflowError:
        valid = False
    if not valid or abs(value) > MAX_INPUT or (value != 0 and abs(value) < MIN_NONZERO):
        raise InputError(f'{name} outside software domain: zero or absolute value 1e-12..1e12', 'NUMERIC_RANGE')
    if value < 0 or (positive and value == 0):
        raise InputError(f'{name} must be ' + ('positive' if positive else 'nonnegative'))
    return value


def validate_json_tree(value):
    if isinstance(value, str):
        try:
            value.encode('utf-8')
        except UnicodeError as error:
            raise InputError('JSON strings must contain valid Unicode scalar values') from error
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        number(abs(value), 'JSON number')
        return
    if isinstance(value, list):
        for item in value:
            validate_json_tree(item)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key in value:
            validate_json_tree(key)
        for item in value.values():
            validate_json_tree(item)
        return
    raise InputError('JSON-compatible containers with string keys required')


def failure(error):
    return {'status': 'INVALID_INPUT', 'error_code': getattr(error, 'code', 'INVALID_INPUT'), 'message': str(error)}
