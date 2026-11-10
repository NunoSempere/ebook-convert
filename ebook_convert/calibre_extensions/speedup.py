"""Python implementation of the parts of calibre's ``speedup`` C extension
that the conversion pipeline uses."""

from __future__ import annotations

import os
import re
from datetime import datetime

O_CLOEXEC = getattr(os, 'O_CLOEXEC', 0)

_xml_illegal = re.compile(
    '[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]|[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]'
)


def clean_xml_chars(s: str) -> str:
    'Remove characters that are illegal in XML 1.0'
    return _xml_illegal.sub('', s)


def barename(tag: str) -> str:
    'The local part of a Clark-notation ``{ns}name`` tag'
    if tag and tag[0] == '{':
        return tag.rpartition('}')[2]
    return tag


def namespace(tag: str) -> str:
    'The namespace of a Clark-notation ``{ns}name`` tag or the empty string'
    if tag and tag[0] == '{':
        return tag[1:].partition('}')[0]
    return ''


def pread_all(fd: int, size: int, offset: int) -> bytes:
    chunks = []
    while size > 0:
        chunk = os.pread(fd, size, offset)
        if not chunk:
            break
        chunks.append(chunk)
        size -= len(chunk)
        offset += len(chunk)
    return b''.join(chunks)


_iso8601 = re.compile(
    r'^\s*(?P<year>[-+]?\d{4,})(?:-?(?P<month>\d{2})(?:-?(?P<day>\d{2}))?)?'
    r'(?:[T\s](?P<hour>\d{2})(?::?(?P<minute>\d{2})(?::?(?P<second>\d{2})(?:[.,](?P<frac>\d+))?)?)?'
    r'\s*(?P<tz>Z|z|[-+]\d{2}(?::?\d{2})?)?)?\s*$'
)


def parse_iso8601(date_string: str) -> tuple[datetime, bool, int]:
    """Parse an ISO 8601 date/time string.

    Returns (naive datetime, timezone_was_specified, utc_offset_in_seconds).
    Raises ValueError for strings that are not ISO 8601 dates.
    """
    m = _iso8601.match(date_string)
    if m is None:
        raise ValueError(f'Not an ISO 8601 date: {date_string!r}')
    g = m.groupdict()
    year = int(g['year'])
    month = int(g['month'] or 1)
    day = int(g['day'] or 1)
    hour = int(g['hour'] or 0)
    minute = int(g['minute'] or 0)
    second = int(g['second'] or 0)
    micro = 0
    if g['frac']:
        micro = int((g['frac'] + '000000')[:6])
    if hour == 24 and minute == 0 and second == 0:
        hour = 0
    year = max(1, min(year, 9999))
    dt = datetime(year, month, day, hour, minute, second, micro)
    tz = g['tz']
    aware = tz is not None
    tzseconds = 0
    if aware and tz not in ('Z', 'z'):
        sign = -1 if tz[0] == '-' else 1
        digits = tz[1:].replace(':', '')
        hh, mm = int(digits[:2]), int(digits[2:4] or 0)
        tzseconds = sign * (hh * 3600 + mm * 60)
    return dt, aware, tzseconds


def set_thread_name(name: str) -> None:
    pass


def utf8_decode(data: bytes) -> str:
    return data.decode('utf-8', 'replace')


def get_num_of_significant_chars(elem) -> int:
    ans = 0
    for text in (elem.text, elem.tail):
        if text:
            ans += len(text.strip())
    return ans
