
import os
from io import BytesIO

from PIL import Image, ImageOps

from ebook_convert.ebooks.mobi import MAX_THUMB_DIMEN, MAX_THUMB_SIZE
from ebook_convert.ebooks.mobi.utils import (rescale_image, mobify_image,
        write_font_record)
from ebook_convert.ebooks import generate_masthead
from ebook_convert.ebooks.oeb.base import OEB_RASTER_IMAGES
from ebook_convert.ptempfile import PersistentTemporaryFile
from ebook_convert.utils.imghdr import what


__license__ = 'GPL v3'
__copyright__ = '2012, Kovid Goyal <kovid@kovidgoyal.net>'
__docformat__ = 'restructuredtext en'

# Image formats that can be read but that no MOBI/AZW3 viewer can display, so
# they are converted to PNG before being added to the book
UNSUPPORTED_IMAGE_TYPES = frozenset({'image/webp', 'image/avif', 'image/jxl'})

PLACEHOLDER_GIF = (b'GIF89a\x01\x00\x01\x00\xf0\x00\x00\x00\x00\x00\xff\xff'
                   b'\xff!\xf9\x04\x01\x00\x00\x00\x00!\xfe calibre-placeho'
                   b'lder-gif-for-azw3\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
                   b'\x00\x02\x02D\x01\x00;')


def process_jpegs_for_amazon(data):
    '''
    Amazon's MOBI renderer cannot render JPEG images without a JFIF (APP0)
    segment and images with EXIF data are not displayed on the cover screen.
    Re-encode JPEG images that lack JFIF metadata or carry EXIF data, applying
    any EXIF orientation first so that the picture stays upright. Other image
    formats and JPEGs that need no change are returned untouched.
    '''
    try:
        img = Image.open(BytesIO(data))
    except Exception:
        return data
    if img.format != 'JPEG':
        return data
    # img.info is empty for JPEGs with neither JFIF nor EXIF (nor other)
    # metadata segments
    changed = not img.info
    # Check for the EXIF segment via img.info, not the tag count, so that
    # empty EXIF segments (APP1 marker with zero entries) are also detected
    has_exif = 'exif' in img.info
    if hasattr(img, 'getexif'):
        exif = img.getexif()
        if exif.get(0x0112) in (2, 3, 4, 5, 6, 7, 8):
            changed = True
            img = ImageOps.exif_transpose(img)
    if changed or has_exif:
        if img.mode not in ('RGB', 'L', 'CMYK'):
            img = img.convert('RGB')
        out = BytesIO()
        # Saving without an exif= argument drops the APP1 segment and Pillow
        # always writes a JFIF APP0 header
        img.save(out, 'JPEG', quality=95)
        data = out.getvalue()
    return data


