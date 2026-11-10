"""Tests for the Calibre fixes back-ported into the EPUB/OEB pipeline.

The CLI only exposes the input and output file, so conversions that need a
non-default option (EPUB 3 output) run the Plumber in-process and set the
option through the UI recommendations, the way the Calibre GUI does.
"""
import zipfile

import pytest

from ebook_convert import logging
from ebook_convert.customize.conversion import OptionRecommendation
from ebook_convert.ebooks.conversion.plumber import Plumber

from tests.test_convert import convert


CONTAINER_XML = (
    '<?xml version="1.0"?><container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
    '<rootfile full-path="OEBPS/content.opf" '
    'media-type="application/oebps-package+xml"/></rootfiles></container>')

XHTML_HEAD = ('<?xml version="1.0" encoding="UTF-8"?>'
              '<html xmlns="http://www.w3.org/1999/xhtml" '
              'xmlns:epub="http://www.idpf.org/2007/ops">')


def opf3(manifest, spine, language='en', extra_meta=''):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="uid">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<dc:identifier id="uid">urn:uuid:12345678-1234-1234-1234-123456789abc'
        '</dc:identifier><dc:title>Test Book</dc:title>'
        '<dc:language>%s</dc:language><dc:creator>Someone</dc:creator>%s'
        '<meta property="dcterms:modified">2024-01-01T00:00:00Z</meta>'
        '</metadata><manifest>%s</manifest><spine>%s</spine></package>'
        % (language, extra_meta, manifest, spine))


def chapter(title, body):
    return ('%s<head><title>%s</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/></head>'
            '<body>%s</body></html>' % (XHTML_HEAD, title, body))


def write_epub(path, files):
    """Write the EPUB ``path`` from ``files`` (archive name -> str/bytes)."""
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('mimetype', 'application/epub+zip',
                    compress_type=zipfile.ZIP_STORED)
        zf.writestr('META-INF/container.xml', CONTAINER_XML)
        for name, data in files.items():
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    return path


def convert_inprocess(src, dst, **options):
    """Convert ``src`` to ``dst`` with the given conversion options."""
    plumber = Plumber(str(src), str(dst), logging.default_log, lambda *a: None)
    plumber.merge_ui_recommendations(
        [(name, value, OptionRecommendation.HIGH)
         for name, value in options.items()])
    plumber.run()
    assert dst.exists() and dst.stat().st_size > 0
    return dst


def read_epub(path):
    with zipfile.ZipFile(path) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def opf_of(files):
    name = next(n for n in files if n.endswith('.opf'))
    return files[name].decode('utf-8')


def nav_of(files):
    names = [n for n in files if n.endswith('.xhtml') and b'epub:type="toc"'
             in files[n]]
    assert len(names) == 1, names
    return names[0], files[names[0]].decode('utf-8')


def test_epub_to_epub3(epub3_path, tmp_path):
    """Item A: EPUB 3 output has a nav, no NCX and a version 3.0 package."""
    out = convert_inprocess(epub3_path, tmp_path / 'out.epub', epub_version='3')
    files = read_epub(out)
    assert not any(n.endswith('.ncx') for n in files)
    opf = opf_of(files)
    assert 'version="3.0"' in opf
    assert 'properties="nav"' in opf
    assert '<guide' not in opf
    name, nav = nav_of(files)
    assert name.endswith('nav.xhtml')
    assert 'Chapter One' in nav and 'Chapter Two' in nav
    assert 'role="doc-toc"' in nav
    assert 'xml:lang="en"' in opf  # package language from set_package_language


