"""
HTML5 parsing into lxml trees, built on html5lib.

This module is a drop-in stand-in for the small subset of the ``html5-parser``
API that the converter used.  ``html5-parser`` is a C extension that ships no
binary wheels and has to be compiled against the very same ``libxml2`` that
``lxml`` was built with, which made installing the converter with plain
``pip``/``uvx`` unreliable.  ``html5lib`` is pure Python, so the package now
installs anywhere without a compiler.

The differences that matter:

- ``html5lib`` coerces XML-illegal names (``epub:type``, ``xmlns:epub``) into
  ``epubU0003Atype`` style names.  :func:`parse` undoes that and turns known
  prefixes back into proper namespaced attributes/elements.
- Line numbers are not available; ``line_number_attr`` is accepted and
  ignored.
"""
import re
import warnings

import bs4
import html5lib
from html5lib.constants import DataLossWarning
from lxml import etree

XHTML_NS = 'http://www.w3.org/1999/xhtml'
XML_NS = 'http://www.w3.org/XML/1998/namespace'
XMLNS_NS = 'http://www.w3.org/2000/xmlns/'

# Prefixes that commonly show up in (X)HTML found inside ebooks, used when the
# document does not declare them itself.
KNOWN_PREFIXES = {
    'epub': 'http://www.idpf.org/2007/ops',
    'svg': 'http://www.w3.org/2000/svg',
    'math': 'http://www.w3.org/1998/Math/MathML',
    'xlink': 'http://www.w3.org/1999/xlink',
    'xml': XML_NS,
}

_COERCED = re.compile(r'U([0-9A-F]{5})')
_XMLNS_PREFIX = 'xmlnsU0003A'


def _uncoerce(name):
    """Reverse html5lib's ``U0003A`` style escaping of XML-illegal names."""
    return _COERCED.sub(lambda m: chr(int(m.group(1), 16)), name)


def _collect_declarations(root):
    """Pull namespace declarations that html5lib kept as plain attributes."""
    prefixes = dict(KNOWN_PREFIXES)
    for el in root.iter(etree.Element):
        for name in list(el.attrib):
            if name == 'xmlns':
                del el.attrib[name]
            elif name.startswith(_XMLNS_PREFIX):
                prefixes[name[len(_XMLNS_PREFIX):]] = el.attrib.pop(name)
            elif name.startswith('{%s}' % XMLNS_NS):
                # Foreign content (svg, math) keeps its declarations as
                # attributes in the xmlns namespace; the element is already in
                # the right namespace, so only remember prefixed ones.
                prefix = name.split('}', 1)[1]
                value = el.attrib.pop(name)
                if prefix != 'xmlns':
                    prefixes[prefix] = value
    return prefixes


def _restore_names(root, prefixes):
    """Turn ``prefixU0003Alocal`` names back into ``{uri}local`` ones."""
    for el in root.iter(etree.Element):
        for name in list(el.attrib):
            if 'U0003A' not in name or name.startswith('{'):
                continue
            prefix, _, local = _uncoerce(name).partition(':')
            if local and prefix in prefixes:
                el.set('{%s}%s' % (prefixes[prefix], local),
                       el.attrib.pop(name))
        if 'U0003A' in el.tag:
            local = el.tag.rpartition('}')[2]
            prefix, _, local = _uncoerce(local).partition(':')
            if local and prefix in prefixes:
                el.tag = '{%s}%s' % (prefixes[prefix], local)


def _reroot(root, prefixes, namespaced):
    """Rebuild the root so its namespace map is tidy.

    html5lib's lxml tree builder binds XHTML to the ``html`` prefix, which
    makes every element serialize as ``<html:p>``.  Moving the children onto
    a fresh root with the desired declarations makes lxml re-bind them.
    """
    nsmap = {k: v for k, v in prefixes.items() if k != 'xml'}
    if namespaced:
        nsmap[None] = XHTML_NS
    new_root = etree.Element(root.tag, nsmap=nsmap)
    for key, value in root.attrib.items():
        new_root.set(key, value)
    new_root.text = root.text
    new_root.extend(list(root))
    # Drop declarations nothing uses any more (html5lib's ``html`` binding,
    # the xmlns-namespace ones left behind by removed attributes, and any of
    # the well-known prefixes the document did not actually need).
    etree.cleanup_namespaces(new_root)
    return new_root


def parse(data, transport_encoding=None, maybe_xhtml=False,
          namespace_elements=False, keep_doctype=True, sanitize_names=True,
          line_number_attr=None, return_root=True, **kwargs):
    """Parse HTML/XHTML markup with the HTML5 algorithm into an lxml tree.

    :param data: markup, as ``str`` or ``bytes``.  Bytes are decoded using
        ``transport_encoding`` if given, otherwise a BOM or ``<meta>``
        declaration, falling back to UTF-8 (not windows-1252 as a browser
        would; ebook content is overwhelmingly UTF-8).
    :param maybe_xhtml: when true (or ``namespace_elements`` is set) HTML
        elements are placed in the XHTML namespace, as ``html5-parser`` did.
    :param return_root: return the ``<html>`` element (default) or the
        enclosing ``ElementTree``.
    """
    namespaced = bool(maybe_xhtml or namespace_elements)
    encodings = {}
    if isinstance(data, bytes):
        # html5lib refuses encoding hints for str input.
        encodings = dict(transport_encoding=transport_encoding,
                         default_encoding='utf-8')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DataLossWarning)
        tree = html5lib.parse(data, treebuilder='lxml',
                              namespaceHTMLElements=namespaced, **encodings)
    root = tree.getroot()
    prefixes = _collect_declarations(root)
    _restore_names(root, prefixes)
    root = _reroot(root, prefixes, namespaced)
    if return_root:
        return root
    return etree.ElementTree(root)


def parse_soup(markup):
    """Parse markup with the HTML5 algorithm into a BeautifulSoup object."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', DataLossWarning)
        return bs4.BeautifulSoup(markup, 'html5lib')
