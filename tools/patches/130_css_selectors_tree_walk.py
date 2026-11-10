"""css_selectors/select.py: build the id and class maps by walking the tree
instead of evaluating ``//*[@id]`` / ``//*[@class]``.

On some real-world trees (a MOBI converted to one HTML file whose <body> has
100,000 children) libxml2 takes minutes for that XPath while a Python walk
takes well under a second; the maps are built once per document, so the
walk costs nothing elsewhere."""

TARGET = 'css_selectors/select.py'

REPLACEMENTS = [
    (
        """    def iteridtags(self):
        return get_compiled_xpath('//*[@id]')(self.root)

    def iterclasstags(self):
        return get_compiled_xpath('//*[@class]')(self.root)
""",
        """    def iteridtags(self):
        # ebook-convert: a tree walk; the XPath is pathologically slow on very wide trees
        return [elem for elem in self.root.iter('*') if elem.get('id') is not None]

    def iterclasstags(self):
        return [elem for elem in self.root.iter('*') if elem.get('class') is not None]
""",
    ),
]
