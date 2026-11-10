# License: GPLv3 Copyright: 2011, Kovid Goyal <kovid@kovidgoyal.net>
# Trimmed for ebook-convert: only ``urls_from_identifiers`` from
# calibre/ebooks/metadata/sources/identify.py (used by the book jacket and
# metadata rendering).  The metadata download machinery (plugins, network,
# ``id_link_rules`` preferences) is not included.

from __future__ import annotations

import re
from typing import NamedTuple

from ebook_convert.ebooks.metadata import check_issn
from ebook_convert.polyglot.urllib import urlparse


class IdentifierURL(NamedTuple):
    name: str
    id_type: str
    id_val: str
    url: str


def urls_from_identifiers(identifiers, sort_results: bool = False) -> list[IdentifierURL]:
    identifiers = {k.lower(): v for k, v in identifiers.items()}
    ans: list[IdentifierURL] = []
    keys_left = set(identifiers)

    def add(name: str, k: str, val: str, url: str) -> None:
        ans.append(IdentifierURL(name, k, val, url))
        keys_left.discard(k)

    isbn = identifiers.get('isbn', None)
    if isbn:
        add(isbn, 'isbn', isbn, 'https://www.worldcat.org/isbn/' + isbn)
    doi = identifiers.get('doi', None)
    if doi:
        add('DOI', 'doi', doi, 'https://dx.doi.org/' + doi)
    arxiv = identifiers.get('arxiv', None)
    if arxiv:
        add('arXiv', 'arxiv', arxiv, 'https://arxiv.org/abs/' + arxiv)
    oclc = identifiers.get('oclc', None)
    if oclc:
        add('OCLC', 'oclc', oclc, 'https://www.worldcat.org/oclc/' + oclc)
    issn = check_issn(identifiers.get('issn', None))
    if issn:
        add(issn, 'issn', issn, 'https://www.worldcat.org/issn/' + issn)
    amazon = identifiers.get('amazon', None) or identifiers.get('mobi-asin', None)
    if amazon:
        add('Amazon', 'amazon', amazon, 'https://www.amazon.com/dp/' + amazon)
    google = identifiers.get('google', None)
    if google:
        add('Google Books', 'google', google, 'https://books.google.com/books?id=' + google)
    q = {'http', 'https', 'file'}
    for k, url in identifiers.items():
        if url and re.match(r'ur[il]\d*$', k) is not None:
            url = url[:8].replace('|', ':') + url[8:].replace('|', ',')
            if url.partition(':')[0].lower() in q:
                parts = urlparse(url)
                name = parts.netloc or parts.path
                add(name, k, url, url)
    for k in tuple(keys_left):
        val = identifiers.get(k)
        if val:
            url = val[:8].replace('|', ':') + val[8:].replace('|', ',')
            if url.partition(':')[0].lower() in q:
                parts = urlparse(url)
                name = parts.netloc or parts.path
                add(name, k, url, url)
    if sort_results:
        from ebook_convert.utils.icu import primary_sort_key

        ans = sorted(ans, key=lambda x: primary_sort_key(str(x[0])))
    return ans
