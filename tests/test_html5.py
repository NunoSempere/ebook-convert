from lxml import etree

from ebook_convert.utils import html5


XHTML = 'http://www.w3.org/1999/xhtml'
EPUB = 'http://www.idpf.org/2007/ops'
SVG = 'http://www.w3.org/2000/svg'


def test_plain_html_is_not_namespaced():
    root = html5.parse('<p>one<p>two')
    assert root.tag == 'html'
    assert [p.text for p in root.xpath('//p')] == ['one', 'two']


def test_xhtml_mode_namespaces_elements_without_prefix():
    root = html5.parse('<html><body><p>x</p></body></html>', maybe_xhtml=True)
    assert root.tag == '{%s}html' % XHTML
    assert root.prefix is None
    assert etree.tostring(root).startswith(b'<html xmlns="%s"' % XHTML.encode())


def test_prefixed_attributes_and_elements_are_restored():
    src = ('<html xmlns="%s" xmlns:epub="%s"><body epub:type="bodymatter">'
           '<nav epub:type="toc"/><epub:switch/><p xml:lang="en">x</p>'
           '</body></html>' % (XHTML, EPUB))
    root = html5.parse(src, maybe_xhtml=True)
    body = root.find('{%s}body' % XHTML)
    assert body.get('{%s}type' % EPUB) == 'bodymatter'
    assert root.xpath('//*[@epub:type="toc"]', namespaces={'epub': EPUB})
    assert root.find('.//{%s}switch' % EPUB) is not None
    assert root.find('.//{%s}p' % XHTML).get(
        '{http://www.w3.org/XML/1998/namespace}lang') == 'en'
    # The result must round-trip through a strict XML parser.
    etree.fromstring(etree.tostring(root))


def test_inline_svg_keeps_its_namespace_and_serializes_cleanly():
    src = ('<html><body><svg xmlns="%s" xmlns:xlink="http://www.w3.org/1999/xlink">'
           '<use xlink:href="#a"/></svg></body></html>' % SVG)
    root = html5.parse(src, maybe_xhtml=True)
    svg = root.find('.//{%s}svg' % SVG)
    assert svg is not None
    use = svg[0]
    assert use.get('{http://www.w3.org/1999/xlink}href') == '#a'
    out = etree.tostring(root)
    assert b'2000/xmlns/' not in out
    etree.fromstring(out)


def test_illegal_names_do_not_crash():
    root = html5.parse('<p 1bad="x" foo:bar="y">z</p>')
    assert root.xpath('//p')[0].text == 'z'
    etree.fromstring(etree.tostring(root))


def test_bytes_input():
    root = html5.parse('<p>café</p>'.encode('utf-8'))
    assert root.xpath('//p')[0].text == 'café'


def test_soup():
    soup = html5.parse_soup('<p>a<b>b')
    assert soup.find('b').text == 'b'
