import importlib.resources
import mimetypes


mimetypes.init([str(importlib.resources.
                files('ebook_convert') / 'data/mime.types')])