@pytest.fixture
def paged_epub(tmp_path):
    """An EPUB 3 whose nav is in the spine, has a page-list and whose
    chapter contains CSS page breaks, so that splitting happens."""
    nav = (
        '%s<head><title>Contents</title></head><body>'
        '<nav epub:type="toc"><h1>Contents</h1><ol>'
        '<li><a href="ch1.xhtml">Chapter One</a></li>'
        '<li><a href="ch1.xhtml#part2">Part Two</a></li></ol></nav>'
        '<nav epub:type="page-list" hidden=""><ol>'
        '<li><a href="ch1.xhtml">1</a></li>'
        '<li><a href="ch1.xhtml#part2">2</a></li></ol></nav>'
        '<nav epub:type="landmarks" hidden=""><ol>'
        '<li><a epub:type="toc" href="nav.xhtml">Contents</a></li>'
        '<li><a epub:type="bodymatter" href="ch1.xhtml">Start</a></li>'
        '</ol></nav></body></html>' % XHTML_HEAD)
    ch1 = chapter('Chapter One',
                  '<h1>Chapter One</h1><p>%s</p>'
                  '<h1 id="part2" class="pb">Part Two</h1><p>%s</p>'
                  % ('one ' * 200, 'two ' * 200))
    files = {
        'OEBPS/content.opf': opf3(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
            ' properties="nav"/>'
            '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="css" href="style.css" media-type="text/css"/>',
            '<itemref idref="nav"/><itemref idref="c1"/>'),
        'OEBPS/nav.xhtml': nav,
        'OEBPS/ch1.xhtml': ch1,
        'OEBPS/style.css': '.pb { page-break-before: always }',
    }
    return write_epub(tmp_path / 'paged.epub', files)


def test_nav_not_split_and_page_list_preserved(paged_epub, tmp_path):
    """Items B and C: the chapter is split at the page break, the nav is
    not, and the page-list and landmarks survive with their links
    rewritten to the split files."""
    out = convert_inprocess(paged_epub, tmp_path / 'out.epub', epub_version='3')
    files = read_epub(out)
    assert any('ch1_split' in n for n in files), sorted(files)
    assert not any('nav_split' in n for n in files), sorted(files)
    name, nav = nav_of(files)
    assert 'role="doc-toc"' in nav
    assert 'Contents</h1>' in nav
    # The page-list of the input nav is kept, with its links pointing at
    # the split files
    assert 'epub:type="page-list"' in nav
    assert 'ch1_split_001.xhtml#part2' in nav
    assert nav.count('ch1.xhtml') == 0
    assert 'epub:type="landmarks"' in nav
    assert 'epub:type="bodymatter"' in nav


def test_landmarks_become_guide_entries(paged_epub, tmp_path):
    """Item D: EPUB 3 landmarks are carried through the pipeline as OPF
    guide references (so the rest of the pipeline sees them)."""
    out = tmp_path / 'out.epub'
    convert(paged_epub, out)
    opf = opf_of(read_epub(out))
    assert '<guide' in opf
    assert 'type="text"' in opf  # bodymatter -> text
    assert 'type="toc"' in opf


def test_cover_landmark_is_detected(tmp_path):
    """Item D: an EPUB 3 cover identified only through the manifest
    cover-image property and a cover landmark is found and kept."""
    from PIL import Image
    cover = tmp_path / 'cover.jpg'
    Image.new('RGB', (600, 800), (20, 120, 30)).save(cover, 'JPEG')
    nav = (
        '%s<head><title>nav</title></head><body>'
        '<nav epub:type="toc"><ol><li><a href="ch1.xhtml">One</a></li></ol>'
        '</nav><nav epub:type="landmarks" hidden=""><ol>'
        '<li><a epub:type="cover" href="titlepage.xhtml">Cover</a></li>'
        '<li><a epub:type="bodymatter" href="ch1.xhtml">Start</a></li>'
        '</ol></nav></body></html>' % XHTML_HEAD)
    files = {
        'OEBPS/content.opf': opf3(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
            ' properties="nav"/>'
            '<item id="cover" href="cover.jpg" media-type="image/jpeg"'
            ' properties="cover-image"/>'
            '<item id="tp" href="titlepage.xhtml"'
            ' media-type="application/xhtml+xml"/>'
            '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="css" href="style.css" media-type="text/css"/>',
            '<itemref idref="tp"/><itemref idref="c1"/>'),
        'OEBPS/nav.xhtml': nav,
        'OEBPS/titlepage.xhtml': chapter('Cover', '<img src="cover.jpg"/>'),
        'OEBPS/ch1.xhtml': chapter('One', '<h1>One</h1><p>text</p>'),
        'OEBPS/style.css': 'p { margin: 0 }',
        'OEBPS/cover.jpg': cover.read_bytes(),
    }
    src = write_epub(tmp_path / 'cover.epub', files)
    out = tmp_path / 'out.epub'
    proc = convert(src, out)
    assert 'Bad image' not in proc.stderr
    rfiles = read_epub(out)
    opf = opf_of(rfiles)
    assert 'type="cover"' in opf
    assert any(n.lower().endswith('.jpg') for n in rfiles)
    # EPUB 3 output marks the cover image and the title page by property
    out3 = convert_inprocess(src, tmp_path / 'out3.epub', epub_version='3')
    opf = opf_of(read_epub(out3))
    assert 'cover-image' in opf
    assert 'calibre:title-page' in opf


