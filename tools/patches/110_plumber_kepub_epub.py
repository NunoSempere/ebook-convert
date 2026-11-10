"""Kobo names its files ``book.kepub.epub``.  Treat that double extension as
the KEPUB format on both sides, so ``ebook-convert in.epub out.kepub.epub``
produces a KEPUB instead of a plain EPUB and ``ebook-convert in.kepub.epub
out.epub`` strips the Kobo markup (plain ``.kepub`` works as well)."""

TARGET = 'ebooks/conversion/plumber.py'

REPLACEMENTS = [
    (
        """        input_fmt = input_fmt[1:].lower().replace('original_', '')
        if view_kepub and input_fmt.lower() == 'kepub':
""",
        """        input_fmt = input_fmt[1:].lower().replace('original_', '')
        if self.input.lower().endswith('.kepub.epub'):
            input_fmt = 'kepub'
        if view_kepub and input_fmt.lower() == 'kepub':
""",
    ),
    (
        '''            output_fmt = os.path.splitext(self.output)[1]
            if not output_fmt:
                output_fmt = '.oeb'
''',
        '''            output_fmt = os.path.splitext(self.output)[1]
            if self.output.lower().endswith('.kepub.epub'):
                output_fmt = '.kepub'
            if not output_fmt:
                output_fmt = '.oeb'
''',
    ),
]
