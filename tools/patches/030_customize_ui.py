"""customize/ui.py: the device driver and metadata source base classes are not
vendored; replace them with placeholder classes so the isinstance() checks in
the plugin registry keep working (no plugin is ever an instance of them)."""

TARGET = 'customize/ui.py'

REPLACEMENTS = [
    (
        'from ebook_convert.devices.interface import DevicePlugin\n',
        '',
    ),
    (
        'from ebook_convert.ebooks.metadata.sources.base import Source\n',
        '',
    ),
    (
        "#: A plugin instance or class, or the name of a plugin\n",
        '''

class DevicePlugin:  # ebook-convert: device drivers are not included
    pass


class Source:  # ebook-convert: metadata download sources are not included
    pass


#: A plugin instance or class, or the name of a plugin
''',
    ),
]
