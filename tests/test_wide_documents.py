"""Changes made for documents with very wide trees (a MOBI converted to one
HTML file with 100,000 <p> children of <body>), where libxml2's node-set
sorting and some of Calibre's pruning loops were quadratic."""
import time

from lxml import etree

from ebook_convert.ebooks.oeb.base import XPath, order_document_elements
from ebook_convert.ebooks.oeb.polish.split import do_split
from ebook_convert.utils.logging import default_log as log

DOC = ('<html xmlns="http://www.w3.org/1999/xhtml"><body>t0<div>a<p>b<span>c</span>d<i>e</i>f</p>g'
       '<p>h</p>i</div>j<div><p>k</p>l<p>m<b>n</b>o</p></div>p</body></html>')

# (split point xpath, before, expected first half, expected second half), as
# produced by Calibre's original element-by-element pruning
SPLITS = [
    ('/*/*/*[2]/*[2]', True,
     '<html xmlns="http://www.w3.org/1999/xhtml"><body>t0<div>a<p>b<span>c</span>d<i>e</i>f</p>g<p>h</p>i</div>j<div><p>k</p>l</div>p</body></html>',
     '<html xmlns="http://www.w3.org/1999/xhtml"><body>\n<div>\n<p>m<b>n</b>o</p></div>p</body></html>'),
    ('/*/*/*[2]/*[2]', False,
     '<html xmlns="http://www.w3.org/1999/xhtml"><body>t0<div>a<p>b<span>c</span>d<i>e</i>f</p>g<p>h</p>i</div>j<div><p>k</p>l<p>m<b>n</b>o</p>\n</div>p</body></html>',
     '<html xmlns="http://www.w3.org/1999/xhtml"><body>\n<div>\n</div>p</body></html>'),
    ('/*/*/*[1]/*[1]/*[2]', True,
     '<html xmlns="http://www.w3.org/1999/xhtml"><body>t0<div>a<p>b<span>c</span>d</p>g</div>j</body></html>',
     '<html xmlns="http://www.w3.org/1999/xhtml"><body>\n<div>\n<p>\n<i>e</i>f</p>g<p>h</p>i</div>j<div><p>k</p>l<p>m<b>n</b>o</p></div>p</body></html>'),
]


def test_split_pruning_matches_original_algorithm():
    for path, before, first, second in SPLITS:
        root = etree.fromstring(DOC)
        t1, t2 = do_split(root.xpath(path)[0], log, before)
        assert etree.tostring(t1).decode() == first, (path, before)
        assert etree.tostring(t2).decode() == second, (path, before)


def _wide_doc(n):
    root = etree.Element('{http://www.w3.org/1999/xhtml}html')
    body = etree.SubElement(root, '{http://www.w3.org/1999/xhtml}body')
    for i in range(n):
        p = etree.SubElement(body, '{http://www.w3.org/1999/xhtml}p', attrib={'class': 'c%d' % (i % 7)})
        d = etree.SubElement(p, '{http://www.w3.org/1999/xhtml}div' if i % 3 else '{http://www.w3.org/1999/xhtml}span',
                             attrib={'class': 'inner'})
        d.text = 'x'
    return root, body


def test_page_margin_paragraph_query_is_a_single_step():
    root, body = _wide_doc(300)
    paras = XPath('descendant::*[self::h:p or self::h:div]')(body)
    union = XPath('descendant::h:p|descendant::h:div')(body)
    assert paras == union  # same nodes, same document order


def test_order_document_elements_is_cheap_and_harmless():
    root, body = _wide_doc(20000)
    before = etree.tostring(root)
    t = time.time()
    order_document_elements(root)
    assert time.time() - t < 2
    assert etree.tostring(root) == before
    order_document_elements(None)  # non-elements are ignored
    order_document_elements('text')
    t = time.time()
    assert len(XPath('//*[@class]')(root)) == 40000
    assert time.time() - t < 5
