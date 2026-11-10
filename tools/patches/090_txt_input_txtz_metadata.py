"""TXT input: when reading a TXTZ archive, ``file_ext`` is reassigned to the
extension of the text file found inside the archive, so the metadata reader
was later asked for *txt* metadata of the zip stream and the title/authors in
metadata.opf were lost.  Remember the container format for the metadata
lookup."""

TARGET = 'ebooks/conversion/plugins/txt_input.py'

REPLACEMENTS = [
    (
        """        # Extract content from zip archive.
        if file_ext == 'txtz':
""",
        """        # Extract content from zip archive.
        container_ext = file_ext  # ebook-convert: metadata must be read from the archive, not the inner .txt
        if file_ext == 'txtz':
""",
    ),
    (
        """            input_mi = get_file_type_metadata(stream, file_ext)
""",
        """            input_mi = get_file_type_metadata(stream, container_ext)
""",
    ),
]
