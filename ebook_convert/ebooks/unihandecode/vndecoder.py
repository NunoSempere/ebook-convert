# License: GPLv3 Copyright: 2010, Hiroshi Miura <miurahr@linux.com>

"""
Decode unicode text to an ASCII representation of the text in Vietnamese.

"""

from __future__ import annotations
from ebook_convert.ebooks.unihandecode.unicodepoints import CODEPOINTS
from ebook_convert.ebooks.unihandecode.unidecoder import Unidecoder
from ebook_convert.ebooks.unihandecode.vncodepoints import CODEPOINTS as HANCODES


class Vndecoder(Unidecoder):
    codepoints = {}

    def __init__(self) -> None:
        self.codepoints = CODEPOINTS
        self.codepoints.update(HANCODES)
