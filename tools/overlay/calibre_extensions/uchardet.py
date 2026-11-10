"""Stand-in for calibre's ``uchardet`` C extension, implemented with the
``chardet`` package.  Returns the detected encoding name or ''."""

from __future__ import annotations


def detect(data: bytes) -> str:
    try:
        import chardet
    except ImportError:
        return ''
    ans = chardet.detect(bytes(data))
    enc = (ans or {}).get('encoding') or ''
    if enc and (ans.get('confidence') or 0) < 0.5:
        return ''
    return enc
