# License: GPLv3 Copyright: 2009, John Schember <john@nachtimwald.com>

from __future__ import annotations
import io
import os
from typing import TYPE_CHECKING

from ebook_convert.customize.conversion import InputFormatPlugin, OptionRecommendation, OutputFormatPlugin
from ebook_convert.ptempfile import TemporaryDirectory
from ebook_convert.utils.localization import _

if TYPE_CHECKING:
    from optparse import Values

    from ebook_convert.ebooks.oeb.base import Manifest, OEBBook
    from ebook_convert.utils.logging import Log


class PMLOutput(OutputFormatPlugin):
    name = 'PML Output'
    author = 'John Schember'
    file_type = 'pmlz'
    commit_name = 'pml_output'

    options = {
        OptionRecommendation(
            name='pml_output_encoding',
            recommended_value='cp1252',
            level=OptionRecommendation.LOW,
            help=_('Specify the character encoding of the output document. The default is cp1252.'),
        ),
        OptionRecommendation(
            name='inline_toc',
            recommended_value=False,
            level=OptionRecommendation.LOW,
            help=_('Add Table of Contents to beginning of the book.'),
        ),
        OptionRecommendation(
            name='full_image_depth',
            recommended_value=False,
            level=OptionRecommendation.LOW,
            help=_(
                'Do not reduce the size or bit depth of images. Images '
                'have their size and depth reduced by default to accommodate '
                'applications that can not convert images on their '
                'own such as Dropbook.'
            ),
        ),
    }

    def convert(self, oeb_book: OEBBook, output: str, input_plugin: InputFormatPlugin, opts: Values, log: Log) -> None:
        output_path = output
        from ebook_convert.ebooks.pml.pmlml import PMLMLizer
        from ebook_convert.utils.zipfile import ZipFile

        with TemporaryDirectory('_pmlz_output') as tdir:
            pmlmlizer = PMLMLizer(log)
            pml = str(pmlmlizer.extract_content(oeb_book, opts))
            with open(os.path.join(tdir, 'index.pml'), 'wb') as out:
                out.write(pml.encode(opts.pml_output_encoding, 'replace'))

            img_path = os.path.join(tdir, 'index_img')
            if not os.path.exists(img_path):
                os.makedirs(img_path)
            self.write_images(oeb_book.manifest, pmlmlizer.image_hrefs, img_path, opts)

            log.debug('Compressing output...')
            pmlz = ZipFile(output_path, 'w')
            pmlz.add_dir(tdir)

    def write_images(self, manifest: Manifest, image_hrefs: dict[str, str], out_dir: str, opts: Values) -> None:
        from PIL import Image

        from ebook_convert.ebooks.oeb.base import OEB_RASTER_IMAGES

        for item in manifest:
            if item.media_type in OEB_RASTER_IMAGES and item.href in image_hrefs.keys():
                raw = item.data
                assert isinstance(raw, bytes)
                if opts.full_image_depth:
                    im = Image.open(io.BytesIO(raw))
                else:
                    im = Image.open(io.BytesIO(raw)).convert('P')
                    im.thumbnail((300, 300), Image.Resampling.LANCZOS)

                data = io.BytesIO()
                im.save(data, 'PNG')
                data = data.getvalue()

                path = os.path.join(out_dir, image_hrefs[item.href])

                with open(path, 'wb') as out:
                    out.write(data)
