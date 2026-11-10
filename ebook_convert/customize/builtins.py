# License: GPLv3 Copyright: 2008, Kovid Goyal <kovid at kovidgoyal.net>

from __future__ import annotations
import glob
import os
from typing import IO, TYPE_CHECKING

from ebook_convert.constants import ismacos, numeric_version
from ebook_convert.customize import FileTypePlugin, InterfaceActionBase, MetadataReaderPlugin, MetadataWriterPlugin, Plugin, PreferencesPlugin, StoreBase
from ebook_convert.ebooks.html.to_zip import HTML2ZIP
from ebook_convert.ebooks.metadata.archive import ArchiveExtract, KPFExtract, get_comic_metadata
from ebook_convert.utils.localization import _

if TYPE_CHECKING:
    from qt.core import QWidget

    from ebook_convert.ebooks.metadata.book.base import Metadata
    from ebook_convert.gui2.preferences import ConfigWidgetBase

plugins: list[type[Plugin]] = []

# To archive plugins {{{


class PML2PMLZ(FileTypePlugin):
    name = 'PML to PMLZ'
    author = 'John Schember'
    description = _(
        'Create a PMLZ archive containing the PML file '
        'and all images in the folder pmlname_img or images. '
        'This plugin is run every time you add '
        'a PML file to the library.'
    )
    version = numeric_version
    file_types = {'pml'}
    supported_platforms = ['windows', 'osx', 'linux']
    on_import = True

    def run(self, path_to_ebook: str) -> str:
        import zipfile

        of = self.temporary_file('_plugin_pml2pmlz.pmlz')
        pmlz = zipfile.ZipFile(of.name, 'w')
        pmlz.write(path_to_ebook, os.path.basename(path_to_ebook), zipfile.ZIP_DEFLATED)

        pml_img = os.path.splitext(path_to_ebook)[0] + '_img'
        i_img = os.path.join(os.path.dirname(path_to_ebook), 'images')
        img_dir = pml_img if os.path.isdir(pml_img) else i_img if os.path.isdir(i_img) else ''
        if img_dir:
            for image in glob.glob(os.path.join(img_dir, '*.png')):
                pmlz.write(image, os.path.join('images', (os.path.basename(image))))
        pmlz.close()

        return of.name


class TXT2TXTZ(FileTypePlugin):
    name = 'TXT to TXTZ'
    author = 'John Schember'
    description = _(
        'Create a TXTZ archive when a TXT file is imported '
        'containing Markdown or Textile references to images. The referenced '
        'images as well as the TXT file are added to the archive.'
    )
    version = numeric_version
    file_types = {'txt', 'text', 'md', 'markdown', 'textile'}
    supported_platforms = ['windows', 'osx', 'linux']
    on_import = True

    def run(self, path_to_ebook: str) -> str:
        from ebook_convert.ebooks.metadata.opf2 import metadata_to_opf
        from ebook_convert.ebooks.txt.processor import get_images_from_polyglot_text

        with open(path_to_ebook, 'rb') as ebf:
            txt = ebf.read().decode('utf-8', 'replace')
        base_dir = os.path.dirname(path_to_ebook)
        ext = path_to_ebook.rpartition('.')[-1].lower()
        images = get_images_from_polyglot_text(txt, base_dir, ext)

        if images:
            # Create TXTZ and put file plus images inside of it.
            import zipfile

            of = self.temporary_file('_plugin_txt2txtz.txtz')
            txtz = zipfile.ZipFile(of.name, 'w')
            # Add selected TXT file to archive.
            txtz.write(path_to_ebook, os.path.basename(path_to_ebook), zipfile.ZIP_DEFLATED)
            # metadata.opf
            if os.path.exists(os.path.join(base_dir, 'metadata.opf')):
                txtz.write(os.path.join(base_dir, 'metadata.opf'), 'metadata.opf', zipfile.ZIP_DEFLATED)
            else:
                from ebook_convert.ebooks.metadata.txt import get_metadata

                with open(path_to_ebook, 'rb') as ebf:
                    mi = get_metadata(ebf)
                opf = metadata_to_opf(mi)
                txtz.writestr('metadata.opf', opf, zipfile.ZIP_DEFLATED)
            # images
            for image in images:
                txtz.write(os.path.join(base_dir, image), image)
            txtz.close()

            return of.name
        else:
            # No images so just import the TXT file.
            return path_to_ebook


