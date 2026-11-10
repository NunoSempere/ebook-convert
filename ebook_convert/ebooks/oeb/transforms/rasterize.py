# License: GPLv3 Copyright: 2008, Marshall T. Vandegrift <llasram@gmail.com>

"""
SVG rasterization transform.

Calibre renders SVG with Qt (QSvgRenderer).  ebook-convert renders with resvg
through the ``resvg_py`` wheel instead; the transform itself (what gets
rasterized, how it is wired into the manifest, ``svg_originals`` for the DOCX
writer) follows calibre/ebooks/oeb/transforms/rasterize.py.
"""

from __future__ import annotations

import os
import re
from base64 import standard_b64encode
from functools import lru_cache
from urllib.parse import urldefrag

from lxml import etree

from ebook_convert import guess_type
from ebook_convert.ebooks.oeb.base import PNG_MIME, SVG_MIME, XHTML, XLINK, urlnormalize, xml2str, xpath
from ebook_convert.ebooks.oeb.stylizer import Stylizer
from ebook_convert.utils.imghdr import what

IMAGE_TAGS = {XHTML('img'), XHTML('object')}
KEEP_ATTRS = {'class', 'style', 'width', 'height', 'align'}


class Unavailable(Exception):
    pass


def renderer_available() -> bool:
    """Return True if the resvg renderer can be imported."""
    try:
        import resvg_py  # ruff: ignore[unused-import]
    except ImportError:
        return False
    return True


def _length(value):
    """Parse an SVG length attribute (``"120"``, ``"120px"``, ``"2in"``) into
    CSS pixels; return None for percentages or garbage."""
    if value is None:
        return None
    m = re.match(r'^\s*([0-9.]+)\s*([a-z%]*)\s*$', value, re.I)
    if m is None:
        return None
    try:
        num = float(m.group(1))
    except ValueError:
        return None
    unit = m.group(2).lower()
    factor = {'': 1, 'px': 1, 'pt': 96 / 72.0, 'pc': 16, 'in': 96, 'cm': 96 / 2.54, 'mm': 96 / 25.4, 'em': 16, 'ex': 8}.get(unit)
    if factor is None:
        return None
    return num * factor


def svg_intrinsic_size(root, logger=None):
    """Return the (width, height) an SVG root element declares, in pixels.

    Uses the width/height attributes, then the viewBox, then falls back to
    100x100 like Qt's QSvgRenderer does.
    """
    width = _length(root.get('width'))
    height = _length(root.get('height'))
    view_box = root.get('viewBox', root.get('viewbox'))
    box = None
    if view_box is not None:
        try:
            box = [float(x) for x in filter(None, re.split('[, ]+', view_box))]
            if len(box) != 4 or box[2] <= 0 or box[3] <= 0:
                raise ValueError(view_box)
        except (TypeError, ValueError):
            box = None
            if logger is not None:
                logger.warn(f'SVG image has invalid viewBox="{view_box}", ignoring the viewBox')
    if width and height:
        return width, height
    if box is not None:
        bw, bh = box[2], box[3]
        if width:
            return width, width * bh / bw
        if height:
            return height * bw / bh, height
        return bw, bh
    return 100.0, 100.0


def fit_size(size, width=0, height=0):
    """Scale ``size`` to fit inside ``width`` x ``height`` keeping the aspect
    ratio (both bounds optional), returning integer pixel dimensions."""
    w, h = size
    if width and height:
        scale = min(width / w, height / h)
    elif width:
        scale = width / w
    elif height:
        scale = height / h
    else:
        scale = 1.0
    return max(1, int(round(w * scale))), max(1, int(round(h * scale)))


def render_svg(svg_bytes, width=0, height=0, size=None, bgcolor='#ffffff'):
    """Render SVG markup to PNG bytes of the given size using resvg.

    ``size`` is the intrinsic size to scale from; when omitted it is read
    from the markup.
    """
    import resvg_py

    if size is None:
        from ebook_convert.utils.xml_parse import safe_xml_fromstring

        size = svg_intrinsic_size(safe_xml_fromstring(svg_bytes))
    w, h = fit_size(size, width, height)
    if isinstance(svg_bytes, bytes):
        svg_bytes = svg_bytes.decode('utf-8', 'replace')
    png = resvg_py.svg_to_bytes(svg_string=svg_bytes, width=w, height=h, background=bgcolor)
    return bytes(png)


