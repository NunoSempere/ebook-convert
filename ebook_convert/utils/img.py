"""
Image utilities, implemented on Pillow.

Calibre does all of this with Qt (QImage & friends).  This project has no Qt,
so the same API is provided on top of Pillow.  Image objects handed out by
this module are :class:`Image` wrappers which expose the handful of Qt-style
methods the rest of the code base relies on (``width()``, ``height()``,
``scaled()``, ``hasAlphaChannel()``, ...) while holding a ``PIL.Image`` in
``.pil``.
"""
import errno
import math
import os
import shutil
import subprocess
import tempfile
from io import BytesIO
from threading import Thread

from PIL import Image as PILImage
from PIL import ImageChops, ImageFilter, ImageOps

from ebook_convert.ptempfile import TemporaryDirectory
from ebook_convert.utils.config_base import tweaks
from ebook_convert.utils import encoding as uenc
from ebook_convert.utils.filenames import atomic_rename
from ebook_convert.utils.imghdr import what


# Utilities {{{

def fit_image(width, height, pwidth, pheight):
    """
    Fit image in box of width pwidth and height pheight.
    @param width: Width of image
    @param height: Height of image
    @param pwidth: Width of box
    @param pheight: Height of box
    @return: scaled, new_width, new_height. scaled is True iff new_width
             and/or new_height is different from width or height.
    """
    scaled = height > pheight or width > pwidth
    if height > pheight:
        corrf = pheight / float(height)
        width, height = math.floor(corrf*width), pheight
    if width > pwidth:
        corrf = pwidth / float(width)
        width, height = pwidth, math.floor(corrf*height)
    if height > pheight:
        corrf = pheight / float(height)
        width, height = math.floor(corrf*width), pheight

    return scaled, int(width), int(height)


class NotImage(ValueError):
    pass


def normalize_format_name(fmt):
    fmt = fmt.lower()
    if fmt == 'jpg':
        fmt = 'jpeg'
    return fmt


def get_exe_path(name):
    """External helper tools (optipng, jpegtran, cjpeg, JxrDecApp) are looked
    up on ``$PATH``."""
    return name


def _color(spec):
    """Turn ``'#rrggbb'``/``'white'`` into an RGB tuple."""
    from PIL import ImageColor
    if isinstance(spec, tuple):
        return spec
    return ImageColor.getrgb(spec)


def _has_alpha(pil):
    return (pil.mode in ('RGBA', 'LA', 'PA', 'RGBa', 'La') or
            (pil.mode == 'P' and 'transparency' in pil.info))


def _is_gray(pil):
    if pil.mode in ('L', 'LA', '1', 'I'):
        return True
    rgb = pil.convert('RGB')
    r, g, b = rgb.split()
    return (ImageChops.difference(r, g).getbbox() is None and
            ImageChops.difference(r, b).getbbox() is None)


class Image(object):
    """A Pillow image with the bits of the QImage API this code base uses."""

    def __init__(self, pil=None):
        self.pil = pil

    # -- QImage-like interface ------------------------------------------
    def isNull(self):
        return self.pil is None

    def width(self):
        return 0 if self.pil is None else self.pil.width

    def height(self):
        return 0 if self.pil is None else self.pil.height

    def size(self):
        return (self.width(), self.height())

    def hasAlphaChannel(self):
        return self.pil is not None and _has_alpha(self.pil)

    def allGray(self):
        return self.pil is not None and _is_gray(self.pil)

    def scaled(self, width, height, *args, **kwargs):
        """Resize to exactly ``width`` x ``height`` (aspect ratio flags are
        handled by the callers through :func:`fit_image`)."""
        width, height = max(1, int(width)), max(1, int(height))
        if (width, height) == self.pil.size:
            return self
        return Image(self.pil.resize((width, height), PILImage.LANCZOS))

    def copy(self, x=0, y=0, width=None, height=None):
        if width is None and height is None:
            return Image(self.pil.copy())
        return Image(self.pil.crop((x, y, x + width, y + height)))

    def mirrored(self, horizontal=False, vertical=False):
        pil = self.pil
        if horizontal:
            pil = ImageOps.mirror(pil)
        if vertical:
            pil = ImageOps.flip(pil)
        return Image(pil)

    def save(self, fp, fmt=None, **kw):
        fp.write(image_to_data(self, fmt=fmt or 'PNG', **kw))
        return True

    def __repr__(self):
        return '<Image %sx%s %s>' % (self.width(), self.height(),
                                     getattr(self.pil, 'mode', None))


