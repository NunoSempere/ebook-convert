# License: GPLv3 Copyright: 2010, Kovid Goyal <kovid@kovidgoyal.net>
# Pure-Python replacement for calibre/utils/icu.py (ebook-convert).
#
# Calibre implements these string functions on top of the ICU C library.  We
# have no C extensions, so collation is approximated with Unicode
# normalisation and case folding from the standard library:
#
# - primary strength ignores case and accents (NFKD, combining marks removed,
#   casefold);
# - secondary strength ignores case only;
# - tertiary strength (the default) also distinguishes case, lower first
#   unless ``upper_first`` is set;
# - numeric collation sorts digit runs by value, so "chapter 2" < "chapter 10".
#
# Sorting is locale independent: the ``locale_for_sorting`` tweak and language
# specific rules (Swedish v/w, Spanish ch, Turkish i ...) are not honoured.
# Sort keys are tuples, not bytes.  ``visual_to_logical``/``logical_to_visual``
# (bidi reordering, used only by the PDF input heuristics) are identity
# functions.

from __future__ import annotations

import re
import sys
import threading
import unicodedata
from functools import lru_cache

from ebook_convert.utils.config_base import prefs, tweaks

UCOL_PRIMARY, UCOL_SECONDARY, UCOL_TERTIARY = 0, 1, 2
UCOL_ALTERNATE_HANDLING = UCOL_SHIFTED = UCOL_NON_IGNORABLE = None

_locale: str | None = None
_cmap: dict = {}
icu_unicode_version = unicodedata.unidata_version
is_narrow_build = False

_digits = re.compile(r'(\d+)')
_punct = re.compile(r'[\s\W_]+', re.UNICODE)


@lru_cache(maxsize=4096)
def _primary(s: str) -> str:
    'Case and accent insensitive form of s'
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).casefold()


@lru_cache(maxsize=4096)
def _secondary(s: str) -> str:
    'Case insensitive form of s, accents preserved'
    return unicodedata.normalize('NFD', s).casefold()


def _numeric_tokens(s: str) -> tuple:
    ans = []
    for i, part in enumerate(_digits.split(s)):
        if not part:
            continue
        if i % 2:  # a digit run
            ans.append((1, int(part), len(part)))
        else:
            ans.append((2, part))
    return tuple(ans)


class Collator:
    def __init__(self, locale: str = 'en', strength: int = UCOL_TERTIARY, numeric: bool = False, upper_first: bool = False, ignore_punct: bool = False) -> None:
        self.locale = locale
        self.strength = strength
        self.numeric = numeric
        self.upper_first = upper_first
        self.ignore_punct = ignore_punct

    def clone(self) -> Collator:
        return Collator(self.locale, self.strength, self.numeric, self.upper_first, self.ignore_punct)

    def set_attribute(self, *a) -> None:
        pass

    def contractions(self) -> tuple:
        return ()

    # key functions {{{
    def _norm(self, s: str) -> str:
        if self.ignore_punct:
            s = _punct.sub('', s)
        return s

    def _primary_key(self, s: str):
        p = _primary(self._norm(s))
        return _numeric_tokens(p) if self.numeric else p

    def sort_key(self, s):
        if not isinstance(s, str):
            raise TypeError('sort_key needs a str')
        s = self._norm(s)
        p = _primary(s)
        pk = _numeric_tokens(p) if self.numeric else p
        if self.strength == UCOL_PRIMARY:
            return (pk,)
        sk = _secondary(s)
        if self.strength == UCOL_SECONDARY:
            return (pk, sk)
        # tertiary: distinguish case, lower first by default (as ICU does)
        case_key = tuple((not c.islower()) if self.upper_first is False else (not c.isupper()) for c in unicodedata.normalize('NFD', s) if c.isalpha())
        return (pk, sk, case_key)

    def collation_order(self, s):
        if not isinstance(s, str):
            raise TypeError('collation_order needs a str')
        p = _primary(s)
        if not p:
            return (0, 0)
        return (ord(p[0]), 1)

    # }}}

    # two argument functions {{{
    def strcmp(self, a, b) -> int:
        if not isinstance(a, str) or not isinstance(b, str):
            raise TypeError('strcmp needs str arguments')
        ka, kb = self.sort_key(a), self.sort_key(b)
        return (ka > kb) - (ka < kb)

    def _fold(self, s: str) -> str:
        if self.strength == UCOL_PRIMARY:
            return _primary(self._norm(s))
        if self.strength == UCOL_SECONDARY:
            return _secondary(self._norm(s))
        return self._norm(s)

    def find(self, pattern, source) -> tuple[int, int]:
        'Return (position, length) of pattern in source or (-1, -1)'
        if not isinstance(pattern, str) or not isinstance(source, str):
            raise TypeError('find needs str arguments')
        fp, fs = self._fold(pattern), self._fold(source)
        if len(fs) == len(source):
            pos = fs.find(fp)
            return (pos, len(pattern)) if pos > -1 else (-1, -1)
        # folding changed the length; fall back to a search over prefixes
        for i in range(len(source)):
            for j in range(i + 1, len(source) + 1):
                if self._fold(source[i:j]) == fp:
                    return i, j - i
        return -1, -1

    def contains(self, pattern, source) -> bool:
        if not isinstance(pattern, str) or not isinstance(source, str):
            raise TypeError('contains needs str arguments')
        return self._fold(pattern) in self._fold(source)

    def startswith(self, a, b) -> bool:
        'True if a starts with b'
        if not isinstance(a, str) or not isinstance(b, str):
            raise TypeError('startswith needs str arguments')
        return self._fold(a).startswith(self._fold(b))

    # }}}


