"""Python implementation of calibre's ``cPalmdoc`` C extension (PalmDOC /
LZ77 compression used by MOBI and PDB files)."""

from __future__ import annotations


def decompress(data: bytes) -> bytes:
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        c = data[i]
        i += 1
        if c == 0 or 9 <= c <= 0x7F:
            out.append(c)
        elif 1 <= c <= 8:
            out += data[i : i + c]
            i += c
        elif c >= 0xC0:
            out += b' '
            out.append(c ^ 0x80)
        else:
            if i >= n:
                break
            c = (c << 8) | data[i]
            i += 1
            distance = (c & 0x3FFF) >> 3
            length = (c & 7) + 3
            start = len(out) - distance
            if distance <= 0 or start < 0:
                continue
            for _ in range(length):
                out.append(out[start])
                start += 1
    return bytes(out)


def compress(data: bytes) -> bytes:
    from ebook_convert.ebooks.compression.palmdoc import py_compress_doc

    return py_compress_doc(data) if data else b''