def load_jxr_data(data):
    with TemporaryDirectory() as tdir:
        with open(os.path.join(tdir, 'input.jxr'), 'wb') as f:
            f.write(data)
        cmd = [get_exe_path('JxrDecApp'), '-i', 'input.jxr', '-o',
               'output.tif']
        subprocess.Popen(cmd, cwd=tdir, stdout=open(os.devnull, 'wb'),
                         stderr=subprocess.STDOUT).wait()
        try:
            return image_from_path(os.path.join(tdir, 'output.tif'))
        except (OSError, NotImage):
            raise NotImage('Failed to convert JPEG-XR image')

# }}}

# png <-> gif {{{


def png_data_to_gif_data(data):
    img = PILImage.open(BytesIO(data))
    buf = BytesIO()
    if img.mode in ('p', 'P'):
        transparency = img.info.get('transparency')
        if transparency is not None:
            img.save(buf, 'gif', transparency=transparency)
        else:
            img.save(buf, 'gif')
    elif img.mode in ('rgba', 'RGBA'):
        alpha = img.split()[3]
        mask = PILImage.eval(alpha, lambda a: 255 if a <= 128 else 0)
        img = img.convert('RGB').convert('P', palette=PILImage.ADAPTIVE,
                                         colors=255)
        img.paste(255, mask)
        img.save(buf, 'gif', transparency=255)
    else:
        img = img.convert('P', palette=PILImage.ADAPTIVE)
        img.save(buf, 'gif')
    return buf.getvalue()


class AnimatedGIF(ValueError):
    pass


def gif_data_to_png_data(data, discard_animation=False):
    img = PILImage.open(BytesIO(data))
    if getattr(img, 'is_animated', False) and not discard_animation:
        raise AnimatedGIF()
    buf = BytesIO()
    img.save(buf, 'png')
    return buf.getvalue()

# }}}

# Loading images {{{


def null_image():
    ' Create an invalid image. For internal use. '
    return Image()


def image_from_data(data):
    ' Create an image object from data, which should be a bytestring. '
    if isinstance(data, Image):
        return data
    if isinstance(data, PILImage.Image):
        return Image(data)
    try:
        pil = PILImage.open(BytesIO(data))
        pil.load()
    except Exception:
        q = what(None, data)
        if q == 'jxr':
            return load_jxr_data(data)
        raise NotImage('Not a valid image (detected type: {})'.format(q))
    return Image(pil)


def image_from_path(path):
    ' Load an image from the specified path. '
    with open(path, 'rb') as f:
        return image_from_data(f.read())


def image_from_x(x):
    ' Create an image from a bytestring or a path or a file like object. '
    if isinstance(x, str):
        return image_from_path(x)
    if hasattr(x, 'read'):
        return image_from_data(x.read())
    if isinstance(x, (bytes, Image, PILImage.Image)):
        return image_from_data(x)
    if isinstance(x, bytearray):
        return image_from_data(bytes(x))
    raise TypeError('Unknown image src type: %s' % type(x))


def image_and_format_from_data(data):
    ''' Create an image object from the specified data which should be a
    bytestring and also return the format of the image (lower case, e.g.
    ``'jpeg'``). '''
    img = image_from_data(data)
    fmt = (img.pil.format or what(None, data) or '').lower()
    return img, normalize_format_name(fmt)
# }}}