def rasterize_svg(data, sizes=(), width=0, height=0, print=None, fmt='PNG', as_qimage=False):
    """Module level helper with Calibre's signature: rasterize SVG ``data``
    to ``fmt`` bytes, scaled to fit ``width`` x ``height``."""
    from ebook_convert.utils.xml_parse import safe_xml_fromstring

    root = safe_xml_fromstring(data)
    size = svg_intrinsic_size(root)
    if size == (100.0, 100.0) and sizes:
        size = (float(sizes[0]), float(sizes[1]))
    w, h = fit_size(size, width, height)
    if print is not None:
        print(f'Rasterizing SVG to {w} x {h}')
    png = render_svg(data, w, h, size=size)
    if fmt.upper() != 'PNG':
        from ebook_convert.utils.img import image_to_data

        return image_to_data(png, fmt=fmt)
    return png


@lru_cache(maxsize=128)
def data_url(mime_type: str, data: bytes) -> str:
    return f'data:{mime_type};base64,' + standard_b64encode(data).decode('ascii')


class SVGRasterizer:
    def __init__(self, base_css: str = '', save_svg_originals: bool = False) -> None:
        if not renderer_available():
            raise Unavailable('SVG rasterization needs the resvg_py package; SVG images are left as they are')
        self.base_css = base_css
        self.save_svg_originals = save_svg_originals

    @classmethod
    def config(cls, cfg):
        return cfg

    @classmethod
    def generate(cls, opts):
        return cls()

    def __call__(self, oeb, context) -> None:
        oeb.logger.info('Rasterizing SVG images...')
        self.stylizer_cache = {}
        self.oeb = oeb
        self.opts = context
        self.profile = context.dest
        self.images = {}
        self.svg_originals = {}
        self.scan_for_linked_resources_in_manifest()
        self.rasterize_spine()
        self.rasterize_cover()

    def rasterize_svg(self, elem, width=0, height=0, format='PNG') -> bytes:
        logger = self.oeb.logger
        size = svg_intrinsic_size(elem, logger)
        for image in elem.xpath('descendant::*[local-name()="image" and @height and contains(@height, "%")]'):
            logger.info('Found SVG image height in %, trying to convert...')
            try:
                h = float(image.get('height').replace('%', '')) / 100.0
                image.set('height', str(h * size[1]))
            except Exception:
                logger.exception('Failed to convert percentage height:', image.get('height'))
        w, h = fit_size(size, width, height)
        logger.info(f'Rasterizing SVG to {w} x {h}')
        data = render_svg(xml2str(elem, with_tail=False), w, h, size=size)
        if format.upper() != 'PNG':
            from ebook_convert.utils.img import image_to_data

            data = image_to_data(data, fmt=format)
        return data

    def scan_for_linked_resources_in_manifest(self) -> None:
        for item in self.oeb.manifest.values():
            if item.media_type == SVG_MIME and item.data is not None:
                self.scan_for_linked_resources_in_svg(item)

    def scan_for_linked_resources_in_svg(self, item, svg=None):
        if svg is None:
            svg = item.data
        hrefs = self.oeb.manifest.hrefs
        ha = XLINK('href')
        for elem in xpath(svg, '//svg:*[@xl:href]'):
            href = urlnormalize(elem.attrib[ha])
            path = urldefrag(href)[0]
            if not path:
                continue
            abshref = item.abshref(path)
            linkee = hrefs.get(abshref)
            if linkee is None:
                continue
            data = linkee.bytes_representation
            ext = what(None, data)
            if not ext:
                continue
            mt = guess_type('file.' + ext)[0]
            if not mt or not mt.startswith('image/'):
                continue
            elem.set(ha, data_url(mt, data))
        return svg

    def stylizer(self, item):
        ans = self.stylizer_cache.get(item, None)
        if ans is None:
            ans = self.stylizer_cache[item] = Stylizer(item.data, item.href, self.oeb, self.opts, self.profile, base_css=self.base_css)
        return ans

    def rasterize_spine(self) -> None:
        for item in self.oeb.spine:
            self.rasterize_item(item)

    def rasterize_item(self, item) -> None:
        html = item.data
        hrefs = self.oeb.manifest.hrefs
        for elem in xpath(html, '//h:img[@src]'):
            src = urlnormalize(elem.attrib['src'])
            image = hrefs.get(item.abshref(src), None)
            if image and image.media_type == SVG_MIME:
                style = self.stylizer(item).style(elem)
                self.rasterize_external(elem, style, item, image)
        for elem in xpath(html, f'//h:object[@type="{SVG_MIME}" and @data]'):
            data = urlnormalize(elem.attrib['data'])
            image = hrefs.get(item.abshref(data), None)
            if image and image.media_type == SVG_MIME:
                style = self.stylizer(item).style(elem)
                self.rasterize_external(elem, style, item, image)
        for elem in xpath(html, '//svg:svg'):
            style = self.stylizer(item).style(elem)
            self.rasterize_inline(elem, style, item)

    def rasterize_inline(self, elem, style, item) -> None:
        width = style.width
        height = style.height
        width = (width / 72) * self.profile.dpi
        height = (height / 72) * self.profile.dpi
        self.scan_for_linked_resources_in_svg(item, elem)
        data = self.rasterize_svg(elem, width, height)
        manifest = self.oeb.manifest
        href = os.path.splitext(item.href)[0] + '.png'
        id, href = manifest.generate(item.id, href)
        manifest.add(id, href, PNG_MIME, data=data)
        img = elem.makeelement(XHTML('img'), src=item.relhref(href))
        if self.save_svg_originals:
            svg_bytes = etree.tostring(elem, encoding='utf-8', xml_declaration=True, pretty_print=True, with_tail=False)
            svg_id, svg_href = manifest.generate(item.id, 'inline.svg')
            manifest.add(svg_id, svg_href, SVG_MIME, data=svg_bytes)
            self.svg_originals[href] = svg_href
        img.tail = elem.tail
        elem.getparent().replace(elem, img)
        for prop in ('width', 'height'):
            if prop in elem.attrib:
                img.attrib[prop] = elem.attrib[prop]

    def rasterize_external(self, elem, style, item, svgitem) -> None:
        width = style.width
        height = style.height
        width = (width / 72) * self.profile.dpi
        height = (height / 72) * self.profile.dpi
        svg = self.scan_for_linked_resources_in_svg(svgitem)
        size = svg_intrinsic_size(svg, self.oeb.logger)
        w, h = fit_size(size, width, height)
        key = (svgitem.href, w, h)
        if key in self.images:
            href = self.images[key]
        else:
            logger = self.oeb.logger
            logger.info(f'Rasterizing {svgitem.href!r} to {w}x{h}')
            data = render_svg(xml2str(svg), w, h, size=size)
            manifest = self.oeb.manifest
            href = os.path.splitext(svgitem.href)[0] + '.png'
            id, href = manifest.generate(svgitem.id, href)
            manifest.add(id, href, PNG_MIME, data=data)
            self.images[key] = href
        self.svg_originals[href] = svgitem.href
        elem.tag = XHTML('img')
        for attr in list(elem.attrib):
            if attr not in KEEP_ATTRS:
                del elem.attrib[attr]
        elem.attrib['src'] = item.relhref(href)
        if elem.text:
            elem.attrib['alt'] = elem.text
            elem.text = None
        for child in list(elem):
            elem.remove(child)

    def rasterize_cover(self) -> None:
        covers = self.oeb.metadata.cover
        if not covers:
            return
        if str(covers[0]) not in self.oeb.manifest.ids:
            self.oeb.logger.warn('Cover not in manifest, skipping.')
            self.oeb.metadata.clear('cover')
            return
        cover = self.oeb.manifest.ids[str(covers[0])]
        if cover.media_type != SVG_MIME:
            return
        width = (self.profile.width / 72) * self.profile.dpi
        height = (self.profile.height / 72) * self.profile.dpi
        data = self.rasterize_svg(cover.data, width, height)
        href = os.path.splitext(cover.href)[0] + '.png'
        id, href = self.oeb.manifest.generate(cover.id, href)
        self.oeb.manifest.add(id, href, PNG_MIME, data=data)
        covers[0].value = id
