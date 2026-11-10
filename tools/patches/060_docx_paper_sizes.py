"""ebooks/docx/writer/container.py imports the paper size table from the PDF
renderer (calibre.ebooks.pdf.render.common), which needs Qt/PoDoFo and is not
vendored.  Inline the table (values copied from that module)."""

TARGET = 'ebooks/docx/writer/container.py'

REPLACEMENTS = [
    (
        'from ebook_convert.ebooks.pdf.render.common import PAPER_SIZES\n',
        '''
# ebook-convert: paper sizes in points, from calibre.ebooks.pdf.render.common
_inch = 72.0
_cm = _inch / 2.54
_W, _H = (21 * _cm, 29.7 * _cm)
_BW, _BH = (25 * _cm, 35.3 * _cm)
PAPER_SIZES = {
    'a6': (_W * 0.5, _H * 0.5), 'a5': (_H * 0.5, _W), 'a4': (_W, _H), 'a3': (_H, _W * 2),
    'a2': (_W * 2, _H * 2), 'a1': (_H * 2, _W * 4), 'a0': (_W * 4, _H * 4),
    'b6': (_BW * 0.5, _BH * 0.5), 'b5': (_BH * 0.5, _BW), 'b4': (_BW, _BH), 'b3': (_BH * 2, _BW),
    'b2': (_BW * 2, _BH * 2), 'b1': (_BH * 4, _BW * 2), 'b0': (_BW * 4, _BH * 4),
    'letter': (8.5 * _inch, 11 * _inch), 'legal': (8.5 * _inch, 14 * _inch),
}
''',
    ),
]
