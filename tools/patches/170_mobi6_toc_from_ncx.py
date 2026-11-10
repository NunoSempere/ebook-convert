"""mobi/reader/mobi6.py: build the table of contents of a MOBI 6 file from
its NCX index.

Calibre's MOBI 6 reader only knows the inline HTML contents page (the links
after the guide's "toc" anchor), which publishers often keep to the top
level, and ignores the NCX index record that holds the full, possibly
nested, TOC and that Kindles navigate by.  Here the NCX entries are read
(the KF8 reader already does this), anchors are added at their positions
and, when the NCX has more entries than the inline page, it becomes the TOC."""

TARGET = 'ebooks/mobi/reader/mobi6.py'

REPLACEMENTS = [
    (
        '''from ebook_convert.ebooks.mobi.reader.headers import BookHeader
''',
        '''from ebook_convert.ebooks.mobi.reader.headers import NULL_INDEX, BookHeader
''',
    ),
    (
        '''    def add_anchors(self) -> None:
        self.log.debug('Adding anchors...')
        positions = set()
        link_pattern = re.compile(rb\'\'\'<[^<>]+filepos=['"]{0,1}(\\d+)[^<>]*>\'\'\', re.IGNORECASE)
        for match in link_pattern.finditer(self.mobi_html):
            positions.add(int(match.group(1)))
''',
        '''    def read_ncx_entries(self) -> list:
        """The entries of the NCX index record (text, pos, parent, ...), or []."""
        cached = getattr(self, '_ncx_entries', None)
        if cached is not None:
            return cached
        self._ncx_entries = []
        idx = getattr(self.book_header, 'ncxidx', NULL_INDEX)
        if idx and idx != NULL_INDEX and 0 < idx < len(self.sections):
            try:
                from ebook_convert.ebooks.mobi.reader.ncx import read_ncx

                self._ncx_entries = [
                    e for e in read_ncx(self.sections, idx, self.book_header.codec)
                    if e.get('text') and isinstance(e.get('pos'), int) and e['pos'] >= 0
                ]
            except Exception as err:
                self.log.warn(f'Failed to read the NCX index of this MOBI file: {err}')
        return self._ncx_entries

    def toc_from_ncx(self, htmlfile: str) -> TOC | None:
        entries = self.read_ncx_entries()
        if not entries:
            return None
        toc = TOC()
        nodes: dict[int, TOC] = {}
        for entry in entries:
            parent = nodes.get(entry.get('parent', -1), toc)
            nodes[entry['num']] = parent.add_item(htmlfile, f"filepos{entry['pos']}", entry['text'])
        return toc

    def add_anchors(self) -> None:
        self.log.debug('Adding anchors...')
        positions = set()
        link_pattern = re.compile(rb\'\'\'<[^<>]+filepos=['"]{0,1}(\\d+)[^<>]*>\'\'\', re.IGNORECASE)
        for match in link_pattern.finditer(self.mobi_html):
            positions.add(int(match.group(1)))
        for entry in self.read_ncx_entries():  # ebook-convert: TOC entries from the NCX index
            positions.add(entry['pos'])
''',
    ),
    (
        '''            if tocobj is not None:
                tocobj = self.structure_toc(tocobj)
                opf.set_toc(tocobj)

        return opf, ncx_manifest_entry
''',
        '''            if tocobj is not None:
                tocobj = self.structure_toc(tocobj)
        else:
            tocobj = None
        # ebook-convert: prefer the NCX index when it has more entries than
        # the inline contents page (publishers often keep that to the top level)
        ncx_toc = self.toc_from_ncx(os.path.basename(htmlfile))
        if ncx_toc is not None and (tocobj is None or sum(1 for _ in ncx_toc.flat()) > sum(1 for _ in tocobj.flat())):
            self.log.debug('Using the table of contents from the NCX index')
            tocobj = ncx_toc
        if tocobj is not None:
            ncx_manifest_entry = 'toc.ncx'
            opf.set_toc(tocobj)

        return opf, ncx_manifest_entry
''',
    ),
]
