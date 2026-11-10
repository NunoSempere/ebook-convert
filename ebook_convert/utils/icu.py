"""
Pure-Python stand-ins for Calibre's ICU based string utilities.

Calibre does collation, case mapping and Unicode lookups through its ``icu``
C extension.  This project has no C extensions, so the same names are
provided on top of ``str`` and :mod:`unicodedata`.  Sorting is therefore
locale independent (Unicode case folding with accents ignored for the
"primary" variants) rather than following the user's locale collation,
which is accurate enough for grouping index entries and ordering CSS
rules, the only things the converter uses them for.
"""
import re
import unicodedata
from collections import OrderedDict


is_narrow_build = False
_locale = None

UPPER_CASE, LOWER_CASE, TITLE_CASE = 0, 1, 2


def _text(x):
    if x is None:
        return ''
    if isinstance(x, bytes):
        try:
            return x.decode('utf-8')
        except UnicodeDecodeError:
            return x.decode('latin-1')
    return str(x)


def _strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if not unicodedata.combining(c))


# Sort keys {{{

def sort_key(obj):
    ''' Case and accent insensitive key, with case/accents as tie breakers. '''
    s = unicodedata.normalize('NFC', _text(obj))
    # Like ICU's default tertiary strength, lowercase sorts before uppercase.
    return (_strip_accents(s).casefold(), s.casefold(), s.swapcase())


def primary_sort_key(obj):
    ''' Key that ignores case and accents entirely. '''
    return _strip_accents(unicodedata.normalize('NFC', _text(obj))).casefold()


def case_sensitive_sort_key(obj):
    return unicodedata.normalize('NFC', _text(obj))


_num_split = re.compile(r'(\d+)')


def numeric_sort_key(obj):
    ''' Natural sort key: runs of digits compare numerically. '''
    parts = _num_split.split(_text(obj))
    key = []
    for i, part in enumerate(parts):
        if i % 2:
            key.append((0, int(part), ''))
        elif part:
            key.append((1, 0, primary_sort_key(part)))
    return tuple(key)


def collation_order(x):
    ''' (ordinal of the first collation element, its length in characters).
    Used to group strings by their first letter. '''
    s = primary_sort_key(x)
    if not s:
        return 0, 0
    return ord(s[0]), 1

# }}}

# Comparisons {{{

def _cmp(a, b):
    return (a > b) - (a < b)


def strcmp(a, b):
    return _cmp(sort_key(a), sort_key(b))


def case_sensitive_strcmp(a, b):
    return _cmp(case_sensitive_sort_key(a), case_sensitive_sort_key(b))


def primary_strcmp(a, b):
    return _cmp(primary_sort_key(a), primary_sort_key(b))


def _find(needle, haystack, key):
    n, h = key(needle), key(haystack)
    pos = h.find(n)
    return pos, (len(n) if pos > -1 else -1)


def find(needle, haystack):
    ''' (position, length) of needle in haystack ignoring case, or (-1, -1) '''
    return _find(needle, haystack, lambda s: _text(s).casefold())


def primary_find(needle, haystack):
    return _find(needle, haystack, primary_sort_key)


def contains(needle, haystack):
    return find(needle, haystack)[0] > -1


def primary_contains(needle, haystack):
    return primary_find(needle, haystack)[0] > -1


def startswith(a, prefix):
    return _text(a).casefold().startswith(_text(prefix).casefold())


def primary_startswith(a, prefix):
    return primary_sort_key(a).startswith(primary_sort_key(prefix))

# }}}

# Case changes {{{

def upper(x):
    return _text(x).upper()


def lower(x):
    return _text(x).lower()


def title_case(x):
    return _text(x).title()


def capitalize(x):
    try:
        return upper(x[0]) + lower(x[1:])
    except (IndexError, TypeError, AttributeError):
        return x


def swapcase(x):
    return _text(x).swapcase()


def change_case(x, which, locale=None):
    return {UPPER_CASE: upper, LOWER_CASE: lower,
            TITLE_CASE: title_case}[which](x)

# }}}

# Characters {{{

safe_chr = chr


def ord_string(s):
    ''' Tuple of the code points in s. '''
    return tuple(ord(c) for c in _text(s))


def character_name(string):
    try:
        return unicodedata.name(_text(string)[0]) or None
    except (TypeError, ValueError, KeyError, IndexError):
        return None


def character_name_from_code(code):
    try:
        return unicodedata.name(chr(code)) or ''
    except (TypeError, ValueError, KeyError, OverflowError):
        return ''


def normalize(text, mode='NFC'):
    return unicodedata.normalize(mode, _text(text))


def contractions(col=None):
    ''' Collation contractions (multi-letter "letters" like Spanish ch).
    None without ICU. '''
    return frozenset()


def string_length(s):
    ''' Number of code points in s. '''
    return len(_text(s))


def utf16_length(s):
    ''' Number of UTF-16 code units in s. '''
    return len(_text(s).encode('utf-16-le')) // 2

# }}}


def partition_by_first_letter(items, reverse=False, key=lambda x: x):
    ''' Group items by the first letter of key(item), ignoring case and
    accents, in sorted order. Returns an OrderedDict letter -> [items]. '''
    items = sorted(items, key=lambda x: sort_key(key(x)), reverse=reverse)
    ans = OrderedDict()
    last_c, last_ordnum = ' ', 0
    for item in items:
        c = (_text(key(item)) or ' ').upper()
        ordnum, ordlen = collation_order(c)
        if last_ordnum != ordnum:
            last_c = c[0:1]
            last_ordnum = ordnum
        ans.setdefault(last_c, []).append(item)
    return ans