class ThreadLocalCollatorCache(threading.local):
    def __init__(self) -> None:
        self.cache: dict = {}


thread_local_collator_cache = ThreadLocalCollatorCache()


def collator(strength=None, numeric=None, ignore_alternate_chars=None, upper_first=None) -> Collator:
    global _locale
    if _locale is None:
        if tweaks.get('locale_for_sorting'):
            _locale = tweaks['locale_for_sorting']
        else:
            from ebook_convert.utils.localization import bcp47_locale_name

            _locale = bcp47_locale_name()
    key = strength, numeric, ignore_alternate_chars, upper_first
    ans = thread_local_collator_cache.cache.get(key)
    if ans is None:
        ans = Collator(_locale)
        if strength is not None:
            ans.strength = strength
        if numeric is not None:
            ans.numeric = numeric
        if upper_first is not None:
            ans.upper_first = upper_first
        if ignore_alternate_chars is not None:
            ans.ignore_punct = bool(ignore_alternate_chars)
        thread_local_collator_cache.cache[key] = ans
    return ans


def change_locale(locale: str | None = None) -> None:
    global _locale
    _locale = locale
    thread_local_collator_cache.cache.clear()


def primary_collator() -> Collator:
    'Ignores case differences and accented chars'
    return collator(strength=UCOL_PRIMARY)


def primary_collator_without_punctuation() -> Collator:
    'Ignores space and punctuation and case differences and accented chars'
    return collator(strength=UCOL_PRIMARY, ignore_alternate_chars=True)


def sort_collator() -> Collator:
    'Ignores case differences and recognizes numbers in strings (if the tweak is set)'
    return collator(strength=UCOL_SECONDARY, numeric=prefs['numeric_collation'])


def non_numeric_sort_collator() -> Collator:
    'Ignores case differences only'
    return collator(strength=UCOL_SECONDARY, numeric=False)


def numeric_collator() -> Collator:
    'Uses natural sorting for numbers inside strings so something2 will sort before something10'
    return collator(strength=UCOL_SECONDARY, numeric=True)


def case_sensitive_collator() -> Collator:
    'Always sorts upper case letter before lower case'
    return collator(numeric=prefs['numeric_collation'], upper_first=True)


def make_sort_key_func(collator_function, func_name='sort_key'):
    def sort_key(a):
        func = getattr(collator_function(), func_name)
        try:
            return func(a)
        except TypeError:
            if isinstance(a, bytes):
                try:
                    a = a.decode(sys.getdefaultencoding())
                except ValueError:
                    return a
                return func(a)
        return () if func_name == 'sort_key' else (0, 0)

    sort_key.__name__ = func_name
    return sort_key


def make_two_arg_func(collator_function, func_name='strcmp'):
    def two_args(a, b):
        func = getattr(collator_function(), func_name)
        try:
            return func(a, b)
        except TypeError:
            if isinstance(a, bytes):
                a = a.decode(sys.getdefaultencoding(), 'replace')
            elif a is None:
                a = ''
            if isinstance(b, bytes):
                b = b.decode(sys.getdefaultencoding(), 'replace')
            elif b is None:
                b = ''
            return func(a, b)

    two_args.__name__ = func_name
    return two_args


def _title_case(x: str) -> str:
    out = []
    start = True
    for c in x:
        if c.isalpha():
            out.append(c.upper() if start else c.lower())
            start = False
        elif c.isdigit() or c in "'’":
            out.append(c)
            start = False
        else:
            out.append(c)
            start = True
    return ''.join(out)


