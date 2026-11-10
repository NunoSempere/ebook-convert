from io import BytesIO

from PIL import Image as PILImage
import pytest

from ebook_convert.utils import img as uimg


def png_bytes(size=(300, 200), mode='RGB', color=(200, 30, 30)):
    buf = BytesIO()
    PILImage.new(mode, size, color).save(buf, 'PNG')
    return buf.getvalue()


def jpeg_bytes(size=(300, 200)):
    buf = BytesIO()
    PILImage.new('RGB', size, (30, 30, 200)).save(buf, 'JPEG')
    return buf.getvalue()


def test_image_from_data_and_format():
    img, fmt = uimg.image_and_format_from_data(jpeg_bytes())
    assert fmt == 'jpeg'
    assert (img.width(), img.height()) == (300, 200)
    assert not img.hasAlphaChannel()
    with pytest.raises(uimg.NotImage):
        uimg.image_from_data(b'definitely not an image')


def test_scale_image_keeps_aspect_ratio():
    w, h, data = uimg.scale_image(jpeg_bytes((600, 800)), width=180,
                                  height=240)
    assert (w, h) == (180, 240)
    assert PILImage.open(BytesIO(data)).format == 'JPEG'
    w, h, data = uimg.scale_image(jpeg_bytes((800, 600)), width=180,
                                  height=240, as_png=True)
    assert (w, h) == (180, 135)
    assert PILImage.open(BytesIO(data)).format == 'PNG'


def test_image_to_data_formats_and_alpha_blend():
    rgba = png_bytes(mode='RGBA', color=(0, 0, 0, 0))  # fully transparent
    img = uimg.image_from_data(rgba)
    assert img.hasAlphaChannel()
    jpeg = uimg.image_to_data(img, fmt='JPEG')
    out = PILImage.open(BytesIO(jpeg))
    assert out.format == 'JPEG' and out.mode == 'RGB'
    assert out.getpixel((10, 10)) == (255, 255, 255)  # blended onto white
    gif = uimg.image_to_data(img, fmt='GIF')
    assert PILImage.open(BytesIO(gif)).format == 'GIF'
    png = uimg.image_to_data(img, fmt='png')
    assert PILImage.open(BytesIO(png)).format == 'PNG'


def test_save_cover_data_to_returns_jpeg_and_minifies(tmp_path):
    big = png_bytes((4000, 5000))
    data = uimg.save_cover_data_to(big, minify_to=(1000, 1000))
    out = PILImage.open(BytesIO(data))
    assert out.format == 'JPEG'
    assert out.size == (800, 1000)
    # Unchanged input is returned as-is
    small = jpeg_bytes((100, 100))
    assert uimg.save_cover_data_to(small, minify_to=(1000, 1000)) == small
    # Writing to a path picks the format from the extension
    path = tmp_path / 'cover.png'
    uimg.save_cover_data_to(small, str(path))
    assert PILImage.open(path).format == 'PNG'


def test_save_cover_grayscale_and_letterbox():
    data = uimg.save_cover_data_to(jpeg_bytes((300, 200)), grayscale=True)
    assert uimg.image_from_data(data).allGray()
    data = uimg.save_cover_data_to(jpeg_bytes((300, 200)),
                                   minify_to=(400, 400), letterbox=True)
    out = PILImage.open(BytesIO(data))
    assert out.size == (400, 400)
    assert out.getpixel((1, 1)) == (0, 0, 0)  # black letterbox bars


def test_canvas_compose_and_flip():
    with uimg.Canvas(20, 10, '#ffffff') as canvas:
        canvas.compose(png_bytes((10, 10), color=(255, 0, 0)), 10, 0)
        out = PILImage.open(BytesIO(canvas.export()))
    assert out.size == (20, 10)
    assert out.getpixel((2, 5))[0] > 240 and out.getpixel((2, 5))[2] > 240
    assert out.getpixel((15, 5))[1] < 20
    flipped = uimg.flip_image(out, horizontal=True)
    assert flipped.pil.getpixel((2, 5))[1] < 20


def test_resize_to_fit_and_crop():
    resized, img = uimg.resize_to_fit(jpeg_bytes((600, 300)), 300, 300)
    assert resized and img.size() == (300, 150)
    resized, img = uimg.resize_to_fit(jpeg_bytes((100, 100)), 300, 300)
    assert not resized
    assert uimg.crop_image(jpeg_bytes((100, 100)), 90, 90, 50, 50).size() == (10, 10)


def test_transforms_do_not_crash():
    data = jpeg_bytes((50, 40))
    for fn in (uimg.grayscale_image, uimg.despeckle_image,
               uimg.gaussian_blur_image, uimg.gaussian_sharpen_image,
               uimg.oil_paint_image, uimg.normalize_image,
               uimg.quantize_image, uimg.eink_dither_image,
               uimg.remove_borders_from_image):
        assert fn(data).size() == (50, 40), fn.__name__
    assert uimg.rotate_image(data, 90).size() == (40, 50)
    assert uimg.add_borders_to_image(data, 1, 2, 3, 4).size() == (54, 46)
    assert not uimg.image_has_transparent_pixels(data)
    assert uimg.image_has_transparent_pixels(
        png_bytes(mode='RGBA', color=(0, 0, 0, 10)))


def test_remove_borders():
    pil = PILImage.new('RGB', (100, 100), (255, 255, 255))
    pil.paste((0, 0, 0), (20, 30, 60, 70))
    assert uimg.remove_borders_from_image(pil).size() == (40, 40)


def test_gif_png_roundtrip():
    gif = uimg.png_data_to_gif_data(png_bytes(mode='RGBA', color=(1, 2, 3, 255)))
    assert PILImage.open(BytesIO(gif)).format == 'GIF'
    png = uimg.gif_data_to_png_data(gif)
    assert PILImage.open(BytesIO(png)).format == 'PNG'


def test_optimizers_report_missing_tools(tmp_path):
    path = tmp_path / 'x.png'
    path.write_bytes(png_bytes())
    ret = uimg.optimize_png(str(path))
    assert ret is None or isinstance(ret, str)
    assert path.read_bytes()[:4] == b'\x89PNG'
