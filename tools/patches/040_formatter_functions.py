"""utils/formatter_functions.py imports two constants from calibre.db, which
is not vendored; inline them."""

TARGET = 'utils/formatter_functions.py'

REPLACEMENTS = [
    (
        'from ebook_convert.db.constants import DATA_DIR_NAME, DATA_FILE_PATTERN\n',
        "DATA_DIR_NAME = 'data'  # ebook-convert: from calibre.db.constants\nDATA_FILE_PATTERN = f'{DATA_DIR_NAME}/**/*'\n",
    ),
]
