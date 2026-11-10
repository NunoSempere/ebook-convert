"""Regression tests for the DOCX input/output fixes back-ported from Calibre.

DOCX and EPUB fixtures are built programmatically so that each test shows
exactly the markup it exercises.
"""
import io
import logging
import re
import types
import zipfile

from lxml import etree
from lxml import html as lhtml
from PIL import Image
import pytest

from ebook_convert.ebooks.docx.names import DOCXNamespace
from tests.test_convert import convert


W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'

DOC_NSDECL = (
    'xmlns:w="%s" xmlns:r="%s" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
    'mc:Ignorable="wps"' % (W_NS, R_NS))

STYLES_XML = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="%s">
  <w:docDefaults><w:rPrDefault><w:rPr><w:sz w:val="24"/></w:rPr></w:rPrDefault></w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
</w:styles>''' % W_NS


def png_bytes(size=(40, 30), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


def make_docx(path, body, numbering=None, images=None):
    """Write a minimal DOCX whose <w:body> contains ``body``.

    ``numbering`` is the content of <w:numbering>, ``images`` maps
    relationship ids to PNG bytes stored as word/media/<rid>.png.
    """
    images = images or {}
    overrides = [
        ('/word/document.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'),
        ('/word/styles.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'),
    ]
    rels = [('rId100', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles', 'styles.xml')]
    if numbering is not None:
        overrides.append(('/word/numbering.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml'))
        rels.append(('rId101', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering', 'numbering.xml'))
    for rid in images:
        rels.append((rid, 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image', 'media/%s.png' % rid))
    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                     '<Types xmlns="%s">' % CT_NS,
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
                     '<Default Extension="xml" ContentType="application/xml"/>',
                     '<Default Extension="png" ContentType="image/png"/>']
    content_types += ['<Override PartName="%s" ContentType="%s"/>' % o for o in overrides]
    content_types.append('</Types>')
    doc_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>', '<Relationships xmlns="%s">' % REL_NS]
    doc_rels += ['<Relationship Id="%s" Type="%s" Target="%s"/>' % r for r in rels]
    doc_rels.append('</Relationships>')
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:document %s><w:body>%s<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
                '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
                '</w:body></w:document>' % (DOC_NSDECL, body))
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', '\n'.join(content_types))
        zf.writestr('_rels/.rels', (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="%s"><Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>' % REL_NS))
        zf.writestr('word/document.xml', document)
        zf.writestr('word/styles.xml', STYLES_XML)
        zf.writestr('word/_rels/document.xml.rels', '\n'.join(doc_rels))
        if numbering is not None:
            zf.writestr('word/numbering.xml', (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<w:numbering xmlns:w="%s">%s</w:numbering>' % (W_NS, numbering)))
        for rid, data in images.items():
            zf.writestr('word/media/%s.png' % rid, data)
    return path


def make_epub(path, body, images=None):
    """Write a minimal EPUB 2 with a single XHTML file containing ``body``."""
    images = images or {}
    manifest = ''.join(
        '<item id="img%d" href="%s" media-type="image/png"/>' % (i, name)
        for i, name in enumerate(images))
    opf = ('<?xml version="1.0" encoding="utf-8"?>'
           '<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">'
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
           '<dc:title>Backport Fixtures</dc:title><dc:language>en</dc:language>'
           '<dc:identifier id="uid">urn:uuid:backports</dc:identifier></metadata>'
           '<manifest><item id="t" href="index.xhtml" media-type="application/xhtml+xml"/>%s</manifest>'
           '<spine><itemref idref="t"/></spine></package>' % manifest)
    xhtml = ('<?xml version="1.0" encoding="utf-8"?>'
             '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Fixtures</title></head>'
             '<body>%s</body></html>' % body)
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        zf.writestr('META-INF/container.xml', (
            '<?xml version="1.0"?><container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
            '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
            '</rootfiles></container>'))
        zf.writestr('OEBPS/content.opf', opf)
        zf.writestr('OEBPS/index.xhtml', xhtml)
        for name, data in images.items():
            zf.writestr('OEBPS/' + name, data)
    return path


def epub_html_and_css(path):
    """Return (parsed <html> root, concatenated CSS, archive names)."""
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        html = [zf.read(n) for n in names if n.endswith(('.html', '.xhtml'))]
        css = '\n'.join(zf.read(n).decode('utf-8') for n in names if n.endswith('.css'))
    assert len(html) == 1, names
    return lhtml.fromstring(html[0]), css, names


def docx_document(path):
    with zipfile.ZipFile(path) as zf:
        return etree.fromstring(zf.read('word/document.xml'))


def run(text, preserve=False):
    space = ' xml:space="preserve"' if preserve else ''
    return '<w:r><w:t%s>%s</w:t></w:r>' % (space, text)


# ---------------------------------------------------------------------------
# DOCX input, end to end
# ---------------------------------------------------------------------------

def test_lone_space_between_runs_survives(tmp_path):
    body = '<w:p>%s%s%s</w:p>' % (run('Hello'), run(' '), run('world'))
    out = tmp_path / 'out.epub'
    convert(make_docx(tmp_path / 'in.docx', body), out)
    html, css, names = epub_html_and_css(out)
    text = ''.join(html.xpath('//p//text()'))
    assert 'Hello world' in text


def test_restarted_numbered_list_via_lvl_override(tmp_path):
    numbering = (
        '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/>'
        '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '<w:num w:numId="2"><w:abstractNumId w:val="0"/>'
        '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="5"/></w:lvlOverride></w:num>')

    def item(num_id, text):
        return ('<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="%s"/></w:numPr></w:pPr>%s</w:p>'
                % (num_id, run(text)))

    body = item(1, 'one') + item(1, 'two') + '<w:p>%s</w:p>' % run('break') + item(2, 'five') + item(2, 'six')
    out = tmp_path / 'out.epub'
    convert(make_docx(tmp_path / 'in.docx', body, numbering=numbering), out)
    html, css, names = epub_html_and_css(out)
    lists = html.xpath('//ol')
    assert len(lists) == 2
    assert [li.text_content().strip() for li in lists[1]] == ['five', 'six']
    # The override restarts the second list at 5, before the fix every
    # overridden level got the last start value read, or none at all
    assert lists[1][0].get('value') == '5'
    assert lists[0][0].get('value') in (None, '1')


def test_alternate_content_fallback_picture_is_kept(tmp_path):
    drawing = (
        '<w:drawing><wp:inline><wp:extent cx="508000" cy="381000"/>'
        '<wp:docPr id="1" name="Picture 1"/><a:graphic><a:graphicData '
        'uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
        '<pic:nvPicPr><pic:cNvPr id="0" name="fallback.png"/><pic:cNvPicPr/></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="rId5"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        '<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="508000" cy="381000"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
        '</a:graphicData></a:graphic></wp:inline></w:drawing>')
    body = ('<w:p><w:r><mc:AlternateContent><mc:Choice Requires="wps">'
            '<w:drawing><wp:inline><wp:extent cx="1" cy="1"/><wp:docPr id="2" name="Shape"/>'
            '<a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape">'
            '<wps:wsp/></a:graphicData></a:graphic></wp:inline></w:drawing>'
            '</mc:Choice><mc:Fallback>%s</mc:Fallback></mc:AlternateContent></w:r>%s</w:p>'
            % (drawing, run('caption')))
    out = tmp_path / 'out.epub'
    convert(make_docx(tmp_path / 'in.docx', body, images={'rId5': png_bytes()}), out)
    html, css, names = epub_html_and_css(out)
    assert html.xpath('//img'), 'fallback picture was dropped'
    assert any(n.lower().endswith('.png') for n in names)


def test_libreoffice_zero_chars_indent_is_kept(tmp_path):
    body = ('<w:p><w:pPr><w:ind w:leftChars="0" w:left="720" w:firstLineChars="0" w:firstLine="360"/></w:pPr>%s</w:p>'
            '<w:p>%s</w:p>' % (run('Indented paragraph'), run('Plain paragraph')))
    out = tmp_path / 'out.epub'
    convert(make_docx(tmp_path / 'in.docx', body), out)
    html, css, names = epub_html_and_css(out)
    # the pipeline normalises margins into the shorthand
    assert re.search(r'margin(-left)?: (0 0 0 )?36pt', css), css
    assert 'text-indent: 18pt' in css
    assert '0em' not in css


def test_underline_style_colour_and_current_color(tmp_path):
    body = ('<w:p><w:r><w:rPr><w:u w:val="dash" w:color="FF0000"/></w:rPr><w:t>dashed</w:t></w:r></w:p>'
            '<w:p><w:r><w:rPr><w:color w:val="auto"/></w:rPr><w:t>auto colour</w:t></w:r></w:p>')
    out = tmp_path / 'out.epub'
    convert(make_docx(tmp_path / 'in.docx', body), out)
    html, css, names = epub_html_and_css(out)
    assert re.search(r'text-decoration: underline dashed #(F00|FF0000)', css, re.I), css
    # Undefined text colour is left undefined instead of being forced black
    assert 'color: black' not in css


# ---------------------------------------------------------------------------
# DOCX input, unit level
# ---------------------------------------------------------------------------

def test_read_indent_chars_zero_means_use_twips():
    from ebook_convert.ebooks.docx.block_styles import ParagraphStyle, read_indent
    ns = DOCXNamespace()
    ppr = etree.fromstring('<w:pPr xmlns:w="%s"><w:ind w:left="720" w:leftChars="0" '
                           'w:firstLine="360" w:firstLineChars="0"/></w:pPr>' % W_NS)
    style = ParagraphStyle(ns)
    read_indent(ppr, style, ns.XPath, ns.get)
    assert (style.margin_left, style.text_indent) == ('36pt', '18pt')
    ppr = etree.fromstring('<w:pPr xmlns:w="%s"><w:ind w:left="720" w:leftChars="200"/></w:pPr>' % W_NS)
    style = ParagraphStyle(ns)
    read_indent(ppr, style, ns.XPath, ns.get)
    assert style.margin_left == '2em'
    # w:start/w:end are honoured and swapped for right-to-left paragraphs
    ppr = etree.fromstring('<w:pPr xmlns:w="%s"><w:bidi/><w:ind w:start="720" w:end="360"/></w:pPr>' % W_NS)
    style = ParagraphStyle(ns, ppr)
    assert (style.margin_left, style.margin_right) == ('18pt', '36pt')


def test_numbering_overrides():
    from ebook_convert.ebooks.docx.numbering import Numbering
    ns = DOCXNamespace()
    root = etree.fromstring('''<w:numbering xmlns:w="%s">
    <w:abstractNum w:abstractNumId="0">
    <w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/></w:lvl>
    <w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/></w:lvl>
    </w:abstractNum>
    <w:num w:numId="1"><w:abstractNumId w:val="0"/>
    <w:lvlOverride w:ilvl="0"><w:startOverride w:val="5"/></w:lvlOverride>
    <w:lvlOverride w:ilvl="1"><w:startOverride w:val="7"/></w:lvlOverride>
    <w:lvlOverride><w:lvl w:ilvl="2"><w:start w:val="3"/><w:numFmt w:val="upperRoman"/></w:lvl></w:lvlOverride>
    </w:num></w:numbering>''' % W_NS)
    numbering = Numbering(ns)
    styles = types.SimpleNamespace(numbering_style_links={})
    numbering(root, styles, {})
    assert numbering.starts['1'] == {0: 5, 1: 7, 2: 3}
    assert numbering.instances['1'].levels[2].fmt == 'upper-roman'
    # A level without a character style must not crash (4003282cfb)
    assert numbering.instances['1'].levels[2].char_css() == {}


def test_same_border_compares_border_css():
    from ebook_convert.ebooks.docx.char_styles import RunStyle
    ns = DOCXNamespace()
    a = RunStyle(ns, etree.fromstring('<w:rPr xmlns:w="%s"><w:bdr w:val="single" w:sz="4"/></w:rPr>' % W_NS))
    b = RunStyle(ns, etree.fromstring('<w:rPr xmlns:w="%s"/>' % W_NS))
    assert a.same_border(a)
    assert not a.same_border(b), 'get_border_css() returns None, the dicts must be compared'


def test_polish_index_markup_merges_entries_and_keeps_links():
    from ebook_convert.ebooks.docx.index import polish_index_markup
    entries = ('A:Ab', 'A:Dogs', 'A:Dogs', 'A:Y:Ab')
    body = lhtml.fromstring('<div>' + ''.join('<p><a href="#%d">%s</a></p>' % (i, t) for i, t in enumerate(entries)) + '</div>')
    # Blocks are passed in reverse order
    polish_index_markup(None, list(body)[::-1])
    assert len(body) == 1, 'blocks for the same top level entry not merged'

    def entry_for_link(a):
        span = a.getparent()
        level = float(span.get('style', '').rpartition(' ')[2][:-2])
        ans = [a.text or '']
        for s in span.itersiblings(preceding=True):
            slevel = float(s.get('style', '').rpartition(' ')[2][:-2])
            if slevel < level:
                ans.insert(0, s.text or '')
                level = slevel
        return ':'.join(ans)

    assert {a.get('href'): entry_for_link(a) for a in body.iter('a')} == {'#%d' % i: t for i, t in enumerate(entries)}
    assert [s.text for s in body[0]] == ['A', None, None, 'Y', None]
    # Each entry ends with a line break, references to the same entry share a line
    assert [s[-1].tag for s in body[0]] == ['br'] * 5
    assert len(body[0][2].xpath('descendant::br')) == 1

    def polish(*entries):
        body = lhtml.fromstring('<div>' + ''.join('<p><a href="#%d">%s</a>%s</p>' % (i, t, extra)
                                                   for i, (t, extra) in enumerate(entries)) + '</div>')
        polish_index_markup(None, list(body)[::-1])
        assert {a.get('href') for a in body.iter('a')} == {'#%d' % i for i in range(len(entries))}, 'links lost'
        return body

    body = polish(('B:x', ''), ('B:', ''))
    assert len(body) == 1
    assert [s.text_content() for s in body[0]] == ['B', 'x']
    body = polish(('C', '<span> [See D]</span>'), ('C', '<span> [See E]</span>'), ('D', ''))
    assert len(body) == 2
    assert [s.text_content() for s in body[0]] == ['C [See D], C [See E]']
    body = polish(('A:Dogs', '<span> [See Cats]</span>'), ('A:Dogs:X', ''))
    assert len(body) == 1
    assert [s.text_content() for s in body[0]] == ['A', 'Dogs [See Cats]', 'X']
    body = polish((':', ''), (':', ''), ('Z', ''))
    assert len(body) == 2
    body = lhtml.fromstring('<div><p>X</p><p><a href="#1">X</a></p></div>')
    polish_index_markup(None, list(body)[::-1])
    assert len(body) == 2


def test_image_filename_is_sanitised():
    from ebook_convert.ebooks.docx.images import image_filename
    assert image_filename('My Picture #1 (final).png') == 'My_Picture__1__final_.png'
    assert image_filename('..hidden') == 'hidden'


# ---------------------------------------------------------------------------
# DOCX output, end to end
# ---------------------------------------------------------------------------

def test_nbsp_survives_epub_to_docx(tmp_path):
    body = ('<p>Inline: one&#160;two  three&#160;&#160;four</p>'
            '<p>&#160;Leading: indented</p><p>Trailing: text&#160;</p>')
    out = tmp_path / 'out.docx'
    convert(make_epub(tmp_path / 'in.epub', body), out)
    ns = DOCXNamespace()
    doc = docx_document(out)
    paragraphs = [''.join(ns.XPath('.//w:t/text()')(p)) for p in ns.XPath('//w:p')(doc)]
    assert 'Inline: one\xa0two three\xa0\xa0four' in paragraphs
    assert '\xa0Leading: indented' in paragraphs
    assert 'Trailing: text\xa0' in paragraphs


def test_mixed_format_hyperlink_is_one_w_hyperlink(tmp_path):
    body = ('<p>Styled: <a href="https://example.com" title="Example">a <b>b</b> c</a> outside.</p>'
            '<p>Adjacent: <a href="https://example.com">one</a><a href="https://example.com">two</a></p>'
            '<p>Internal: <a href="#target">go <i>there</i></a></p><p id="target">Destination</p>')
    out = tmp_path / 'out.docx'
    convert(make_epub(tmp_path / 'in.epub', body), out)
    ns = DOCXNamespace()
    doc = docx_document(out)
    paragraphs = {''.join(ns.XPath('.//w:t/text()')(p)).split(':')[0]: p for p in ns.XPath('//w:p')(doc)}
    assert len(ns.XPath('./w:hyperlink')(paragraphs['Styled'])) == 1
    assert ns.XPath('./w:hyperlink/w:r/w:t/text()')(paragraphs['Styled']) == ['a ', 'b', ' c']
    assert len(ns.XPath('./w:hyperlink')(paragraphs['Adjacent'])) == 2
    assert len(ns.XPath('./w:hyperlink')(paragraphs['Internal'])) == 1
    assert ns.XPath('./w:hyperlink/@w:anchor')(paragraphs['Internal'])


def test_missing_and_corrupt_images_do_not_crash(tmp_path):
    body = ('<p>Missing: <img src="missing.png" alt="gone"/> after</p>'
            '<p>Corrupt: <img src="corrupt.png" alt="bad"/> after</p>'
            '<p>Linked: <a href="https://example.com"><img src="ok.png" alt="ok"/></a> after</p>')
    images = {'corrupt.png': b'this is not a PNG', 'ok.png': png_bytes()}
    out = tmp_path / 'out.docx'
    proc = convert(make_epub(tmp_path / 'in.epub', body, images=images), out)
    assert 'Traceback' not in proc.stderr
    ns = DOCXNamespace()
    doc = docx_document(out)
    drawings = ns.XPath('//w:drawing')(doc)
    assert len(drawings) == 2  # corrupt replaced by a blank, missing dropped
    # The image inside a link is clickable
    assert len(ns.XPath('//w:hyperlink/w:r/w:drawing')(doc)) == 1
    with zipfile.ZipFile(out) as zf:
        media = [n for n in zf.namelist() if n.startswith('word/media/')]
        blank = next(n for n in media if 'corrupt' in n)
        assert Image.open(io.BytesIO(zf.read(blank))).size == (1, 1)


def test_underline_style_and_colour_in_output(tmp_path):
    body = '<p>Plain <span style="text-decoration: underline dashed red">dashed</span> end</p>'
    out = tmp_path / 'out.docx'
    convert(make_epub(tmp_path / 'in.epub', body), out)
    with zipfile.ZipFile(out) as zf:
        styles = zf.read('word/styles.xml').decode('utf-8') + zf.read('word/document.xml').decode('utf-8')
    assert 'w:val="dash"' in styles
    assert 'w:color="FF0000"' in styles


def test_comment_after_li_and_whitespace_only_li(tmp_path):
    body = ('<ul><li><!-- a comment --><ul><li>nested</li></ul></li>'
            '<li>\n  <ul><li>deeper</li></ul></li><li>plain</li></ul>')
    out = tmp_path / 'out.docx'
    proc = convert(make_epub(tmp_path / 'in.epub', body), out)
    assert 'Traceback' not in proc.stderr
    ns = DOCXNamespace()
    doc = docx_document(out)
    texts = [''.join(ns.XPath('.//w:t/text()')(p)) for p in ns.XPath('//w:p[w:pPr/w:numPr]')(doc)]
    assert 'nested' in texts and 'deeper' in texts and 'plain' in texts


# ---------------------------------------------------------------------------
# DOCX output, unit level (ported from Calibre's docx/writer/tests.py)
# ---------------------------------------------------------------------------

class WriterHarness:

    def __init__(self):
        from ebook_convert.ebooks.docx.writer.container import DocumentRelationships
        from ebook_convert.ebooks.docx.writer.links import LinksManager
        self.namespace = DOCXNamespace()
        self.relationships = DocumentRelationships(self.namespace)
        self.links = LinksManager(self.namespace, self.relationships, logging.getLogger('test-docx'))
        self.item = types.SimpleNamespace(abshref=lambda href: href or 'test.html')
        self.body = etree.Element(self.namespace.expand('w:body'))

    def link(self, url='https://example.com', tooltip=None):
        return (self.item, url, tooltip)

    def block(self):
        from ebook_convert.ebooks.docx.writer.from_html import Block
        styles = types.SimpleNamespace(create_block_style=lambda *args, **kwargs: types.SimpleNamespace(id=None))
        styles.create_text_style = lambda style, **kwargs: style.get('font-weight', 'normal')
        style = {'page-break-before': 'auto', 'page-break-inside': 'auto'}
        return Block(self.namespace, styles, self.links, etree.Element('p'), style)

    def add_text(self, block, text, link=None, bold=False, lang=None, bookmark=None):
        style = {'white-space': 'normal', 'font-weight': 'bold' if bold else 'normal'}
        block.add_text(text, style, link=link, lang=lang, bookmark=bookmark)
        block.runs[-1].descendant_style = types.SimpleNamespace(id='Bold' if bold else 'Normal')

    def floating_drawing(self):
        mk = self.namespace.makeelement
        ans = mk(self.body, 'w:drawing', append=False)
        anchor = mk(ans, 'wp:anchor')
        mk(anchor, 'wp:docPr')
        graphic_data = mk(mk(anchor, 'a:graphic'), 'a:graphicData')
        mk(mk(mk(graphic_data, 'pic:pic'), 'pic:nvPicPr'), 'pic:cNvPr')
        return ans

    def xpath(self, expression, root=None):
        return self.namespace.XPath(expression)(self.body if root is None else root)


@pytest.fixture
def h():
    return WriterHarness()


def test_styled_hyperlink(h):
    block, link = h.block(), h.link(tooltip='Example')
    h.add_text(block, 'Before ')
    h.add_text(block, 'oddities linktext ', link)
    h.add_text(block, '&', link, bold=True, lang='it')
    h.add_text(block, ' ampersands', link)
    h.add_text(block, ' after')
    block.serialize(h.body)
    hyperlinks = h.xpath('./w:p/w:hyperlink')
    assert len(hyperlinks) == 1
    hyperlink = hyperlinks[0]
    assert h.xpath('./w:r/w:t/text()', hyperlink) == ['oddities linktext ', '&', ' ampersands']
    assert h.xpath('./w:r/w:rPr/w:rStyle/@w:val', hyperlink) == ['Normal', 'Bold', 'Normal']
    assert h.xpath('./w:r/w:rPr/w:lang/@w:val', hyperlink) == ['it']
    assert h.xpath('./w:r/w:t/@xml:space', hyperlink) == ['preserve', 'preserve']
    assert h.xpath('./w:p/w:r/w:t/text()') == ['Before ', ' after']
    assert hyperlink.get(h.namespace.expand('w:tooltip')) == 'Example'
    rid = h.relationships.get_relationship_id('https://example.com', h.namespace.names['LINKS'], 'External')
    assert hyperlink.get(h.namespace.expand('r:id')) == rid


def test_distinct_source_anchors(h):
    for second in (h.link(), h.link(tooltip='Different'), h.link(url='https://example.org')):
        h.body.clear()
        block = h.block()
        h.add_text(block, 'one', h.link())
        h.add_text(block, 'two', second)
        assert len(block.runs) == 2
        block.serialize(h.body)
        assert len(h.xpath('./w:p/w:hyperlink')) == 2


def test_link_interrupted_by_plain_text(h):
    block, link = h.block(), h.link()
    h.add_text(block, 'one', link)
    h.add_text(block, ' between ')
    h.add_text(block, 'two', link)
    block.serialize(h.body)
    assert len(h.xpath('./w:p/w:hyperlink')) == 2
    assert h.xpath('./w:p/w:r/w:t/text()') == [' between ']


def test_separate_blocks(h):
    link = h.link()
    for parent in (h.body, h.namespace.makeelement(h.body, 'w:tc')):
        for text in ('one', 'two'):
            block = h.block()
            h.add_text(block, text, link)
            h.add_text(block, ' bold', link, bold=True)
            block.serialize(parent)
    assert len(h.xpath('.//w:p/w:hyperlink')) == 4
    assert all(len(h.xpath('./w:hyperlink', p)) == 1 for p in h.xpath('.//w:p'))


def test_internal_link_and_fallback(h):
    h.links.document_hrefs.add('test.html')
    h.links.anchor_map[('test.html', 'target')] = 'Target'
    for url, expected in (('#target', 1), ('missing.html#target', 0), ('mailto:test@example.com', 0)):
        h.body.clear()
        block, link = h.block(), h.link(url)
        h.add_text(block, 'one', link)
        h.add_text(block, 'two', link, bold=True)
        block.serialize(h.body)
        assert len(h.xpath('./w:p/w:hyperlink')) == expected, url
        assert h.xpath('.//w:t/text()') == ['one', 'two']
        if expected:
            assert h.xpath('./w:p/w:hyperlink/@w:anchor') == ['Target']


def test_run_contents_and_legacy_serialization(h):
    from ebook_convert.ebooks.docx.writer.from_html import TextRun
    block, link = h.block(), h.link()
    h.add_text(block, 'one', link, bookmark='bookmark')
    block.add_break()
    drawing = etree.Element(h.namespace.expand('w:drawing'))
    block.add_image(drawing, link=link)
    h.add_text(block, 'two', link, bold=True)
    block.serialize(h.body)
    assert len(h.xpath('./w:p/w:hyperlink')) == 1
    assert len(h.xpath('./w:p/w:hyperlink/w:r/w:br')) == 1
    assert h.xpath('./w:p/w:hyperlink/w:r/w:drawing') == [drawing]
    assert h.xpath('.//w:bookmarkStart/@w:name') == ['bookmark']
    assert h.xpath('.//w:bookmarkStart/@w:id') == h.xpath('.//w:bookmarkEnd/@w:id')
    p = h.namespace.makeelement(h.body, 'w:p')
    run = TextRun(h.namespace, None, None)
    run.add_text('legacy', False, link=link)
    run.serialize(p, h.links)
    assert h.xpath('./w:hyperlink/w:r/w:t/text()', p) == ['legacy']


def test_linked_images(h):
    block, link = h.block(), h.link()
    drawings = [etree.Element(h.namespace.expand('w:drawing')) for _ in range(3)]
    h.add_text(block, 'text', link)
    block.add_image(drawings[0])
    block.add_image(drawings[1], link=link)
    block.add_image(drawings[2], link=h.link())
    block.serialize(h.body)
    assert h.xpath('./w:p/w:r/w:drawing') == drawings[:1]
    assert [h.xpath('./w:r/w:drawing', x) for x in h.xpath('./w:p/w:hyperlink')] == [[], drawings[1:2], drawings[2:]]


def test_linked_floating_images(h):
    h.links.document_hrefs.add('test.html')
    h.links.anchor_map[('test.html', 'target')] = 'Target'
    block, link = h.block(), h.link(tooltip='Tip')
    h.add_text(block, 'text', link)
    block.add_image(h.floating_drawing(), link=link, floating=True)
    block.add_image(h.floating_drawing(), link=h.link('#target'), floating=True)
    block.add_image(h.floating_drawing(), floating=True)
    block.serialize(h.body)
    # Word ignores <w:hyperlink> around floating images, the link must be on the image itself
    assert h.xpath('./w:p/w:hyperlink/w:r/w:t/text()') == ['text']
    assert not h.xpath('.//w:hyperlink//w:drawing')
    external = h.relationships.get_relationship_id('https://example.com', h.namespace.names['LINKS'], 'External')
    internal = h.relationships.get_relationship_id('#Target', h.namespace.names['LINKS'])
    for pr in ('wp:docPr', 'pic:cNvPr'):
        hlinks = h.xpath('.//%s/a:hlinkClick' % pr)
        assert [h.namespace.get(x, 'r:id') for x in hlinks] == [external, internal], pr
        assert [x.get('tooltip') for x in hlinks] == ['Tip', None], pr


def test_floating_image_does_not_split_link(h):
    block, link = h.block(), h.link()
    drawings = [h.floating_drawing() for _ in range(2)]
    h.add_text(block, 'before ', link)
    block.add_image(drawings[0], link=link, floating=True)
    h.add_text(block, ' middle ', link)
    block.add_image(drawings[1], link=link, floating=True)
    h.add_text(block, ' after', link)
    block.serialize(h.body)
    hyperlinks = h.xpath('./w:p/w:hyperlink')
    assert len(hyperlinks) == 1
    assert h.xpath('./w:r/w:t/text()', hyperlinks[0]) == ['before ', ' middle ', ' after']
    assert h.xpath('./w:p/w:r/w:drawing') == drawings
    assert len(h.xpath('.//wp:docPr/a:hlinkClick')) == 2


def test_unsupported_scheme_is_logged(h):
    messages = []
    h.links.log = types.SimpleNamespace(warning=lambda msg, *args: messages.append(msg % args))
    block = h.block()
    block.add_image(h.floating_drawing(), link=h.link('mailto:test@example.com'), floating=True)
    block.serialize(h.body)
    assert not h.xpath('.//a:hlinkClick')
    assert len(messages) == 1
    assert 'mailto:test@example.com' in messages[0]


def test_image_runs_do_not_affect_language(h):
    from ebook_convert.ebooks.docx.writer.from_html import Blocks
    block, link = h.block(), h.link()
    for _ in range(2):
        block.add_image(etree.Element(h.namespace.expand('w:drawing')), link=h.link())
    h.add_text(block, 'texte', link, lang='fr')
    blocks = Blocks(h.namespace, types.SimpleNamespace(document_lang='en'), h.links)
    blocks.all_blocks.append(block)
    blocks.resolve_language()
    assert block.block_lang == 'fr'
    assert [r.lang for r in block.runs] == [None, None, None]


def texts(h, text, white_space='normal', ignore_leading_whitespace=False):
    block = h.block()
    block.add_text(text, {'white-space': white_space}, ignore_leading_whitespace=ignore_leading_whitespace)
    block.serialize(h.body)
    return h.xpath('.//w:t/text()')


@pytest.mark.parametrize('ch', ['\xa0', ' ', ' '])
def test_nbsp_is_not_collapsible_whitespace(h, ch):
    assert texts(h, 'one%stwo  three%s%sfour' % (ch, ch, ch)) == ['one%stwo three%s%sfour' % (ch, ch, ch)]


def test_leading_nbsp_is_preserved(h):
    # ignore_leading_whitespace must not eat a leading NBSP
    assert texts(h, ' \t\n\xa0 indented', ignore_leading_whitespace=True) == ['\xa0 indented']


def test_ascii_whitespace_is_still_collapsed(h):
    # In particular the form feed, which lxml refuses to serialize
    assert texts(h, 'one \t\r\n\f\vtwo') == ['one two']


def test_preserved_whitespace_is_untouched(h):
    assert texts(h, '  one\xa0 two  ', white_space='pre') == ['  one\xa0 two  ']
    assert h.xpath('.//w:t/@xml:space') == ['preserve']


def test_soft_hyphens(h):
    block = h.block()
    h.add_text(block, 'hyphen\xadated and spaced \xadout')
    block.serialize(h.body)
    r = h.xpath('./w:p/w:r')[0]
    tags = [etree.QName(c).localname for c in r if not c.tag.endswith('}rPr')]
    assert tags == ['t', 'softHyphen', 't', 't', 'softHyphen', 't']
    assert h.xpath('./w:t/text()', r) == ['hyphen', 'ated and spaced', ' ', 'out']
    # the space before the soft hyphen lives in a preserve-whitespace element
    assert h.xpath('./w:t[@xml:space="preserve"]/text()', r) == [' ']


def test_convert_underline():
    from ebook_convert.ebooks.docx.writer.styles import convert_underline
    assert convert_underline({'underline'}) == 'single auto'
    assert convert_underline({'underline', 'dashed', 'red'}) == 'dash FF0000'
    assert convert_underline({'underline', 'wavy'}) == 'wave auto'
    assert convert_underline({'line-through'}) == ''
    assert convert_underline({'none'}) == ''