plugins += [HTML2ZIP, PML2PMLZ, TXT2TXTZ, ArchiveExtract, KPFExtract]
# }}}

# Metadata reader plugins {{{


class ComicMetadataReader(MetadataReaderPlugin):
    name = 'Read comic metadata'
    file_types = {'cbr', 'cbz', 'cb7', 'cbc'}
    description = _('Extract cover from comic files')

    def customization_help(self, gui: bool = False) -> str:
        return 'Read series number from volume or issue number. Default is volume, set this to issue to use issue number instead.'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        if type == 'cbc':
            from zipfile import ZipFile

            zf = ZipFile(stream)
            fcn = zf.open('comics.txt').read().decode('utf-8').splitlines()[0]
            oname = getattr(stream, 'name', None)
            stream = zf.open(fcn)
            type = fcn.split('.')[-1].lower()
            if oname:
                setattr(stream, 'name', oname)
        if hasattr(stream, 'seek') and hasattr(stream, 'tell'):
            pos = stream.tell()
            id_ = stream.read(3)
            stream.seek(pos)
            if id_ == b'Rar':
                type = 'cbr'
            elif id_.startswith(b'PK'):
                type = 'cbz'
            elif id_.startswith(b'7z'):
                type = 'cb7'
        if type == 'cbr':
            from ebook_convert.utils.unrar import extract_cover_image
        elif type == 'cb7':
            from ebook_convert.utils.seven_zip import extract_cover_image
        else:
            from ebook_convert.libunzip import extract_cover_image
        from ebook_convert.ebooks.metadata import MetaInformation

        ret = extract_cover_image(stream)
        mi = MetaInformation(None, None)
        stream.seek(0)
        if type in {'cbr', 'cbz'}:
            series_index = self.site_customization
            if series_index not in {'volume', 'issue'}:
                series_index = 'volume'
            try:
                mi.smart_update(get_comic_metadata(stream, type, series_index=series_index))
            except Exception:
                pass
        if ret is not None:
            path, data = ret
            ext = os.path.splitext(path)[1][1:]
            mi.cover_data = (ext.lower(), data)
        return mi


class CHMMetadataReader(MetadataReaderPlugin):
    name = 'Read CHM metadata'
    file_types = {'chm'}
    description = _('Read metadata from %s files') % 'CHM'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.chm.metadata import get_metadata

        return get_metadata(stream)


class EPUBMetadataReader(MetadataReaderPlugin):
    name = 'Read EPUB metadata'
    file_types = {'epub', 'kepub'}
    description = _('Read metadata from EPUB and KEPUB files')

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.epub import get_metadata, get_quick_metadata

        if self.quick:
            return get_quick_metadata(stream, ftype=type)
        return get_metadata(stream, ftype=type)


class FB2MetadataReader(MetadataReaderPlugin):
    name = 'Read FB2 metadata'
    file_types = {'fb2', 'fbz'}
    description = _('Read metadata from %s files') % 'FB2'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.fb2 import get_metadata

        return get_metadata(stream)


class HTMLMetadataReader(MetadataReaderPlugin):
    name = 'Read HTML metadata'
    file_types = {'html'}
    description = _('Read metadata from %s files') % 'HTML'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.html import get_metadata

        return get_metadata(stream)


class HTMLZMetadataReader(MetadataReaderPlugin):
    name = 'Read HTMLZ metadata'
    file_types = {'htmlz'}
    description = _('Read metadata from %s files') % 'HTMLZ'
    author = 'John Schember'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.extz import get_metadata

        return get_metadata(stream)


class IMPMetadataReader(MetadataReaderPlugin):
    name = 'Read IMP metadata'
    file_types = {'imp'}
    description = _('Read metadata from %s files') % 'IMP'
    author = 'Ashish Kulkarni'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.imp import get_metadata

        return get_metadata(stream)


class LITMetadataReader(MetadataReaderPlugin):
    name = 'Read LIT metadata'
    file_types = {'lit'}
    description = _('Read metadata from %s files') % 'LIT'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.lit import get_metadata

        return get_metadata(stream)


