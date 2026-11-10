import os

from ebook_convert.customize.conversion import InputFormatPlugin
from ebook_convert.ebooks.pdb.header import PdbHeaderReader
from ebook_convert.ebooks.pdb import PDBError, IDENTITY_TO_NAME, get_reader


class PDBInput(InputFormatPlugin):

    name = 'PDB Input'
    author = 'John Schember'
    description = 'Convert PDB to HTML'
    file_types = {'pdb', 'updb'}
    commit_name = 'pdb_input'

    def convert(self, stream, options, file_ext, log,
                accelerators):

        header = PdbHeaderReader(stream)
        Reader = get_reader(header.ident)

        if Reader is None:
            raise PDBError('No reader available for format within container.'
                           '\n Identity is %s. Book type is %s' %
                           (header.ident,
                            IDENTITY_TO_NAME.get(header.ident, 'Unknown')))

        log.debug('Detected ebook format as: %s with identity: %s',
                  IDENTITY_TO_NAME[header.ident], header.ident)

        reader = Reader(header, stream, log, options)
        opf = reader.extract_content(os.getcwd())

        return opf
