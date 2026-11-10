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
    '''PalmDOC (LZ77) compression.

    Byte for byte the output of calibre's reference ``py_compress_doc`` (and
    of the C extension), but matches are found through hash chains of 3-byte
    prefixes instead of up to eight ``bytes.rindex`` scans per position,
    which made compression a third of the time of a large MOBI conversion.
    '''
    if not data:
        return b''
    out = bytearray()
    append, extend = out.append, out.extend
    ldata = len(data)
    heads: dict = {}        # 3-byte key -> most recent position
    prev = [-1] * ldata     # previous position with the same key
    indexed = 0             # positions < indexed are in the hash chains
    i = 0
    while i < ldata:
        if i > 10 and (ldata - i) > 10:
            # index every position p <= i - 3 (the match must end at or before i)
            limit = i - 3
            while indexed <= limit:
                key = data[indexed:indexed + 3]
                prev[indexed] = heads.get(key, -1)
                heads[key] = indexed
                indexed += 1
            lo = i - 2047
            if lo < 0:
                lo = 0
            best = 0
            bp = -1
            p = heads.get(data[i:i + 3], -1)
            while p >= lo:
                maxlen = i - p
                if maxlen > 10:
                    maxlen = 10
                if maxlen > best:
                    n = 3
                    while n < maxlen and data[p + n] == data[i + n]:
                        n += 1
                    if n > best:
                        best, bp = n, p
                        if best == 10:
                            break
                p = prev[p]
            if best >= 3:
                m = i - bp
                code = 0x8000 + ((m << 3) & 0x3FF8) + (best - 3)
                append(code >> 8)
                append(code & 0xFF)
                i += best
                continue
        och = data[i]
        i += 1
        if och == 0x20 and i < ldata:
            onch = data[i]
            if 0x40 <= onch < 0x80:
                append(onch ^ 0x80)
                i += 1
                continue
        if och == 0 or 8 < och < 0x80:
            append(och)
        else:
            j = i
            end = i + 7 if i + 7 < ldata else ldata
            while j < end:
                c = data[j]
                if c == 0 or 8 < c < 0x80:
                    break
                j += 1
            n = j - i + 1
            append(n)
            append(och)
            extend(data[i:j])
            i = j
    return bytes(out)