class Resources(object):

    def __init__(self, oeb, opts, is_periodical, add_fonts=False,
            process_images=True):
        self.oeb, self.log, self.opts = oeb, oeb.log, opts
        self.is_periodical = is_periodical
        self.process_images = process_images

        self.item_map = {}
        self.records = []
        self.mime_map = {}
        self.masthead_offset = 0
        self.used_image_indices = set()
        self.image_indices = set()
        self.cover_offset = self.thumbnail_offset = None
        self.has_fonts = False

        self.add_resources(add_fonts)

    def process_image(self, data):
        if not self.process_images:
            return process_jpegs_for_amazon(data)
        func = mobify_image if self.opts.mobi_keep_original_images else rescale_image
        try:
            return process_jpegs_for_amazon(func(data))
        except Exception:
            ext = what(None, data)
            if ext not in ('png', 'gif'):
                raise
            if ext == 'gif':
                with PersistentTemporaryFile(suffix='.gif') as pt:
                    pt.write(data)
                    return mobify_image(data)

            with PersistentTemporaryFile(suffix='.png') as pt:
                pt.write(data)
            try:
                from ebook_convert.utils.img import optimize_png
                optimize_png(pt.name)
                data = open(pt.name, 'rb').read()
            finally:
                os.remove(pt.name)
            return func(data)

    def add_resources(self, add_fonts):
        oeb = self.oeb
        oeb.logger.info('Serializing resources...')
        index = 1

        mh_href = None
        if 'masthead' in oeb.guide and oeb.guide['masthead'].href:
            mh_href = oeb.guide['masthead'].href
            self.records.append(None)
            index += 1
            self.used_image_indices.add(0)
            self.image_indices.add(0)
        elif self.is_periodical:
            # Generate a default masthead
            data = generate_masthead(str(self.oeb.metadata['title'][0]))
            self.records.append(data)
            self.used_image_indices.add(0)
            self.image_indices.add(0)
            index += 1

        cover_href = self.cover_offset = self.thumbnail_offset = None
        if (oeb.metadata.cover and
                str(oeb.metadata.cover[0]) in oeb.manifest.ids):
            cover_id = str(oeb.metadata.cover[0])
            item = oeb.manifest.ids[cover_id]
            cover_href = item.href

        for item in self.oeb.manifest.values():
            if item.media_type not in OEB_RASTER_IMAGES:
                continue
            if item.media_type.lower() in UNSUPPORTED_IMAGE_TYPES:
                self.convert_unsupported_image(item)
            try:
                data = self.process_image(item.data)
            except Exception:
                self.log.warning('Bad image file %r', item.href)
                continue
            else:
                if mh_href and item.href == mh_href:
                    self.records[0] = data
                    continue

                self.image_indices.add(len(self.records))
                self.records.append(data)
                self.item_map[item.href] = index
                self.mime_map[item.href] = 'image/%s'%what(None, data)
                index += 1

                if cover_href and item.href == cover_href:
                    self.cover_offset = self.item_map[item.href] - 1
                    self.used_image_indices.add(self.cover_offset)
                    try:
                        # Build the thumbnail from the processed data so that
                        # it is upright and free of EXIF metadata as well
                        tdata = rescale_image(data, dimen=MAX_THUMB_DIMEN,
                            maxsizeb=MAX_THUMB_SIZE)
                    except Exception as err:
                        self.log.warning('Failed to generate thumbnail: %s',
                                         err)
                    else:
                        self.image_indices.add(len(self.records))
                        self.records.append(tdata)
                        self.thumbnail_offset = index - 1
                        self.used_image_indices.add(self.thumbnail_offset)
                        index += 1
            finally:
                item.unload_data_from_memory()

        if add_fonts:
            for item in self.oeb.manifest.values():
                if item.href and item.href.rpartition('.')[-1].lower() in {
                        'ttf', 'otf'} and isinstance(item.data, bytes):
                    self.records.append(write_font_record(item.data))
                    self.item_map[item.href] = len(self.records)
                    self.has_fonts = True

    def convert_unsupported_image(self, item):
        '''
        Convert an image in a format no Kindle can display (WebP, AVIF, JXL)
        to PNG, in place, updating the manifest item's media type.
        '''
        from ebook_convert.utils.img import (image_and_format_from_data,
                                             image_to_data)
        try:
            img, fmt = image_and_format_from_data(item.data)
        except Exception as err:
            self.log.warning('Could not decode %s image %s: %s',
                             item.media_type, item.href, err)
            return
        if 'image/%s' % fmt in UNSUPPORTED_IMAGE_TYPES and not img.isNull():
            self.log.info('Converting %s image %s to PNG', fmt.upper(),
                          item.href)
            item.data = image_to_data(img, fmt='PNG')
            item.media_type = 'image/png'

    def add_extra_images(self):
        '''
        Add any images that were created after the call to add_resources()
        '''
        for item in self.oeb.manifest.values():
            if (item.media_type not in OEB_RASTER_IMAGES or item.href in self.item_map):
                continue
            if item.media_type.lower() in UNSUPPORTED_IMAGE_TYPES:
                self.convert_unsupported_image(item)
            try:
                data = self.process_image(item.data)
            except Exception:
                self.log.warning('Bad image file %r', item.href)
            else:
                self.records.append(data)
                self.item_map[item.href] = len(self.records)
            finally:
                item.unload_data_from_memory()

    def serialize(self, records, used_images):
        used_image_indices = self.used_image_indices | {
                v-1 for k, v in self.item_map.items() if k in used_images}
        for i in self.image_indices-used_image_indices:
            self.records[i] = PLACEHOLDER_GIF
        records.extend(self.records)

    def __bool__(self):
        return bool(self.records)
    __nonzero__ = __bool__
