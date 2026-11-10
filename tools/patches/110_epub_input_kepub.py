"""EPUB input: removing Kobo markup from KEPUB files needs
calibre.ebooks.oeb.polish.kepubify, which depends on the content server's
renderer and ICU's sentence iterator (not vendored).  Convert KEPUB files as
plain EPUB and say so, instead of crashing."""

TARGET = 'ebooks/conversion/plugins/epub_input.py'

REPLACEMENTS = [
    (
        '''        from ebook_convert.ebooks.oeb.polish.container import Container
        from ebook_convert.ebooks.oeb.polish.errors import drm_message
        from ebook_convert.ebooks.oeb.polish.kepubify import check_for_kobo_drm, unkepubify_container

        container = Container(os.getcwd(), opf, log)
        if self.for_viewer:
            log('Checking for Kobo DRM...')
            with drm_message(_('The file {} is locked with DRM. It cannot be viewed').format(path)):
                check_for_kobo_drm(container)
        else:
            log('Removing Kobo markup...')
            with drm_message(_('The file {} is locked with DRM. It cannot be converted').format(path)):
                unkepubify_container(container)
                container.commit()
''',
        '''        # ebook-convert: the kepubifier is not included; the Kobo <span> markup
        # is harmless for conversion and is left in place.
        log.warn('KEPUB input is converted as a plain EPUB (Kobo markup is not removed)')
''',
    ),
]
