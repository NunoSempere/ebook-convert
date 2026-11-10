"""
Read meta information from epub files (Calibre ebooks/metadata/epub.py,
without the LocalZipFile recovery path and the Qt based cover renderer).
"""
import io
import os
import posixpath
from contextlib import closing

from ebook_convert.ebooks.metadata.opf import get_metadata as get_metadata_from_opf
from ebook_convert.ebooks.metadata.opf import set_metadata as set_metadata_opf
from ebook_convert.ebooks.metadata.opf2 import OPF
from ebook_convert.ptempfile import TemporaryDirectory
from ebook_convert.utils.directory import CurrentDir
from ebook_convert.utils.imghdr import what as what_image_type
from ebook_convert.utils.xml_parse import safe_xml_fromstring
from ebook_convert.utils.zipfile import BadZipfile, ZipFile, safe_replace


class EPubException(Exception):
    pass


class OCFException(EPubException):
    pass


class ContainerException(OCFException):
    pass


class Container(dict):

    def __init__(self, stream=None, file_exists=None):
        if not stream:
            return
        container = safe_xml_fromstring(stream.read())
        if container.get('version', None) != '1.0':
            raise EPubException('unsupported version of OCF')
        rootfiles = container.xpath('./*[local-name()="rootfiles"]')
        if not rootfiles:
            raise EPubException('<rootfiles/> element missing')
        for rootfile in rootfiles[0].xpath('./*[local-name()="rootfile"]'):
            mt, fp = rootfile.get('media-type'), rootfile.get('full-path')
            if not mt or not fp:
                raise EPubException('<rootfile/> element malformed')

            if file_exists and not file_exists(fp):
                # Some Kobo epubs have multiple rootfile entries, but only one
                # exists.  Ignore the ones that don't exist.
                continue
            if mt not in self:
                self[mt] = fp


class OCF(object):
    MIMETYPE = 'application/epub+zip'
    CONTAINER_PATH = 'META-INF/container.xml'
    ENCRYPTION_PATH = 'META-INF/encryption.xml'

    def __init__(self):
        raise NotImplementedError('Abstract base class')


class Encryption(object):

    OBFUSCATION_ALGORITHMS = frozenset(['http://ns.adobe.com/pdf/enc#RC',
                                        'http://www.idpf.org/2008/embedding'])

    def __init__(self, raw):
        self.root = safe_xml_fromstring(raw) if raw else None
        self.entries = {}
        if self.root is not None:
            for em in self.root.xpath('descendant::*[contains(name(), "EncryptionMethod")]'):
                algorithm = em.get('Algorithm', '')
                cr = em.getparent().xpath('descendant::*[contains(name(), "CipherReference")]')
                if cr:
                    uri = cr[0].get('URI', '')
                    if uri and algorithm:
                        self.entries[uri] = algorithm

    def is_encrypted(self, uri):
        algo = self.entries.get(uri, None)
        return algo is not None and algo not in self.OBFUSCATION_ALGORITHMS


class OCFReader(OCF):

    def open(self, name):
        raise NotImplementedError()

    def __init__(self):
        try:
            mimetype = self.read_bytes('mimetype').decode('utf-8').rstrip()
            if mimetype != OCF.MIMETYPE:
                print('WARNING: Invalid mimetype declaration', mimetype)
        except Exception:
            print("WARNING: Epub doesn't contain a valid mimetype declaration")

        try:
            with closing(self.open(OCF.CONTAINER_PATH)) as f:
                self.container = Container(f, self.exists)
        except KeyError:
            raise EPubException('missing OCF container.xml file')
        opf_path = self.container.get(OPF.MIMETYPE)
        if not opf_path:
            raise EPubException('missing OPF package file entry in container')
        self.opf_path = opf_path
        self._opf_cached = None
        self._encryption_meta_cached = None

    @property
    def opf(self):
        if self._opf_cached is None:
            try:
                with closing(self.open(self.opf_path)) as f:
                    self._opf_cached = OPF(f, self.root, populate_spine=False)
            except KeyError:
                raise EPubException('missing OPF package file')
        return self._opf_cached

    @property
    def encryption_meta(self):
        if self._encryption_meta_cached is None:
            try:
                self._encryption_meta_cached = Encryption(self.read_bytes(self.ENCRYPTION_PATH))
            except Exception:
                self._encryption_meta_cached = Encryption(None)
        return self._encryption_meta_cached

    def read_bytes(self, name):
        return self.open(name).read()

    def exists(self, path):
        try:
            self.open(path).close()
            return True
        except OSError:
            return False


class OCFZipReader(OCFReader):

    def __init__(self, stream, mode='r', root=None):
        if isinstance(stream, ZipFile):
            self.archive = stream
        else:
            try:
                self.archive = ZipFile(stream, mode=mode)
            except BadZipfile:
                raise EPubException('not a ZIP .epub OCF container')
        if root is not None:
            self.root = root
        else:
            name = getattr(stream, 'name', None)
            if isinstance(name, str) and name:
                self.root = os.path.abspath(os.path.dirname(name))
            else:
                self.root = os.getcwd()
        super().__init__()

    def open(self, name):
        return io.BytesIO(self.archive.read(name))

    def read_bytes(self, name):
        return self.archive.read(name)

    def exists(self, path):
        try:
            self.archive.getinfo(path)
            return True
        except KeyError:
            return False


