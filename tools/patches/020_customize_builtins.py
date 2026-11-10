"""Reduce calibre/customize/builtins.py to the plugins the converter needs.

Keeps the archive, metadata reader/writer and conversion plugin sections and
the input/output profiles; drops AI providers, catalogs, device drivers,
metadata download sources, GUI interface actions, preferences and store
plugins.  The conversion plugin list is replaced by the set verified to work
without Qt or C extensions (see README).
"""

TARGET = 'customize/builtins.py'

INPUT_PLUGINS = [
    'AZW4Input', 'DOCXInput', 'EPUBInput', 'FB2Input', 'HTMLInput', 'HTMLZInput', 'LRFInput', 'MOBIInput',
    'ODTInput', 'PDBInput', 'PDFInput', 'PMLInput', 'RBInput', 'RTFInput', 'SNBInput', 'TCRInput', 'TXTInput',
]
OUTPUT_PLUGINS = [
    'AZW3Output', 'DOCXOutput', 'EPUBOutput', 'FB2Output', 'HTMLOutput', 'HTMLZOutput', 'LRFOutput', 'MOBIOutput',
    'OEBOutput', 'PDBOutput', 'PMLOutput', 'RBOutput', 'RTFOutput', 'SNBOutput', 'TCROutput', 'TXTOutput', 'TXTZOutput',
]
# plugin modules that exist in the vendored tree, keyed by class name
PLUGIN_MODULES = {
    'AZW4Input': 'azw4_input', 'DOCXInput': 'docx_input', 'EPUBInput': 'epub_input', 'FB2Input': 'fb2_input',
    'HTMLInput': 'html_input', 'HTMLZInput': 'htmlz_input', 'LRFInput': 'lrf_input', 'MOBIInput': 'mobi_input',
    'ODTInput': 'odt_input', 'PDBInput': 'pdb_input', 'PDFInput': 'pdf_input', 'PMLInput': 'pml_input',
    'RBInput': 'rb_input', 'RTFInput': 'rtf_input', 'SNBInput': 'snb_input', 'TCRInput': 'tcr_input',
    'TXTInput': 'txt_input',
    'AZW3Output': 'mobi_output', 'DOCXOutput': 'docx_output', 'EPUBOutput': 'epub_output', 'FB2Output': 'fb2_output',
    'HTMLOutput': 'html_output', 'HTMLZOutput': 'htmlz_output', 'LRFOutput': 'lrf_output', 'MOBIOutput': 'mobi_output',
    'OEBOutput': 'oeb_output', 'PDBOutput': 'pdb_output', 'PMLOutput': 'pml_output', 'RBOutput': 'rb_output',
    'RTFOutput': 'rtf_output', 'SNBOutput': 'snb_output', 'TCROutput': 'tcr_output', 'TXTOutput': 'txt_output',
    'TXTZOutput': 'txt_output',
}


def _cut(text, start_marker, end_marker):
    start = text.index(start_marker)
    end = text.index(end_marker, start) + len(end_marker)
    return text[:start], text[end:]


def apply(text):
    # 1. drop the AI provider imports and registration
    lines = []
    for line in text.split('\n'):
        if line.startswith('from ebook_convert.ai.'):
            continue
        if line.startswith('plugins.extend((OpenRouterAI'):
            continue
        lines.append(line)
    text = '\n'.join(lines)

    # 2. replace the conversion plugins section
    head, tail = _cut(text, '# Conversion plugins {{{', '# }}}')
    by_module = {}
    for cls, mod in PLUGIN_MODULES.items():
        by_module.setdefault(mod, []).append(cls)
    section = ['# Conversion plugins {{{', '# ebook-convert: only plugins that run without Qt and Calibre C extensions']
    for mod in sorted(by_module):
        section.append('from ebook_convert.ebooks.conversion.plugins.%s import %s' % (mod, ', '.join(sorted(by_module[mod]))))
    section.append('')
    section.append('plugins += [\n    ' + ',\n    '.join(INPUT_PLUGINS) + ',\n]')
    section.append('plugins += [\n    ' + ',\n    '.join(OUTPUT_PLUGINS) + ',\n]')
    section.append('# }}}')
    text = head + '\n'.join(section) + tail

    # 3. keep only the profiles from everything after the conversion plugins
    start = text.index('# Catalog plugins {{{')
    text = text[:start] + '''# Profiles {{{
from ebook_convert.customize.profiles import input_profiles, output_profiles

plugins += input_profiles + output_profiles
# }}}
'''
    return text
