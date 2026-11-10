"""Python implementation of calibre's ``fast_html_entities`` C extension.

``replace_all_entities(raw, keep_xml_entities=False)`` decodes HTML5 named and
numeric character references in ``raw`` (``str`` or UTF-8 ``bytes``, the same
type is returned).  With ``keep_xml_entities`` the five XML entities
(``&amp; &lt; &gt; &apos; &quot;``) and numeric references to those characters
are left untouched so the result stays well-formed XML.
"""

from __future__ import annotations

import re
from functools import lru_cache
from html.entities import html5 as _html5_table

_ent_pat = re.compile(r'&(#[xX][0-9a-fA-F]+|#[0-9]+|[a-zA-Z][a-zA-Z0-9]*);')

_xml_entities = {'amp', 'lt', 'gt', 'apos', 'quot'}
_xml_chars = {'&', '<', '>', "'", '"'}

# C1 controls decode as windows-1252, as in HTML5, except for the ones
# undefined in windows-1252
_c1 = {}
for _i in range(0x80, 0xA0):
    _c1[_i] = bytes((_i,)).decode('cp1252', 'ignore') or chr(_i)
del _i


@lru_cache(maxsize=None)
def _named_entities() -> dict[str, str]:
    ans = {}
    for k, v in _html5_table.items():
        ans[k.rstrip(';')] = v
    try:
        from ebook_convert.ebooks.html_entities import html5_entities

        ans.update(html5_entities)
    except Exception:
        pass
    return ans


def _decode_numeric(ent: str) -> str:
    try:
        num = int(ent[2:], 16) if ent[1] in 'xX' else int(ent[1:])
    except ValueError:
        return '�'
    if num == 0 or num > 0x10FFFF or 0xD800 <= num <= 0xDFFF:
        return '�'
    if 0x80 <= num <= 0x9F:
        return _c1[num]
    return chr(num)


def _replace(match: re.Match, keep_xml_entities: bool) -> str:
    ent = match.group(1)
    if ent[0] == '#':
        ans = _decode_numeric(ent)
        if keep_xml_entities and ans in _xml_chars:
            return match.group(0)
        return ans
    if keep_xml_entities and ent in _xml_entities:
        return match.group(0)
    if ent in ('apos', 'squot'):
        return "'"
    return _named_entities().get(ent, match.group(0))


def replace_all_entities(raw, keep_xml_entities: bool = False):
    if isinstance(raw, bytes):
        return replace_all_entities(raw.decode('utf-8', 'replace'), keep_xml_entities).encode('utf-8')
    if '&' not in raw:
        return raw
    return _ent_pat.sub(lambda m: _replace(m, keep_xml_entities), raw)
