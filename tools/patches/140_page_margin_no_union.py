"""page_margin.py: ``descendant::h:p|descendant::h:div`` is a union, which
makes libxml2 sort the node set with a pairwise comparison that walks
sibling lists.  On a <body> with 100,000 children that takes minutes; the
equivalent single-step expression returns the same nodes in document order
in a fraction of a second."""

TARGET = 'ebooks/oeb/transforms/page_margin.py'

REPLACEMENTS = [
    (
        "        paras = XPath('descendant::h:p|descendant::h:div')\n",
        "        paras = XPath('descendant::*[self::h:p or self::h:div]')  # ebook-convert: no union, see tools/patches\n",
    ),
]
