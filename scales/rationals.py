from fractions import Fraction


def parse_rational(value):
    if not isinstance(value, (int, str, Fraction)) or isinstance(value, bool):
        raise ValueError('expected an exact rational number')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError('expected an exact rational number') from exc


def encode_rational(value):
    # Hexadecimal integer text also handles exact moments of arbitrarily large input integers.
    return f'{value.numerator:#x}/{value.denominator:#x}'


def decode_rational(text):
    numerator, denominator = text.split('/')
    return Fraction(int(numerator, 16), int(denominator, 16))