def test_important_wins_when_flattening_css(tmp_path):
    """Item E: an !important declaration in a stylesheet beats a later
    inline style when the CSS is flattened into classes."""
    files = {
        'OEBPS/content.opf': opf3(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
            ' properties="nav"/>'
            '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="css" href="style.css" media-type="text/css"/>',
            '<itemref idref="c1"/>'),
        'OEBPS/nav.xhtml': (
            '%s<head><title>nav</title></head><body><nav epub:type="toc">'
            '<ol><li><a href="ch1.xhtml">One</a></li></ol></nav></body></html>'
            % XHTML_HEAD),
        'OEBPS/ch1.xhtml': chapter(
            'One', '<h1>One</h1><p class="imp" style="color: blue">'
            'important text</p><p class="plain" style="color: blue">'
            'plain text</p>'),
        'OEBPS/style.css': ('.imp { color: red !important }\n'
                            '.plain { color: red }'),
    }
    src = write_epub(tmp_path / 'imp.epub', files)
    out = tmp_path / 'out.epub'
    convert(src, out)
    rfiles = read_epub(out)
    css = b'\n'.join(v for n, v in rfiles.items() if n.endswith('.css'))
    css = css.decode('utf-8')
    assert 'color: red' in css
    assert 'color: blue' in css  # the plain paragraph keeps its inline colour
    html = rfiles[next(n for n in rfiles if n.endswith('ch1.xhtml'))]
    html = html.decode('utf-8')
    assert 'color: blue' not in html  # styles were flattened into classes


def test_duplicate_font_face_rules_are_merged(tmp_path):
    """Item E: identical @font-face rules from several stylesheets are
    written only once into the global stylesheet."""
    font = b'\0' * 64
    face = ('@font-face { font-family: "Dup"; font-weight: normal; '
            'font-style: normal; src: url(fonts/dup.ttf) }')
    files = {
        'OEBPS/content.opf': opf3(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
            ' properties="nav"/>'
            '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="css" href="style.css" media-type="text/css"/>'
            '<item id="css2" href="style2.css" media-type="text/css"/>'
            '<item id="f" href="fonts/dup.ttf" media-type="font/ttf"/>',
            '<itemref idref="c1"/>'),
        'OEBPS/nav.xhtml': (
            '%s<head><title>nav</title></head><body><nav epub:type="toc">'
            '<ol><li><a href="ch1.xhtml">One</a></li></ol></nav></body></html>'
            % XHTML_HEAD),
        'OEBPS/ch1.xhtml': (
            '%s<head><title>One</title>'
            '<link rel="stylesheet" type="text/css" href="style.css"/>'
            '<link rel="stylesheet" type="text/css" href="style2.css"/>'
            '</head><body><h1>One</h1><p class="d">text</p></body></html>'
            % XHTML_HEAD),
        'OEBPS/style.css': face + '\n.d { font-family: "Dup" }',
        'OEBPS/style2.css': face,
        'OEBPS/fonts/dup.ttf': font,
    }
    src = write_epub(tmp_path / 'fonts.epub', files)
    out = tmp_path / 'out.epub'
    convert(src, out)
    rfiles = read_epub(out)
    css = b'\n'.join(v for n, v in rfiles.items() if n.endswith('.css'))
    assert css.count(b'@font-face') == 1, css.decode('utf-8')
    opf = opf_of(rfiles)
    # EPUB 2 output uses the font MIME type epubcheck expects
    assert 'application/x-font-truetype' in opf