# Saving images {{{


def _prepare_for_save(pil, fmt, bgcolor='#ffffff'):
    """Convert ``pil`` into a mode the target format can store."""
    if fmt == 'JPEG':
        if _has_alpha(pil):
            pil = blend_image(Image(pil), bgcolor).pil
        if pil.mode not in ('RGB', 'L', 'CMYK'):
            pil = pil.convert('RGB')
    elif fmt == 'PNG':
        if pil.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P', '1', 'I'):
            pil = pil.convert('RGBA' if _has_alpha(pil) else 'RGB')
    elif fmt == 'BMP':
        if pil.mode not in ('RGB', 'L', 'P', '1'):
            pil = pil.convert('RGB')
    elif fmt in ('PPM', 'PGM'):
        pil = pil.convert('L' if fmt == 'PGM' else 'RGB')
    return pil


def image_to_data(img, compression_quality=95, fmt='JPEG',
                  png_compression_level=9, jpeg_optimized=True,
                  jpeg_progressive=False):
    '''
    Serialize image to bytestring in the specified format.

    :param compression_quality: is for JPEG and goes from 0 to 100. 100 being
        lowest compression, highest image quality
    :param png_compression_level: is for PNG and goes from 0-9. 9 being
        highest compression.
    :param jpeg_optimized: Turns on the 'optimize' option for libjpeg which
        losslessly reduce file size
    :param jpeg_progressive: Turns on the 'progressive scan' option for
        libjpeg which allows JPEG images to be downloaded in streaming fashion
    '''
    img = image_from_data(img)
    if img.isNull():
        raise ValueError('Cannot serialize a null image')
    fmt = fmt.upper()
    if fmt == 'JPG':
        fmt = 'JPEG'
    if fmt == 'GIF':
        return png_data_to_gif_data(image_to_data(img, fmt='PNG'))
    pil = _prepare_for_save(img.pil, fmt)
    kw = {}
    if fmt == 'JPEG':
        kw.update(quality=max(1, min(100, int(compression_quality))),
                  optimize=bool(jpeg_optimized),
                  progressive=bool(jpeg_progressive))
    elif fmt == 'PNG':
        kw['compress_level'] = min(9, max(0, int(png_compression_level)))
    buf = BytesIO()
    try:
        pil.save(buf, fmt, **kw)
    except (KeyError, ValueError, OSError) as err:
        raise ValueError('Failed to export image as %s with error: %s' %
                         (fmt, err))
    return buf.getvalue()


def save_image(img, path, **kw):
    ''' Save image to the specified path. Image format is taken from the file
    extension. You can pass the same keyword arguments as for the
    `image_to_data()` function. '''
    fmt = path.rpartition('.')[-1]
    kw['fmt'] = kw.get('fmt', fmt)
    with open(path, 'wb') as f:
        f.write(image_to_data(image_from_data(img), **kw))