def get_zip_reader(stream, root=None):
    try:
        zf = ZipFile(stream, mode='r')
    except BadZipfile:
        raise EPubException('not a ZIP .epub OCF container')
    return OCFZipReader(zf, root=root)


class OCFDirReader(OCFReader):

    def __init__(self, path):
        self.root = path
        super().__init__()

    def open(self, name):
        return open(os.path.join(self.root, name), 'rb')

    def read_bytes(self, name):
        with self.open(name) as f:
            return f.read()


def render_cover(cpage, zf, reader=None):
    """Extract the cover image referenced by the HTML cover page ``cpage``.
    Only simple cover pages (a lone <img> or <svg><image/></svg>) are
    understood, there is no HTML renderer in this fork."""
    from ebook_convert.ebooks import render_html_svg_workaround
    from ebook_convert.logging import default_log

    if not cpage:
        return
    if reader is not None and reader.encryption_meta.is_encrypted(cpage):
        return

    with TemporaryDirectory('_epub_meta') as tdir:
        with CurrentDir(tdir):
            zf.extractall()
            cpage = os.path.join(tdir, cpage)
            if not os.path.exists(cpage):
                return

            try:
                # In the case of manga, the first spine item may be an image
                # already, so treat it as a raster cover.
                file_format = what_image_type(cpage)
                if file_format == 'jpeg':
                    # Only JPEG is allowed since elsewhere we assume raster
                    # covers are JPEG.
                    with open(cpage, 'rb') as source:
                        return source.read()
            except Exception:
                pass

            return render_html_svg_workaround(cpage, default_log, root=tdir)


epub_allow_rendered_cover = True


def get_cover(raster_cover, first_spine_item, reader):
    zf = reader.archive

    if raster_cover:
        if reader.encryption_meta.is_encrypted(raster_cover):
            return
        try:
            return reader.read_bytes(raster_cover)
        except Exception:
            pass

    if epub_allow_rendered_cover:
        return render_cover(first_spine_item, zf, reader=reader)


def get_metadata(stream, extract_cover=True, ftype='epub'):
    """ Return metadata as a :class:`Metadata` object """
    stream.seek(0)
    reader = get_zip_reader(stream)
    opfbytes = reader.read_bytes(reader.opf_path)
    mi, ver, raster_cover, first_spine_item = get_metadata_from_opf(opfbytes, ftype)
    if extract_cover:
        base = posixpath.dirname(reader.opf_path)
        if raster_cover:
            raster_cover = posixpath.normpath(posixpath.join(base, raster_cover))
        if first_spine_item:
            first_spine_item = posixpath.normpath(posixpath.join(base, first_spine_item))
        try:
            cdata = get_cover(raster_cover, first_spine_item, reader)
            if cdata is not None:
                mi.cover_data = ('jpg', cdata)
        except Exception:
            import traceback
            traceback.print_exc()
    mi.timestamp = None
    return mi


def get_quick_metadata(stream, ftype='epub'):
    return get_metadata(stream, False)


def serialize_cover_data(new_cdata, cpath):
    from ebook_convert.utils.img import save_cover_data_to
    return save_cover_data_to(new_cdata, data_fmt=os.path.splitext(cpath)[1][1:])


def set_metadata(stream, mi, apply_null=False, update_timestamp=False,
                 force_identifiers=False, add_missing_cover=True, ftype='epub'):
    stream.seek(0)
    reader = get_zip_reader(stream, root=os.getcwd())
    new_cdata = None
    try:
        new_cdata = mi.cover_data[1]
        if not new_cdata:
            raise Exception('no cover')
    except Exception:
        try:
            with open(mi.cover, 'rb') as f:
                new_cdata = f.read()
        except Exception:
            pass

    opfbytes, ver, raster_cover = set_metadata_opf(
        reader.read_bytes(reader.opf_path), mi,
        cover_prefix=posixpath.dirname(reader.opf_path),
        cover_data=new_cdata, apply_null=apply_null,
        update_timestamp=update_timestamp,
        force_identifiers=force_identifiers,
        add_missing_cover=add_missing_cover, ftype=ftype)
    cpath = None
    replacements = {}
    if new_cdata and raster_cover:
        try:
            cpath = posixpath.join(posixpath.dirname(reader.opf_path), raster_cover)
            cover_replacable = (not reader.encryption_meta.is_encrypted(cpath) and
                                os.path.splitext(cpath)[1].lower() in ('.png', '.jpg', '.jpeg'))
            if cover_replacable:
                replacements[cpath] = serialize_cover_data(new_cdata, cpath)
        except Exception:
            import traceback
            traceback.print_exc()

    safe_replace(stream, reader.container[OPF.MIMETYPE], opfbytes,
                 extra_replacements=replacements, add_missing=True)
