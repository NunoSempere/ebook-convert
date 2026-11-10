# License: GPLv3 Copyright: 2009, John Schember <john@nachtimwald.com>

from __future__ import annotations
import os
from typing import IO, TYPE_CHECKING

from ebook_convert.customize.conversion import InputFormatPlugin
from ebook_convert.utils.localization import _

if TYPE_CHECKING:
    from optparse import Values

    from ebook_convert.utils.logging import Log


class RBInput(InputFormatPlugin):
    name = 'RB Input'
    author = 'John Schember'
    description = _('Convert RB files to HTML')
    file_types = {'rb'}
    commit_name = 'rb_input'

    def convert(self, stream: IO[bytes], options: Values, file_ext: str, log: Log, accelerators: dict[str, str]) -> str:
        from ebook_convert.ebooks.rb.reader import Reader

        reader = Reader(stream, log, options.input_encoding)
        opf = reader.extract_content(os.getcwd())

        return opf
