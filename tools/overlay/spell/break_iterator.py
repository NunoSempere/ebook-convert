"""Pure-Python stand-in for ``calibre.spell.break_iterator``.

Calibre segments text with ICU's ``BreakIterator`` (a C extension).  The
converter only needs sentence boundaries, for the Kobo ``<span>`` markup in
KEPUB output, so this module implements the same rule kepubify uses
(pgaskin/kepubify, ``kepub/kobo.go``): a sentence ends after ``.``, ``!`` or
``?``, optionally followed by one closing quote or an ellipsis, and the
ASCII whitespace that follows.  As with ICU, that trailing whitespace belongs
to the sentence it ends.  Positions are code point offsets into the text.
"""
from __future__ import annotations

import re

_SENTENCE = re.compile(r'.*?[.!?][\'"”’“…]?[ \t\n\r\f\v]+', re.DOTALL)
_WORD = re.compile(r'\w+(?:[\'’-]\w+)*')


def sentence_positions(text: str, lang: str = 'en') -> list[tuple[int, int]]:
    ans: list[tuple[int, int]] = []
    pos = 0
    for m in _SENTENCE.finditer(text):
        ans.append((m.start(), m.end() - m.start()))
        pos = m.end()
    if pos < len(text):
        ans.append((pos, len(text) - pos))
    return ans


def split_into_sentences(text: str, lang: str = 'en') -> tuple[str, ...]:
    return tuple(text[p:p + s] for p, s in sentence_positions(text, lang))


def split_into_words_and_positions(text: str, lang: str = 'en') -> list[tuple[int, int]]:
    return [(m.start(), m.end() - m.start()) for m in _WORD.finditer(text)]


def split_into_words(text: str, lang: str = 'en') -> list[str]:
    return [m.group() for m in _WORD.finditer(text)]


def count_words(text: str, lang: str = 'en') -> int:
    return sum(1 for _ in _WORD.finditer(text))


def index_of(needle: str, haystack: str, lang: str = 'en') -> int:
    ''' Position of needle in haystack as a whole word, or -1 '''
    for m in re.finditer(r'(?<!\w)%s(?!\w)' % re.escape(needle), haystack):
        return m.start()
    return -1