def make_change_case_func(func, name):
    def change_case(x):
        if isinstance(x, bytes):
            try:
                x = x.decode(sys.getdefaultencoding())
            except ValueError:
                return x
        return func(x)

    change_case.__name__ = name
    return change_case


# ################ The string functions ########################################
sort_key = make_sort_key_func(sort_collator)
numeric_sort_key = make_sort_key_func(numeric_collator)
primary_sort_key = make_sort_key_func(primary_collator)
case_sensitive_sort_key = make_sort_key_func(case_sensitive_collator)
collation_order = make_sort_key_func(sort_collator, 'collation_order')
collation_order_for_partitioning = make_sort_key_func(non_numeric_sort_collator, 'collation_order')

strcmp = make_two_arg_func(sort_collator)
case_sensitive_strcmp = make_two_arg_func(case_sensitive_collator)
primary_strcmp = make_two_arg_func(primary_collator)
upper = make_change_case_func(str.upper, 'upper')
lower = make_change_case_func(str.lower, 'lower')
title_case = make_change_case_func(_title_case, 'title_case')


def capitalize(x: str) -> str:
    try:
        return upper(x[0]) + lower(x[1:])
    except (IndexError, TypeError, AttributeError):
        return x


def swapcase(x: str) -> str:
    return x.swapcase()


swap_case = swapcase

find = make_two_arg_func(collator, 'find')
primary_find = make_two_arg_func(primary_collator, 'find')
primary_no_punc_find = make_two_arg_func(primary_collator_without_punctuation, 'find')
contains = make_two_arg_func(collator, 'contains')
primary_contains = make_two_arg_func(primary_collator, 'contains')
primary_no_punc_contains = make_two_arg_func(primary_collator_without_punctuation, 'contains')


@lru_cache(maxsize=64)
def ascii_primary_no_punc_matcher(query: str):
    if not query.isascii():
        return None
    table = {ord(c): None for c in ' \t\n\r\x0b\x0c!"#$%&\'()*+,-./:;<=>?@[\\]^_`{|}~'}
    q = query.lower().translate(table)
    if not q:
        return None

    def matcher(text: str) -> bool:
        return q in text.lower().translate(table)

    return matcher


startswith = make_two_arg_func(collator, 'startswith')
primary_startswith = make_two_arg_func(primary_collator, 'startswith')
safe_chr = chr


def ord_string(s: str) -> tuple[int, ...]:
    return tuple(map(ord, s))


def word_prefix_find(haystack: str, needle: str) -> int:
    'Position of needle at the start of a word in haystack, or -1'
    h, n = _primary(haystack), _primary(needle)
    if not n:
        return -1
    for m in re.finditer(r'\b' + re.escape(n), h):
        return m.start()
    return -1


def character_name(string) -> str | None:
    try:
        return unicodedata.name(str(string)[0]) or None
    except (TypeError, ValueError, KeyError, IndexError):
        pass


def character_name_from_code(code: int) -> str:
    try:
        return unicodedata.name(chr(code)) or ''
    except (TypeError, ValueError, KeyError):
        return ''


def normalize(text, mode: str = 'NFC') -> str:
    return unicodedata.normalize(mode, str(text))


def contractions(col=None) -> frozenset:
    return frozenset()


def partition_by_first_letter(items, reverse: bool = False, key=lambda x: x):
    # Build a list of 'equal' first letters by noticing changes
    # in the 'ordinal' for the first letter.
    from collections import OrderedDict

    items = sorted(items, key=lambda x: sort_key(key(x)), reverse=reverse)
    ans = OrderedDict()
    last_c, last_ordnum = ' ', 0
    for item in items:
        c = upper(key(item) or ' ')
        ordnum, ordlen = collation_order(c)
        if last_ordnum != ordnum:
            last_c = c[0:1]
            last_ordnum = ordnum
        try:
            ans[last_c].append(item)
        except KeyError:
            ans[last_c] = [item]
    return ans


# Return the number of unicode codepoints in a string
string_length = len


def utf16_length(s: str) -> int:
    return len(s.encode('utf-16-le')) // 2


def remove_accents(txt: str) -> str:
    return unicodedata.normalize('NFKC', ''.join(c for c in unicodedata.normalize('NFKD', txt) if not unicodedata.combining(c)))


remove_accents_icu = remove_accents_regex = remove_accents


def visual_to_logical(text: str, want_map: bool = False):
    '''
    ICU's bidi reordering is not available; text is returned unchanged.
    '''
    if want_map:
        return text, tuple(range(len(text)))
    return text


def logical_to_visual(text: str, want_map: bool = False):
    if want_map:
        return text, tuple(range(len(text)))
    return text
