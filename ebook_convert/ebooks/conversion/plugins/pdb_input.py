# License: GPLv3 Copyright: 2009, John Schember <john@nachtimwald.com>

from __future__ import annotations
import os
from typing import IO, TYPE_CHECKING

from ebook_convert.customize.conversion import InputFormatPlugin
from ebook_convert.utils.localization import _

if TYPE_CHECKING:
    from optparse import Values

    from ebook_convert.ebooks.oeb.base import OEBBook
    from ebook_convert.utils.logging import Log


class PDBInput(InputFormatPlugin):
    name = 'PDB Input'
    author = 'John Schember'
    description = _('Convert PDB to HTML')
    file_types = {'pdb', 'updb'}
    commit_name = 'pdb_input'

    def convert(self, stream: IO[bytes], options: Values, file_ext: str, log: Log, accelerators: dict[str, str]) -> str | OEBBook | None:
        from ebook_convert.ebooks.pdb import IDENTITY_TO_NAME, PDBError, get_reader
        from ebook_convert.ebooks.pdb.header import PdbHeaderReader

        header = PdbHeaderReader(stream)
        Reader = get_reader(header.ident)

        if Reader is None:
            raise PDBError(
                'No reader available for format within container.\n Identity is {}. Book type is {}'.format(
                    header.ident, IDENTITY_TO_NAME.get(header.ident, _('Unknown'))
                )
            )

        log.debug(f'Detected ebook format as: {IDENTITY_TO_NAME[header.ident]} with identity: {header.ident}')

        reader = Reader(header, stream, log, options)
        opf = reader.extract_content(os.getcwd())

        return opf
