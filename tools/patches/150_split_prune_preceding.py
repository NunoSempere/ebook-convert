"""polish/split.py: pruning the second half of a split document replaced
every element before the split point by its children with a slice
assignment on the parent, which is O(number of siblings) per element and so
quadratic on wide documents (a MOBI converted to one HTML file).  Removing
the preceding siblings along the ancestor path gives the same tree: the
ancestors keep their tags with their text cleared, everything else before
the split point goes, including tails."""

TARGET = 'ebooks/oeb/polish/split.py'

REPLACEMENTS = [
    (
        """    # Tree 2
    ancestors = frozenset(XPath('ancestor::*')(split_point2))
    for elem in tuple(body2.iterdescendants()):
        if elem is split_point2:
            if not before:
                # Keep the split point element's tail, if it contains non-whitespace
                # text
                tail = elem.tail
                if tail and not tail.isspace():
                    parent = elem.getparent()
                    idx = parent.index(elem)
                    if idx == 0:
                        parent.text = (parent.text or '') + tail
                    else:
                        sib = parent[idx - 1]
                        sib.tail = (sib.tail or '') + tail
                # Remove the element itself
                nix_element(elem)
            break
        if elem in ancestors:
            # We have to preserve the ancestors as they could have CSS
            # styles that are inherited/applicable, like font or
            # width. So we only remove the text, if any.
            elem.text = '\\n'
        else:
            nix_element(elem, top=False)

    body2.text = '\\n'
""",
        """    # Tree 2 (ebook-convert: linear-time pruning, see tools/patches)
    # Remove everything before the split point: walk up from it and drop the
    # preceding siblings at each level. The ancestors are kept, as they could
    # have CSS styles that are inherited/applicable, like font or width, with
    # their text removed.
    node = split_point2
    while node is not body2:
        parent = cast('_Element', node.getparent())
        for sib in tuple(parent):
            if sib is node:
                break
            parent.remove(sib)
        if parent is not body2:
            parent.text = '\\n'
        node = parent
    if not before:
        elem = split_point2
        # Keep the split point element's tail, if it contains non-whitespace
        # text
        tail = elem.tail
        if tail and not tail.isspace():
            parent = elem.getparent()
            parent.text = (parent.text or '') + tail
        # Remove the element itself
        nix_element(elem)

    body2.text = '\\n'
""",
    ),
]
