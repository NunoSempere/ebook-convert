# License: GPLv3 Copyright: 2011, John Schember <john@nachtimwald.com>

from __future__ import annotations
import os
from typing import IO, TYPE_CHECKING

from ebook_convert.customize.conversion import InputFormatPlugin
from ebook_convert.utils.localization import _

if TYPE_CHECKING:
    from optparse import Values

    from ebook_convert.ebooks.oeb.base import OEBBook
    from ebook_convert.utils.logging import Log


class AZW4Input(InputFormatPlugin):
    name = 'AZW4 Input'
    author = 'John Schember'
    description = _('Convert AZW4 to HTML')
    file_types = {'azw4'}
    commit_name = 'azw4_input'

    def convert(self, stream: IO[bytes], options: Values, file_ext: str, log: Log, accelerators: dict[str, str]) -> str | OEBBook | None:
        from ebook_convert.ebooks.azw4.reader import Reader
        from ebook_convert.ebooks.pdb.header import PdbHeaderReader

        header = PdbHeaderReader(stream)
        reader = Reader(header, stream, log, options)
        opf = reader.extract_content(os.getcwd())

        return opf