def save_cover_data_to(
    data, path=None,
    bgcolor='#ffffff',
    resize_to=None,
    compression_quality=90,
    minify_to=None,
    grayscale=False,
    eink=False, letterbox=False,
    data_fmt='jpeg'
):
    '''
    Saves image in data to path, in the format specified by the path
    extension. Removes any transparency. If there is no transparency and no
    resize and the input and output image formats are the same, no changes are
    made.

    :param data: Image data as bytestring
    :param path: If None img data is returned, in JPEG format
    :param data_fmt: The fmt to return data in when path is None. Defaults to JPEG
    :param compression_quality: The quality of the image after compression.
        Number between 1 and 100. 1 means highest compression, 100 means no
        compression (lossless). When generating PNG this number is divided by 10
        for the png_compression_level.
    :param bgcolor: The color for transparent pixels. Must be specified in hex.
    :param resize_to: A tuple (width, height) or None for no resizing
    :param minify_to: A tuple (width, height) to specify maximum target size.
        The image will be resized to fit into this target size. If None the
        value from the tweak is used.
    :param grayscale: If True, the image is converted to grayscale,
        if that's not already the case.
    :param eink: If True, the image is dithered down to the 16 specific shades
        of gray of the eInk palette.
        Works best with formats that actually support color indexing (i.e., PNG)
    :param letterbox: If True, in addition to fit resize_to inside minify_to,
        the image will be letterboxed (i.e., centered on a black background).
    '''
    fmt = normalize_format_name(
        data_fmt if path is None else os.path.splitext(path)[1][1:])
    if isinstance(data, (Image, PILImage.Image)):
        img = image_from_data(data)
        changed = True
    else:
        img, orig_fmt = image_and_format_from_data(data)
        changed = fmt != orig_fmt

    if resize_to is not None:
        changed = True
        img = img.scaled(resize_to[0], resize_to[1])
    owidth, oheight = img.width(), img.height()
    nwidth, nheight = (tweaks['maximum_cover_size'] if minify_to is None
                       else minify_to)
    if letterbox:
        img = blend_on_canvas(img, nwidth, nheight, bgcolor='#000000')
        # Check if we were minified
        if oheight != nheight or owidth != nwidth:
            changed = True
    else:
        scaled, nwidth, nheight = fit_image(owidth, oheight, nwidth, nheight)
        if scaled:
            changed = True
            img = img.scaled(nwidth, nheight)
    if img.hasAlphaChannel():
        changed = True
        img = blend_image(img, bgcolor)
    if grayscale and not eink:
        if not img.allGray():
            changed = True
            img = grayscale_image(img)
    if eink:
        img = eink_dither_image(img)
        changed = True
    if changed:
        out = image_to_data(img, compression_quality, fmt,
                            compression_quality // 10)
    else:
        out = data
    if path is None:
        return out
    with open(path, 'wb') as f:
        f.write(out)
# }}}

# Overlaying images {{{


def blend_on_canvas(img, width, height, bgcolor='#ffffff'):
    ' Blend the `img` onto a canvas with the specified background color and size '
    img = image_from_data(img)
    w, h = img.width(), img.height()
    scaled, nw, nh = fit_image(w, h, width, height)
    if scaled:
        img = img.scaled(nw, nh)
        w, h = nw, nh
    canvas = create_canvas(width, height, bgcolor)
    overlay_image(img, canvas, (width - w)//2, (height - h)//2)
    return canvas


class Canvas(object):

    def __init__(self, width, height, bgcolor='#ffffff'):
        self.img = create_canvas(width, height, bgcolor)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def compose(self, img, x=0, y=0):
        img = image_from_data(img)
        overlay_image(img, self.img, x, y)

    def export(self, fmt='JPEG', compression_quality=95):
        return image_to_data(self.img, compression_quality=compression_quality,
                             fmt=fmt)


def create_canvas(width, height, bgcolor='#ffffff'):
    'Create a blank canvas of the specified size and color '
    return Image(PILImage.new('RGB', (max(1, int(width)), max(1, int(height))),
                              _color(bgcolor)))


def overlay_image(img, canvas=None, left=0, top=0):
    ' Overlay the `img` onto the canvas at the specified position (in place) '
    img = image_from_data(img)
    if canvas is None:
        canvas = create_canvas(img.width(), img.height(), '#ffffff')
    left, top = int(left), int(top)
    src = img.pil
    if _has_alpha(src):
        src = src.convert('RGBA')
        canvas.pil.paste(src, (left, top), src)
    else:
        canvas.pil.paste(src.convert(canvas.pil.mode), (left, top))
    return canvas


def texture_image(canvas, texture):
    ' Repeatedly tile the image `texture` across and down the image `canvas` '
    canvas = image_from_data(canvas)
    texture = image_from_data(texture)
    if canvas.hasAlphaChannel():
        canvas = blend_image(canvas)
    out = canvas.pil.copy()
    tw, th = texture.pil.size
    tex = texture.pil.convert('RGBA')
    for y in range(0, out.height, th):
        for x in range(0, out.width, tw):
            out.paste(tex, (x, y), tex)
    return Image(out)


def blend_image(img, bgcolor='#ffffff'):
    ''' Used to convert images that have semi-transparent pixels to opaque by
    blending with the specified color '''
    img = image_from_data(img)
    canvas = create_canvas(img.width(), img.height(), bgcolor)
    overlay_image(img, canvas)
    return canvas
# }}}

# Image borders {{{


def add_borders_to_image(img, left=0, top=0, right=0, bottom=0,
                         border_color='#ffffff'):
    img = image_from_data(img)
    if not (left > 0 or right > 0 or top > 0 or bottom > 0):
        return img
    canvas = create_canvas(img.width() + left + right,
                           img.height() + top + bottom, border_color)
    overlay_image(img, canvas, left, top)
    return canvas


def remove_borders_from_image(img, fuzz=None):
    ''' Try to auto-detect and remove any borders from the image. Returns
    the image itself if no borders could be removed. `fuzz` is a measure of
    what colors are considered identical (must be a number between 0 and 255 in
    absolute intensity units). Default is from a tweak whose default value is 10. '''
    fuzz = tweaks['cover_trim_fuzz_value'] if fuzz is None else fuzz
    img = image_from_data(img)
    pil = img.pil.convert('RGB')
    bbox = None
    for corner in ((0, 0), (pil.width - 1, pil.height - 1)):
        bg = PILImage.new('RGB', pil.size, pil.getpixel(corner))
        diff = ImageChops.difference(pil, bg).convert('L')
        diff = diff.point(lambda v: 255 if v > max(0, fuzz) else 0)
        box = diff.getbbox()
        if box is None:
            continue
        bbox = box if bbox is None else (
            min(bbox[0], box[0]), min(bbox[1], box[1]),
            max(bbox[2], box[2]), max(bbox[3], box[3]))
    if bbox is None or bbox == (0, 0, pil.width, pil.height):
        return img
    return Image(img.pil.crop(bbox))
# }}}

# Cropping/scaling of images {{{


def resize_image(img, width, height):
    return image_from_data(img).scaled(int(width), int(height))


def resize_to_fit(img, width, height):
    img = image_from_data(img)
    resize_needed, nw, nh = fit_image(img.width(), img.height(), width,
                                      height)
    if resize_needed:
        img = resize_image(img, nw, nh)
    return resize_needed, img


def clone_image(img):
    ''' Returns a copy of the image. '''
    return image_from_data(img).copy()


def scale_image(data, width=60, height=80, compression_quality=70,
                as_png=False, preserve_aspect_ratio=True):
    ''' Scale an image, returning it as either JPEG or PNG data (bytestring).
    Transparency is alpha blended with white when converting to JPEG. '''
    img = image_from_data(data)
    if preserve_aspect_ratio:
        scaled, nwidth, nheight = fit_image(img.width(), img.height(), width,
                                            height)
        if scaled:
            img = img.scaled(nwidth, nheight)
    else:
        if img.width() != width or img.height() != height:
            img = img.scaled(width, height)
    fmt = 'PNG' if as_png else 'JPEG'
    w, h = img.width(), img.height()
    return w, h, image_to_data(img, compression_quality=compression_quality,
                               fmt=fmt)


def crop_image(img, x, y, width, height):
    '''
    Return the specified section of the image.

    :param x, y: The top left corner of the crop box
    :param width, height: The width and height of the crop box. Note that if
    the crop box exceeds the source images dimensions, width and height will be
    auto-truncated.
    '''
    img = image_from_data(img)
    width = min(width, img.width() - x)
    height = min(height, img.height() - y)
    return img.copy(x, y, width, height)

# }}}

# Image transformations {{{


def grayscale_image(img):
    img = image_from_data(img)
    mode = 'LA' if img.hasAlphaChannel() else 'L'
    return Image(img.pil.convert(mode))


def set_image_opacity(img, alpha=0.5):
    ''' Change the opacity of `img`. Note that the alpha value is multiplied to
    any existing alpha values, so you cannot use this function to convert a
    semi-transparent image to an opaque one. For that use `blend_image()`. '''
    pil = image_from_data(img).pil.convert('RGBA')
    a = pil.getchannel('A').point(lambda v: int(v * alpha))
    pil.putalpha(a)
    return Image(pil)


def flip_image(img, horizontal=False, vertical=False):
    return image_from_data(img).mirrored(horizontal, vertical)


def image_has_transparent_pixels(img):
    ' Return True iff the image has at least one semi-transparent pixel '
    img = image_from_data(img)
    if img.isNull() or not img.hasAlphaChannel():
        return False
    extrema = img.pil.convert('RGBA').getchannel('A').getextrema()
    return extrema[0] < 255


def rotate_image(img, degrees):
    pil = image_from_data(img).pil
    return Image(pil.rotate(-degrees, expand=True,
                            resample=PILImage.BICUBIC))


def gaussian_sharpen_image(img, radius=0, sigma=3, high_quality=True):
    pil = image_from_data(img).pil
    return Image(pil.filter(ImageFilter.UnsharpMask(radius=max(sigma, 0.1))))


def gaussian_blur_image(img, radius=-1, sigma=3):
    pil = image_from_data(img).pil
    return Image(pil.filter(ImageFilter.GaussianBlur(max(sigma, 0.1))))


def despeckle_image(img):
    pil = image_from_data(img).pil
    return Image(pil.filter(ImageFilter.MedianFilter(3)))


def oil_paint_image(img, radius=-1, high_quality=True):
    pil = image_from_data(img).pil
    size = 3 if radius is None or radius < 1 else int(radius) * 2 + 1
    return Image(pil.filter(ImageFilter.ModeFilter(size)))


def normalize_image(img):
    pil = image_from_data(img).pil
    return Image(ImageOps.autocontrast(pil))


def quantize_image(img, max_colors=256, dither=True, palette=''):
    ''' Quantize the image to contain a maximum of `max_colors` colors. By
    default a palette is chosen automatically, if you want to use a fixed
    palette, then pass in a list of color names in the `palette` variable. If
    you, specify a palette `max_colors` is ignored. Note that it is possible
    for the actual number of colors used to be less than max_colors.

    :param max_colors: Max. number of colors in the auto-generated palette. Must be between 2 and 256.
    :param dither: Whether to use dithering or not. dithering is almost always a good thing.
    :param palette: Use a manually specified palette instead. For example: palette='red green blue #eee'
    '''
    img = image_from_data(img)
    if img.hasAlphaChannel():
        img = blend_image(img)
    pil = img.pil.convert('RGB')
    dither_mode = PILImage.Dither.FLOYDSTEINBERG if dither else PILImage.Dither.NONE
    if palette and isinstance(palette, (str, bytes)):
        palette = palette.split()
    if palette:
        colors = [_color(c) for c in palette]
        pal = PILImage.new('P', (1, 1))
        flat = [v for c in colors for v in c]
        flat += [0] * (768 - len(flat))
        pal.putpalette(flat)
        return Image(pil.quantize(palette=pal, dither=dither_mode))
    return Image(pil.quantize(colors=max(2, min(256, int(max_colors))),
                              dither=dither_mode))


def eink_dither_image(img):
    ''' Dither the source image down to the eInk palette of 16 shades of grey.

    NOTE: No need to call grayscale_image first, as this will inline a
    grayscaling pass if need be.
    '''
    img = image_from_data(img)
    if img.hasAlphaChannel():
        img = blend_image(img)
    gray = img.pil.convert('L')
    pal = PILImage.new('P', (1, 1))
    levels = [int(round(i * 255 / 15.)) for i in range(16)]
    flat = [v for lvl in levels for v in (lvl, lvl, lvl)]
    flat += [0] * (768 - len(flat))
    pal.putpalette(flat)
    return Image(gray.convert('RGB').quantize(
        palette=pal, dither=PILImage.Dither.FLOYDSTEINBERG).convert('L'))

# }}}

# Optimization of images {{{


def run_optimizer(file_path, cmd, as_filter=False, input_data=None):
    exe = shutil.which(cmd[0])
    if exe is None:
        return '%s is not installed' % cmd[0]
    file_path = os.path.abspath(file_path)
    cwd = os.path.dirname(file_path)
    ext = os.path.splitext(file_path)[1]
    if not ext or len(ext) > 10 or not ext.startswith('.'):
        ext = '.jpg'
    fd, outfile = tempfile.mkstemp(dir=cwd, suffix=ext)
    try:
        if as_filter:
            outf = os.fdopen(fd, 'wb')
        else:
            os.close(fd)
        iname, oname = os.path.basename(file_path), os.path.basename(outfile)

        def repl(q, r):
            cmd[cmd.index(q)] = r
        if not as_filter:
            repl(True, iname), repl(False, oname)

        stdin = subprocess.PIPE if as_filter else None
        stderr = subprocess.PIPE if as_filter else subprocess.STDOUT
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                             stderr=stderr, stdin=stdin)
        stderr = p.stderr if as_filter else p.stdout
        if as_filter:
            src = input_data or open(file_path, 'rb')

            def copy(src, dest):
                try:
                    shutil.copyfileobj(src, dest)
                finally:
                    src.close(), dest.close()
            inw = Thread(name='CopyInput', target=copy, args=(src, p.stdin))
            inw.daemon = True
            inw.start()
            outw = Thread(name='CopyOutput', target=copy,
                          args=(p.stdout, outf))
            outw.daemon = True
            outw.start()
        raw = uenc.force_unicode(stderr.read())
        if p.wait() != 0:
            return raw
        else:
            if as_filter:
                outw.join(60.0), inw.join(60.0)
            try:
                sz = os.path.getsize(outfile)
            except EnvironmentError:
                sz = 0
            if sz < 1:
                return '%s returned a zero size image' % cmd[0]
            shutil.copystat(file_path, outfile)
            atomic_rename(outfile, file_path)
    finally:
        try:
            os.remove(outfile)
        except EnvironmentError as err:
            if err.errno != errno.ENOENT:
                raise
        try:
            os.remove(outfile + '.bak')  # optipng creates these files
        except EnvironmentError as err:
            if err.errno != errno.ENOENT:
                raise


def optimize_jpeg(file_path):
    ''' Losslessly optimize a JPEG file in place with jpegtran, if it is
    installed. Returns None on success, otherwise an error message. '''
    exe = get_exe_path('jpegtran')
    cmd = [exe] + '-copy none -optimize -progressive -maxmemory 100M -outfile'.split() + [False, True]
    return run_optimizer(file_path, cmd)


def optimize_png(file_path, level=7):
    ''' Optimize a PNG file in place with optipng, if it is installed. level
    goes from 1 to 7 with 7 being maximum compression. Returns None on
    success, otherwise an error message. '''
    exe = get_exe_path('optipng')
    cmd = [exe] + '-fix -clobber -strip all -o{} -out'.format(level).split() + [False, True]
    return run_optimizer(file_path, cmd)


def encode_jpeg(file_path, quality=80):
    ''' Re-encode an image file as an optimized progressive JPEG in place
    with cjpeg, if it is installed. '''
    quality = max(0, min(100, int(quality)))
    exe = get_exe_path('cjpeg')
    cmd = [exe] + '-optimize -progressive -maxmemory 100M -quality'.split() + [str(quality)]
    img = image_from_path(file_path)
    ppm = image_to_data(img, fmt='PPM')
    return run_optimizer(file_path, cmd, as_filter=True,
                         input_data=BytesIO(ppm))
# }}}
