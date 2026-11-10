# License: GPLv3 Copyright: 2009, John Schember <john@nachtimwald.com>

import os

from ebook_convert.customize.conversion import InputFormatPlugin, OptionRecommendation
from ebook_convert import polyglot

ENGINES = 'calibre', 'pdftohtml'

# Files pdftohtml and the reflow engine leave in the working directory that
# are not part of the book and must not end up in the OPF manifest
NOT_BOOK_FILES = frozenset({'index.xml', 'metadata.opf', 'src.pdf'})


class PDFInput(InputFormatPlugin):

    name        = 'PDF Input'
    author      = 'Kovid Goyal and John Schember and Alan Pettigrew'
    description = 'Convert PDF files to HTML'
    file_types  = {'pdf'}
    commit_name = 'pdf_input'

    options = {
        OptionRecommendation(name='no_images', recommended_value=False,
            help='Do not extract images from the document'),
        OptionRecommendation(name='unwrap_factor', recommended_value=0.45,
            help='Scale used to determine the length at which a line should '
            'be unwrapped. Valid values are a decimal between 0 and 1. The '
            'default is 0.45, just below the median line length.'),
        OptionRecommendation(name='pdf_engine', recommended_value='calibre',
            choices=ENGINES,
            help='The PDF engine to use, the "calibre" engine is recommended '
            'as it has automatic header and footer removal. Choices: '
            + ', '.join(ENGINES)),
        OptionRecommendation(name='pdf_header_skip', recommended_value=-1,
            help='Skip everything to the specified number of pixels at the '
            'top of a page. Negative numbers mean auto-detect and remove '
            'headers, zero means do not remove headers and positive numbers '
            'mean remove headers that appear above that many pixels from the '
            'top of the page. Works only with the calibre PDF engine.'),
        OptionRecommendation(name='pdf_footer_skip', recommended_value=-1,
            help='Skip everything to the specified number of pixels at the '
            'bottom of a page. Negative numbers mean auto-detect and remove '
            'footers, zero means do not remove footers and positive numbers '
            'mean remove footers that appear below that many pixels from the '
            'bottom of the page. Works only with the calibre PDF engine.'),
        OptionRecommendation(name='pdf_header_regex', recommended_value='',
            help='Regular expression to remove lines at the top of a page. '
            'This only looks at the first line of a page and works only with '
            'the calibre PDF engine.'),
        OptionRecommendation(name='pdf_footer_regex', recommended_value='',
            help='Regular expression to remove lines at the bottom of a page. '
            'This only looks at the last line of a page and works only with '
            'the calibre PDF engine.'),
    }

    def convert(self, stream, options, file_ext, log, accelerators):
        from ebook_convert.ebooks.metadata.opf2 import OPFCreator
        from ebook_convert.ebooks.pdf.pdftohtml import pdftohtml

        log.debug('Converting file to html...')
        # The main html file will be named index.html
        self.opts, self.log = options, log
        engine = getattr(options, 'pdf_engine', 'calibre')
        if engine == 'calibre':
            from ebook_convert.ebooks.pdf.reflow import PDFDocument
            from ebook_convert.utils.cleantext import clean_ascii_chars

            pdftohtml(os.getcwd(), stream.name, options.no_images, as_xml=True)
            with open('index.xml', 'rb') as f:
                xml = clean_ascii_chars(f.read())
            PDFDocument(xml, options, log)
        else:
            pdftohtml(os.getcwd(), stream.name, options.no_images)

        from ebook_convert.ebooks.metadata.meta import get_metadata
        log.debug('Retrieving document metadata...')
        mi = get_metadata(stream, 'pdf')
        opf = OPFCreator(os.getcwd(), mi)

        manifest = [('index.html', None)]

        for name in sorted(os.listdir(os.getcwd())):
            if name == 'index.html' or name in NOT_BOOK_FILES:
                continue
            manifest.append((name, None))
        log.debug('Generating manifest...')
        opf.create_manifest(manifest)

        opf.create_spine(['index.html'])
        log.debug('Rendering manifest...')
        with open('metadata.opf', 'wb') as opffile:
            opf.render(opffile)
        if os.path.exists('toc.ncx'):
            ncxid = opf.manifest.id_for_path('toc.ncx')
            if ncxid:
                with open('metadata.opf', 'r+b') as f:
                    raw = f.read().replace(b'<spine', b'<spine toc="%s"' %
                                           polyglot.as_bytes(ncxid))
                    f.seek(0)
                    f.write(raw)

        return os.path.join(os.getcwd(), 'metadata.opf')
