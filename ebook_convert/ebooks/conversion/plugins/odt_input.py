# License: GPLv3 Copyright: 2008, Kovid Goyal kovid@kovidgoyal.net

"""
Convert an ODT file into a Open Ebook
"""

from __future__ import annotations
from typing import IO, TYPE_CHECKING

from ebook_convert.customize.conversion import InputFormatPlugin
from ebook_convert.utils.localization import _

if TYPE_CHECKING:
    from optparse import Values

    from ebook_convert.utils.logging import Log


class ODTInput(InputFormatPlugin):
    name = 'ODT Input'
    author = 'Kovid Goyal'
    description = _('Convert ODT (LibreOffice) files to HTML')
    file_types = {'odt'}
    commit_name = 'odt_input'

    def convert(self, stream: IO[bytes], options: Values, file_ext: str, log: Log, accelerators: dict[str, str]) -> str:
        from ebook_convert.ebooks.odt.input import Extract

        return Extract()(stream, '.', log)