class LRFMetadataReader(MetadataReaderPlugin):
    name = 'Read LRF metadata'
    file_types = {'lrf'}
    description = _('Read metadata from %s files') % 'LRF'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.lrf.meta import get_metadata

        return get_metadata(stream)


class LRXMetadataReader(MetadataReaderPlugin):
    name = 'Read LRX metadata'
    file_types = {'lrx'}
    description = _('Read metadata from %s files') % 'LRX'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.lrx import get_metadata

        return get_metadata(stream)


class MOBIMetadataReader(MetadataReaderPlugin):
    name = 'Read MOBI metadata'
    file_types = {'mobi', 'prc', 'azw', 'azw3', 'azw4', 'pobi'}
    description = _('Read metadata from %s files') % 'MOBI'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.mobi import get_metadata

        return get_metadata(stream)


class ODTMetadataReader(MetadataReaderPlugin):
    name = 'Read ODT metadata'
    file_types = {'odt'}
    description = _('Read metadata from %s files') % 'ODT'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.odt import get_metadata

        return get_metadata(stream)


class DocXMetadataReader(MetadataReaderPlugin):
    name = 'Read DOCX metadata'
    file_types = {'docx'}
    description = _('Read metadata from %s files') % 'DOCX'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.docx import get_metadata

        return get_metadata(stream)


class OPFMetadataReader(MetadataReaderPlugin):
    name = 'Read OPF metadata'
    file_types = {'opf'}
    description = _('Read metadata from %s files') % 'OPF'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.opf import get_metadata

        return get_metadata(stream)[0]


class PDBMetadataReader(MetadataReaderPlugin):
    name = 'Read PDB metadata'
    file_types = {'pdb', 'updb'}
    description = _('Read metadata from %s files') % 'PDB'
    author = 'John Schember'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.pdb import get_metadata

        return get_metadata(stream)


class PDFMetadataReader(MetadataReaderPlugin):
    name = 'Read PDF metadata'
    file_types = {'pdf'}
    description = _('Read metadata from %s files') % 'PDF'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.pdf import get_metadata, get_quick_metadata

        if self.quick:
            return get_quick_metadata(stream)
        return get_metadata(stream)


class PMLMetadataReader(MetadataReaderPlugin):
    name = 'Read PML metadata'
    file_types = {'pml', 'pmlz'}
    description = _('Read metadata from %s files') % 'PML'
    author = 'John Schember'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.pml import get_metadata

        return get_metadata(stream)


class RARMetadataReader(MetadataReaderPlugin):
    name = 'Read RAR metadata'
    file_types = {'rar'}
    description = _('Read metadata from e-books in RAR archives')

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.rar import get_metadata

        return get_metadata(stream)


class RBMetadataReader(MetadataReaderPlugin):
    name = 'Read RB metadata'
    file_types = {'rb'}
    description = _('Read metadata from %s files') % 'RB'
    author = 'Ashish Kulkarni'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.rb import get_metadata

        return get_metadata(stream)


class RTFMetadataReader(MetadataReaderPlugin):
    name = 'Read RTF metadata'
    file_types = {'rtf'}
    description = _('Read metadata from %s files') % 'RTF'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.rtf import get_metadata

        return get_metadata(stream)


class SNBMetadataReader(MetadataReaderPlugin):
    name = 'Read SNB metadata'
    file_types = {'snb'}
    description = _('Read metadata from %s files') % 'SNB'
    author = 'Li Fanxi'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.snb import get_metadata

        return get_metadata(stream)


class TOPAZMetadataReader(MetadataReaderPlugin):
    name = 'Read Topaz metadata'
    file_types = {'tpz', 'azw1'}
    description = _('Read metadata from %s files') % 'MOBI'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.topaz import get_metadata

        return get_metadata(stream)


class TXTMetadataReader(MetadataReaderPlugin):
    name = 'Read TXT metadata'
    file_types = {'txt'}
    description = _('Read metadata from %s files') % 'TXT'
    author = 'John Schember'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.txt import get_metadata

        return get_metadata(stream)


class TXTZMetadataReader(MetadataReaderPlugin):
    name = 'Read TXTZ metadata'
    file_types = {'txtz'}
    description = _('Read metadata from %s files') % 'TXTZ'
    author = 'John Schember'

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.extz import get_metadata

        return get_metadata(stream)


