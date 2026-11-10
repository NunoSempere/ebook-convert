"""ebooks/lrf/html/convert_from.py reads one constant off the device driver
base class (calibre.devices, not vendored); inline it."""

TARGET = 'ebooks/lrf/html/convert_from.py'

REPLACEMENTS = [
    (
        'from ebook_convert.devices.interface import DevicePlugin as Device\n',
        '''

class Device:  # ebook-convert: from calibre.devices.interface.DevicePlugin
    THUMBNAIL_HEIGHT = 68

''',
    ),
]