def test_rtl_language_sets_page_progression_direction(tmp_path):
    """Item D: a right-to-left book gets page-progression-direction="rtl"
    in EPUB 3 output."""
    files = {
        'OEBPS/content.opf': opf3(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
            ' properties="nav"/>'
            '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item id="css" href="style.css" media-type="text/css"/>',
            '<itemref idref="c1"/>', language='he'),
        'OEBPS/nav.xhtml': (
            '%s<head><title>nav</title></head><body><nav epub:type="toc">'
            '<ol><li><a href="ch1.xhtml">One</a></li></ol></nav></body></html>'
            % XHTML_HEAD),
        'OEBPS/ch1.xhtml': chapter('One', '<h1>One</h1><p>text</p>'),
        'OEBPS/style.css': 'p { margin: 0 }',
    }
    src = write_epub(tmp_path / 'rtl.epub', files)
    out = convert_inprocess(src, tmp_path / 'out.epub', epub_version='3')
    opf = opf_of(read_epub(out))
    assert 'page-progression-direction="rtl"' in opf
    assert 'xml:lang="he"' in opf


def test_dir_container_refuses_paths_outside_root(tmp_path):
    """Item F: DirContainer does not read or write outside its root."""
    from ebook_convert.ebooks.oeb.base import DirContainer
    root = tmp_path / 'book'
    root.mkdir()
    (root / 'a.opf').write_bytes(b'<package/>')
    secret = tmp_path / 'secret.txt'
    secret.write_bytes(b'secret')
    container = DirContainer(str(root), logging.default_log)
    assert container.read('a.opf') == b'<package/>'
    assert container.exists('a.opf')
    assert not container.exists('../secret.txt')
    assert not container.exists('..%2Fsecret.txt')
    with pytest.raises(ValueError):
        container.read('../secret.txt')
    with pytest.raises(ValueError):
        container.write('../evil.txt', b'x')
    assert not (tmp_path / 'evil.txt').exists()


def test_manifest_item_without_id_does_not_crash(tmp_path):
    """Item F: a manifest <item> without an id gets one generated."""
    files = {
        'OEBPS/content.opf': opf3(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
            ' properties="nav"/>'
            '<item id="c1" href="ch1.xhtml" media-type="application/xhtml+xml"/>'
            '<item href="style.css" media-type="text/css"/>'
            '<item href="ch2.xhtml" media-type="application/xhtml+xml"/>',
            '<itemref idref="c1"/>'),
        'OEBPS/nav.xhtml': (
            '%s<head><title>nav</title></head><body><nav epub:type="toc">'
            '<ol><li><a href="ch1.xhtml">One</a></li>'
            '<li><a href="ch2.xhtml">Two</a></li></ol></nav></body></html>'
            % XHTML_HEAD),
        'OEBPS/ch1.xhtml': chapter('One', '<h1>One</h1><p>'
                                   '<a href="ch2.xhtml">next</a></p>'),
        'OEBPS/ch2.xhtml': chapter('Two', '<h1>Two</h1><p>text</p>'),
        'OEBPS/style.css': 'p { margin: 0 }',
    }
    src = write_epub(tmp_path / 'noid.epub', files)
    out = tmp_path / 'out.epub'
    convert(src, out)
    rfiles = read_epub(out)
    assert any(n.endswith('ch2.xhtml') for n in rfiles)
    assert any(n.endswith('.css') for n in rfiles)