class ZipMetadataReader(MetadataReaderPlugin):
    name = 'Read ZIP metadata'
    file_types = {'zip', 'oebzip'}
    description = _('Read metadata from e-books in ZIP archives')

    def get_metadata(self, stream: IO[bytes], type: str) -> Metadata:
        from ebook_convert.ebooks.metadata.zip import get_metadata

        return get_metadata(stream)


plugins += [x for x in list(locals().values()) if isinstance(x, type) and x.__name__.endswith('MetadataReader')]

# }}}

# Metadata writer plugins {{{


class EPUBMetadataWriter(MetadataWriterPlugin):
    name = 'Set EPUB metadata'
    file_types = {'epub', 'kepub'}
    description = _('Set metadata in EPUB and KEPUB files')

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.epub import set_metadata

        q = self.site_customization or ''
        set_metadata(
            stream,
            mi,
            apply_null=self.apply_null,
            force_identifiers=self.force_identifiers,
            ftype=type,
            add_missing_cover='disable-add-missing-cover' != q or type == 'kepub',
        )

    def customization_help(self, gui: bool = False) -> str:
        h = 'disable-add-missing-cover'
        if gui:
            h = '<i>' + h + '</i>'
        return _('Enter {0} below to have the EPUB metadata writer plugin not add cover images to EPUB files that have no existing cover image.').format(h)


class FB2MetadataWriter(MetadataWriterPlugin):
    name = 'Set FB2 metadata'
    file_types = {'fb2', 'fbz'}
    description = _('Set metadata in %s files') % 'FB2'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.fb2 import set_metadata

        set_metadata(stream, mi, apply_null=self.apply_null)


class HTMLZMetadataWriter(MetadataWriterPlugin):
    name = 'Set HTMLZ metadata'
    file_types = {'htmlz'}
    description = _('Set metadata from %s files') % 'HTMLZ'
    author = 'John Schember'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.extz import set_metadata

        set_metadata(stream, mi)


class LRFMetadataWriter(MetadataWriterPlugin):
    name = 'Set LRF metadata'
    file_types = {'lrf'}
    description = _('Set metadata in %s files') % 'LRF'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.lrf.meta import set_metadata

        set_metadata(stream, mi)


class MOBIMetadataWriter(MetadataWriterPlugin):
    name = 'Set MOBI metadata'
    file_types = {'mobi', 'prc', 'azw', 'azw3', 'azw4'}
    description = _('Set metadata in %s files') % 'MOBI'
    author = 'Marshall T. Vandegrift'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.mobi import set_metadata

        set_metadata(stream, mi)


class PDBMetadataWriter(MetadataWriterPlugin):
    name = 'Set PDB metadata'
    file_types = {'pdb'}
    description = _('Set metadata from %s files') % 'PDB'
    author = 'John Schember'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.pdb import set_metadata

        set_metadata(stream, mi)


class PDFMetadataWriter(MetadataWriterPlugin):
    name = 'Set PDF metadata'
    file_types = {'pdf'}
    description = _('Set metadata in %s files') % 'PDF'
    author = 'Kovid Goyal'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.pdf import set_metadata

        set_metadata(stream, mi)


class RTFMetadataWriter(MetadataWriterPlugin):
    name = 'Set RTF metadata'
    file_types = {'rtf'}
    description = _('Set metadata in %s files') % 'RTF'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.rtf import set_metadata

        set_metadata(stream, mi)


class TOPAZMetadataWriter(MetadataWriterPlugin):
    name = 'Set TOPAZ metadata'
    file_types = {'tpz', 'azw1'}
    description = _('Set metadata in %s files') % 'TOPAZ'
    author = 'Greg Riker'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.topaz import set_metadata

        set_metadata(stream, mi)


class TXTZMetadataWriter(MetadataWriterPlugin):
    name = 'Set TXTZ metadata'
    file_types = {'txtz'}
    description = _('Set metadata from %s files') % 'TXTZ'
    author = 'John Schember'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.extz import set_metadata

        set_metadata(stream, mi)


class ODTMetadataWriter(MetadataWriterPlugin):
    name = 'Set ODT metadata'
    file_types = {'odt'}
    description = _('Set metadata from %s files') % 'ODT'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.odt import set_metadata

        return set_metadata(stream, mi)


