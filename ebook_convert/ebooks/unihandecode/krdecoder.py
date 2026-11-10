# License: GPLv3 Copyright: 2010, Hiroshi Miura <miurahr@linux.com>

"""
Decode unicode text to an ASCII representation of the text in Korean.
Based on unidecoder.

"""

from __future__ import annotations
from ebook_convert.ebooks.unihandecode.krcodepoints import CODEPOINTS as HANCODES
from ebook_convert.ebooks.unihandecode.unicodepoints import CODEPOINTS
from ebook_convert.ebooks.unihandecode.unidecoder import Unidecoder


class Krdecoder(Unidecoder):
    codepoints = {}

    def __init__(self) -> None:
        self.codepoints = CODEPOINTS
        self.codepoints.update(HANCODES)
