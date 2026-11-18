import json

from freeze.moments import PairedMoments
from scales.rationals import decode_rational, encode_rational


def encode_seal_moments(moments):
    values = (moments.sx, moments.sy, moments.sxx, moments.syy, moments.sxy)
    return json.dumps([moments.n, *(encode_rational(value) for value in values)], separators=(',', ':'))


def decode_seal_moments(payload):
    n, sx, sy, sxx, syy, sxy = json.loads(payload)
    if type(n) is not int or n < 0:
        raise ValueError('invalid sealed observation count')
    return PairedMoments(n, *(decode_rational(value) for value in (sx, sy, sxx, syy, sxy)))