class DocXMetadataWriter(MetadataWriterPlugin):
    name = 'Set DOCX metadata'
    file_types = {'docx'}
    description = _('Set metadata from %s files') % 'DOCX'

    def set_metadata(self, stream: IO[bytes], mi: Metadata, type: str) -> None:
        from ebook_convert.ebooks.metadata.docx import set_metadata

        return set_metadata(stream, mi)


plugins += [x for x in list(locals().values()) if isinstance(x, type) and x.__name__.endswith('MetadataWriter')]

# }}}

# Conversion plugins {{{
# ebook-convert: only plugins that run without Qt and Calibre C extensions
from ebook_convert.ebooks.conversion.plugins.azw4_input import AZW4Input
from ebook_convert.ebooks.conversion.plugins.docx_input import DOCXInput
from ebook_convert.ebooks.conversion.plugins.docx_output import DOCXOutput
from ebook_convert.ebooks.conversion.plugins.epub_input import EPUBInput
from ebook_convert.ebooks.conversion.plugins.epub_output import EPUBOutput
from ebook_convert.ebooks.conversion.plugins.fb2_input import FB2Input
from ebook_convert.ebooks.conversion.plugins.fb2_output import FB2Output
from ebook_convert.ebooks.conversion.plugins.html_input import HTMLInput
from ebook_convert.ebooks.conversion.plugins.html_output import HTMLOutput
from ebook_convert.ebooks.conversion.plugins.htmlz_input import HTMLZInput
from ebook_convert.ebooks.conversion.plugins.htmlz_output import HTMLZOutput
from ebook_convert.ebooks.conversion.plugins.lrf_input import LRFInput
from ebook_convert.ebooks.conversion.plugins.lrf_output import LRFOutput
from ebook_convert.ebooks.conversion.plugins.mobi_input import MOBIInput
from ebook_convert.ebooks.conversion.plugins.mobi_output import AZW3Output, MOBIOutput
from ebook_convert.ebooks.conversion.plugins.odt_input import ODTInput
from ebook_convert.ebooks.conversion.plugins.oeb_output import OEBOutput
from ebook_convert.ebooks.conversion.plugins.pdb_input import PDBInput
from ebook_convert.ebooks.conversion.plugins.pdb_output import PDBOutput
from ebook_convert.ebooks.conversion.plugins.pdf_input import PDFInput
from ebook_convert.ebooks.conversion.plugins.pml_input import PMLInput
from ebook_convert.ebooks.conversion.plugins.pml_output import PMLOutput
from ebook_convert.ebooks.conversion.plugins.rb_input import RBInput
from ebook_convert.ebooks.conversion.plugins.rb_output import RBOutput
from ebook_convert.ebooks.conversion.plugins.rtf_input import RTFInput
from ebook_convert.ebooks.conversion.plugins.rtf_output import RTFOutput
from ebook_convert.ebooks.conversion.plugins.snb_input import SNBInput
from ebook_convert.ebooks.conversion.plugins.snb_output import SNBOutput
from ebook_convert.ebooks.conversion.plugins.tcr_input import TCRInput
from ebook_convert.ebooks.conversion.plugins.tcr_output import TCROutput
from ebook_convert.ebooks.conversion.plugins.txt_input import TXTInput
from ebook_convert.ebooks.conversion.plugins.txt_output import TXTOutput, TXTZOutput

plugins += [
    AZW4Input,
    DOCXInput,
    EPUBInput,
    FB2Input,
    HTMLInput,
    HTMLZInput,
    LRFInput,
    MOBIInput,
    ODTInput,
    PDBInput,
    PDFInput,
    PMLInput,
    RBInput,
    RTFInput,
    SNBInput,
    TCRInput,
    TXTInput,
]
plugins += [
    AZW3Output,
    DOCXOutput,
    EPUBOutput,
    FB2Output,
    HTMLOutput,
    HTMLZOutput,
    LRFOutput,
    MOBIOutput,
    OEBOutput,
    PDBOutput,
    PMLOutput,
    RBOutput,
    RTFOutput,
    SNBOutput,
    TCROutput,
    TXTOutput,
    TXTZOutput,
]
# }}}

# Profiles {{{
from ebook_convert.customize.profiles import input_profiles, output_profiles

plugins += input_profiles + output_profiles
# }}}
