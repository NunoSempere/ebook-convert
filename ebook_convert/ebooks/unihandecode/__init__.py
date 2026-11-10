# License: GPLv3 Copyright: 2010, Hiroshi Miura <miurahr@linux.com>

from __future__ import annotations
__all__ = ['Unihandecoder']

'''
Decode unicode text to an ASCII representation of the text.
Translate unicode characters to ASCII.

Inspired from John Schember's unidecode library which was created as part
of calibre.

Copyright(c) 2009, John Schember

Tranliterate the string from unicode characters to ASCII in Chinese and others.

'''
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ebook_convert.ebooks.unihandecode.unidecoder import Unidecoder


class Unihandecoder:
    preferred_encoding: str | None = None
    decoder: Unidecoder | None = None

    def __init__(self, lang: str = 'zh', encoding: str = 'utf-8') -> None:
        self.preferred_encoding = encoding
        lang = lang.lower()
        if lang[:2] == 'ja':
            from ebook_convert.ebooks.unihandecode.jadecoder import Jadecoder

            self.decoder = Jadecoder()
        elif lang[:2] == 'kr' or lang == 'korean':
            from ebook_convert.ebooks.unihandecode.krdecoder import Krdecoder

            self.decoder = Krdecoder()
        elif lang[:2] == 'vn' or lang == 'vietnum':
            from ebook_convert.ebooks.unihandecode.vndecoder import Vndecoder

            self.decoder = Vndecoder()
        else:  # zh and others
            from ebook_convert.ebooks.unihandecode.unidecoder import Unidecoder

            self.decoder = Unidecoder()

    def decode(self, text: str | bytes) -> str:
        if isinstance(text, bytes):
            assert self.preferred_encoding is not None  # always set in __init__
            try:
                text = text.decode(self.preferred_encoding)
            except Exception:
                text = text.decode('utf-8', 'replace')
        # at first unicode normalize it. (see Unicode standards)
        ntext = unicodedata.normalize('NFKC', text)
        decoder = self.decoder
        assert decoder is not None
        return decoder.decode(ntext)
