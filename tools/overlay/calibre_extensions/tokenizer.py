"""Stand-in for calibre's ``tokenizer`` C extension (tinycss).

The C tokenizer is not available: ``init()`` raises ``RuntimeError`` so that
tinycss falls back to its pure-Python tokenizer.  ``parse_css4_color_string``
(used by tinycss.color4 for MOBI and DOCX output) is implemented here in
Python: CSS Color Level 3 colours via tinycss.color3, plus the Level 4
additions that matter in ebooks (#rgba / #rrggbbaa, space separated rgb() and
hsl() with ``/ alpha``, hwb(), the ``none`` keyword and angle units).  lab(),
lch(), oklab(), oklch() and color() are approximated through sRGB conversion
of their coordinates where feasible and otherwise return None.
"""

from __future__ import annotations

import math
import re


def init(*a, **kw):
    raise RuntimeError('The C tokenizer is not available; using the Python tokenizer')


_hex_re = re.compile(r'^#([0-9a-fA-F]{3,8})$')
_func_re = re.compile(r'^([a-zA-Z]+)\((.*)\)$', re.S)
_num_re = re.compile(r'^[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?$')


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _parse_hex(h: str):
    n = len(h)
    if n in (3, 4):
        h = ''.join(c * 2 for c in h)
        n *= 2
    if n == 6:
        h += 'ff'
    elif n != 8:
        return None
    try:
        r, g, b, a = (int(h[i : i + 2], 16) / 255.0 for i in range(0, 8, 2))
    except ValueError:
        return None
    return (r, g, b, a)


def _number(tok: str, percent_base: float | None = None, none_value: float = 0.0):
    tok = tok.strip()
    if tok == 'none':
        return none_value
    if tok.endswith('%'):
        if not _num_re.match(tok[:-1]):
            return None
        v = float(tok[:-1]) / 100.0
        return v * percent_base if percent_base is not None else v
    if not _num_re.match(tok):
        return None
    return float(tok)


def _angle(tok: str):
    tok = tok.strip().lower()
    if tok == 'none':
        return 0.0
    for unit, factor in (('deg', 1.0), ('grad', 0.9), ('rad', 180.0 / math.pi), ('turn', 360.0)):
        if tok.endswith(unit):
            tok = tok[: -len(unit)]
            if not _num_re.match(tok):
                return None
            return float(tok) * factor
    if not _num_re.match(tok):
        return None
    return float(tok)


def _split_args(body: str):
    body = body.strip()
    alpha = None
    if '/' in body:
        body, _, alpha = body.rpartition('/')
    if ',' in body:
        args = [x.strip() for x in body.split(',')]
        if alpha is None and len(args) == 4:
            alpha = args.pop()
    else:
        args = body.split()
    return args, alpha


def _alpha(tok):
    if tok is None:
        return 1.0
    v = _number(tok, 1.0, none_value=0.0)
    return None if v is None else _clamp(v)


def _hsl_to_rgb(h, s, l):
    h = (h % 360) / 360.0
    s, l = _clamp(s), _clamp(l)
    if s == 0:
        return l, l, l
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def hue(t):
        t %= 1.0
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    return hue(h + 1 / 3), hue(h), hue(h - 1 / 3)


def _linear_to_srgb(c):
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def _xyz_to_rgb(x, y, z):
    r = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    g = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    b = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    return tuple(_clamp(_linear_to_srgb(c)) for c in (r, g, b))


def _lab_to_xyz(L, a, b):
    fy = (L + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    def finv(t):
        return t**3 if t**3 > 0.008856 else (t - 16 / 116) / 7.787

    # D50 white point converted to D65 is skipped; close enough for ebooks
    return 0.9642 * finv(fx), 1.0 * finv(fy), 0.8251 * finv(fz)


def _oklab_to_rgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s
    return tuple(_clamp(_linear_to_srgb(c)) for c in (r, g, bb))


def _parse_function(name: str, body: str):
    args, alpha_tok = _split_args(body)
    a = _alpha(alpha_tok)
    if a is None:
        return None
    if name in ('rgb', 'rgba'):
        if len(args) != 3:
            return None
        vals = [_number(x, 255.0) for x in args]
        if None in vals:
            return None
        return tuple(_clamp(v / 255.0) for v in vals) + (a,)
    if name in ('hsl', 'hsla'):
        if len(args) != 3:
            return None
        h = _angle(args[0])
        s, l = _number(args[1], 1.0), _number(args[2], 1.0)
        if None in (h, s, l):
            return None
        return _hsl_to_rgb(h, s, l) + (a,)
    if name == 'hwb':
        if len(args) != 3:
            return None
        h = _angle(args[0])
        w, b = _number(args[1], 1.0), _number(args[2], 1.0)
        if None in (h, w, b):
            return None
        w, b = _clamp(w), _clamp(b)
        if w + b >= 1:
            g = w / (w + b)
            return (g, g, g, a)
        r, g, bl = _hsl_to_rgb(h, 1.0, 0.5)
        return tuple(c * (1 - w - b) + w for c in (r, g, bl)) + (a,)
    if name in ('lab', 'lch', 'oklab', 'oklch'):
        if len(args) != 3:
            return None
        ok = name.startswith('ok')
        L = _number(args[0], 1.0 if ok else 100.0)
        if L is None:
            return None
        if name.endswith('ch'):
            c = _number(args[1], 0.4 if ok else 150.0)
            h = _angle(args[2])
            if None in (c, h):
                return None
            aa, bb = c * math.cos(math.radians(h)), c * math.sin(math.radians(h))
        else:
            aa = _number(args[1], 0.4 if ok else 125.0)
            bb = _number(args[2], 0.4 if ok else 125.0)
            if None in (aa, bb):
                return None
        if ok:
            return _oklab_to_rgb(L, aa, bb) + (a,)
        return _xyz_to_rgb(*_lab_to_xyz(L, aa, bb)) + (a,)
    if name == 'color':
        if len(args) != 4:
            return None
        space = args[0].lower()
        vals = [_number(x, 1.0) for x in args[1:]]
        if None in vals:
            return None
        if space in ('srgb', 'display-p3', 'a98-rgb', 'prophoto-rgb', 'rec2020'):
            return tuple(_clamp(v) for v in vals) + (a,)
        if space == 'srgb-linear':
            return tuple(_clamp(_linear_to_srgb(v)) for v in vals) + (a,)
        if space in ('xyz', 'xyz-d65', 'xyz-d50'):
            return _xyz_to_rgb(*vals) + (a,)
    return None


def parse_css4_color_string(css_string: str):
    """Returns an (r, g, b, a) tuple with channels in 0..1, the string
    'currentColor', or None if the string is not a valid CSS colour."""
    if not isinstance(css_string, str):
        return None
    s = css_string.strip()
    if not s:
        return None
    low = s.lower()
    if low == 'currentcolor':
        return 'currentColor'
    if low == 'transparent':
        return (0.0, 0.0, 0.0, 0.0)
    m = _hex_re.match(s)
    if m:
        return _parse_hex(m.group(1))
    m = _func_re.match(s)
    if m:
        return _parse_function(m.group(1).lower(), m.group(2))
    from ebook_convert.tinycss.color3 import py_parse_color_string

    try:
        ans = py_parse_color_string(s)
    except Exception:
        return None
    if ans is None or isinstance(ans, str):
        return ans
    return tuple(ans)
