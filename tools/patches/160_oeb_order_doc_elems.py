"""oeb/base.py: give every parsed document libxml2's document-order indices.

libxml2 compares two nodes for document order by walking sibling lists
unless the elements carry an order index, which only libxslt assigns.  Any
XPath whose result has to be sorted (unions, ``//x[pred]`` over nodes at
different depths) is then quadratic in the width of the tree; a MOBI whose
text is one HTML file with 100,000 <p> children took hours.  Running an
empty XSLT over the document costs a few milliseconds and assigns the
indices, after which the same queries take well under a second."""

TARGET = 'ebooks/oeb/base.py'

REPLACEMENTS = [
    (
        '''@lru_cache(128)
def XPath(expr: str) -> etree.XPath:
''',
        '''_noop_xslt = None


def order_document_elements(elem: etree._Element | None) -> None:
    """Make libxml2 assign document-order indices to the elements of the
    document containing elem (a side effect of running any XSLT on it), so
    that sorting XPath results is linear instead of quadratic on very wide
    trees. Elements created afterwards lack the index but comparisons that
    involve them stay cheap as long as they are few."""
    global _noop_xslt
    if not isinstance(elem, etree._Element):
        return
    if _noop_xslt is None:
        _noop_xslt = etree.XSLT(etree.XML(
            '<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">'
            '<xsl:template match="/"/></xsl:stylesheet>'))
    try:
        _noop_xslt(elem.getroottree())
    except Exception:
        pass


@lru_cache(128)
def XPath(expr: str) -> etree.XPath:
''',
    ),
    (
        '''            elif mt == 'text/plain':
                self.oeb.log.warn(f'{self.href} contains data in TXT format', 'converting to HTML')
                data = self._parse_txt(data)
                self.media_type = XHTML_MIME
            self._data = data
            return data

        @data.setter
        def data(self, value: ItemData | None) -> None:
            self._data = value
''',
        '''            elif mt == 'text/plain':
                self.oeb.log.warn(f'{self.href} contains data in TXT format', 'converting to HTML')
                data = self._parse_txt(data)
                self.media_type = XHTML_MIME
            if data is not self._data:
                order_document_elements(data)
            self._data = data
            return data

        @data.setter
        def data(self, value: ItemData | None) -> None:
            order_document_elements(value)
            self._data = value
''',
    ),
]
