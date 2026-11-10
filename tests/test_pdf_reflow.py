"""Unit tests for the calibre PDF reflow engine and its bidi helpers.

Ported from Calibre's src/calibre/ebooks/pdf/reflow_test.py and bidi_test.py
(37e1e608e3, cc6a3ba2a0). The pages are built from synthetic pdftohtml XML, so
nothing here needs poppler. The cases that need ICU to reorder right-to-left
text are left out: this fork has no ICU and leaves such text in the visual
order pdftohtml produces, which the fallback tests at the end check.
"""
import random

import pytest

from ebook_convert.ebooks.pdf import bidi
from ebook_convert.ebooks.pdf.bidi import (
    OBJECT_REPLACEMENT, fix_markup_line, fix_pdftohtml_html, flatten, has_rtl,
    is_predominantly_rtl, markup_to_text, parse_markup, rebuild, reorder_runs,
    visual_to_logical)
from ebook_convert.ebooks.pdf.reflow import Image, Page, PDFDocument
from ebook_convert.logging import default_log
from ebook_convert.utils.xml_parse import safe_xml_fromstring


class Opts:
    pdf_header_skip = 0
    pdf_footer_skip = 0
    pdf_header_regex = ''
    pdf_footer_regex = ''
    no_images = True
    verbose = 0
    unwrap_factor = 0.4


def build(fragments, width=600, height=800, join=True):
    """Build a Page from (left, top, width, text) or (left, top, width, text,
    height) fragments, the way poppler reports them."""
    parts = ['<page number="1" top="0" left="0" height="%d" width="%d">'
             % (height, width)]
    for frag in fragments:
        left, top, w, text = frag[:4]
        h = frag[4] if len(frag) > 4 else 12
        parts.append('<text top="%d" left="%d" width="%d" height="%d">%s</text>'
                     % (top, left, w, h, text))
    parts.append('</page>')
    opts = Opts()
    page = Page(safe_xml_fromstring(''.join(parts)), {}, opts, default_log,
                iter(range(100000)))
    if join:
        page.join_fragments(opts)
    return page


# Columns of prose hold a lineful of text, unlike the cells of a table. The
# fixtures below use realistic line lengths so that the check which tells the
# two apart is actually exercised.
LEFT_LINE = 'the left column of this page holds'
RIGHT_LINE = 'the right column of this page holds'


def two_columns(rows=6, left_text=LEFT_LINE, right_text=RIGHT_LINE):
    "A plain two column page with a gutter between x=210 and x=250"
    ans = []
    for i in range(rows):
        ans.append((10, 10 + i * 20, 200, '%s %d' % (left_text, i)))
        ans.append((250, 10 + i * 20, 200, '%s %d' % (right_text, i)))
    return ans


def texts_of(page):
    return [t.text_as_string for t in page.texts]


# Single column pages {{{

def check_not_split(fragments, width=600):
    page = build(fragments, width=width)
    assert page.column_count == 1
    for t in page.texts:
        assert t.column == (0, 0)
    return page


def test_plain_page():
    page = check_not_split([(10, 10 + i * 20, 400, 'Line %d of ordinary text' % i)
                            for i in range(8)])
    assert len(page.texts) == 8


def test_fragments_are_still_joined_into_lines():
    page = check_not_split([(10, 10, 40, 'The'), (55, 10, 40, 'quick'),
                            (100, 10, 40, 'fox')])
    assert texts_of(page) == ['The quick fox']


def test_empty_page():
    page = build([])
    assert page.column_count == 1
    assert page.texts == []


def test_too_few_rows_to_tell():
    # Two rows is not enough to know a gap is a gutter and not a wide space
    check_not_split([(10, 10, 200, 'Left one'), (330, 10, 200, 'Right one'),
                     (10, 30, 200, 'Left two'), (330, 30, 200, 'Right two')])


def test_justified_text():
    # Justified text has wide gaps between words, but in a different place
    # on every line, so no strip of the page is free of text
    random.seed(7)
    fragments = []
    for i in range(12):
        x = 10
        for word in range(5):
            fragments.append((x, 10 + i * 20, 70, 'w%d' % word))
            x += 70 + random.choice((20, 45, 70, 95))
    check_not_split(fragments, width=700)


def test_block_quote_indent():
    fragments = [(10, 10 + i * 20, 500, 'Ordinary line %d' % i) for i in range(4)]
    fragments += [(120, 90 + i * 20, 380, 'Indented quotation %d' % i) for i in range(4)]
    fragments += [(10, 180 + i * 20, 500, 'More ordinary text %d' % i) for i in range(4)]
    check_not_split(fragments)


def test_centred_title():
    fragments = [(200, 5, 200, 'A Centred Title', 20)]
    fragments += [(10, 40 + i * 20, 550, 'Body line %d' % i) for i in range(8)]
    check_not_split(fragments)


def test_table_of_contents():
    # The page numbers down the right hand side line up, but they are far
    # too little text to be a column of their own
    fragments = [(10, 10 + i * 20, 300, 'Chapter %d Of This Book' % i) for i in range(10)]
    fragments += [(560, 10 + i * 20, 20, '%d' % (i * 7)) for i in range(10)]
    check_not_split(fragments)


def test_ragged_right_margin():
    # The right hand margin is empty but it is a margin, not a gutter, as
    # there is no text to the right of it
    check_not_split([(10, 10 + i * 20, 200 + (i % 3) * 40, 'Line %d' % i)
                     for i in range(10)])

# }}}


# Column detection {{{

def test_two_columns():
    page = build(two_columns())
    assert page.column_count == 2
    assert [t.column for t in page.texts] == [(0, 0)] * 6 + [(0, 1)] * 6


def test_columns_are_read_one_after_the_other():
    page = build(two_columns())
    assert texts_of(page) == (['%s %d' % (LEFT_LINE, i) for i in range(6)]
                              + ['%s %d' % (RIGHT_LINE, i) for i in range(6)])


def test_fragments_are_not_joined_across_a_gutter():
    # This is what used to run the two columns of a line together
    page = build(two_columns())
    assert len(page.texts) == 12
    for text in texts_of(page):
        assert not (LEFT_LINE in text and RIGHT_LINE in text), text


def test_fragments_within_a_column_are_still_joined():
    fragments = []
    for i in range(6):
        fragments.append((10, 10 + i * 20, 90, 'the left column of'))
        fragments.append((105, 10 + i * 20, 90, 'this page holds %d' % i))
        fragments.append((250, 10 + i * 20, 200, '%s %d' % (RIGHT_LINE, i)))
    page = build(fragments)
    assert page.column_count == 2
    assert texts_of(page) == (
        ['the left column of this page holds %d' % i for i in range(6)]
        + ['%s %d' % (RIGHT_LINE, i) for i in range(6)])


def test_three_columns():
    names = ('first', 'second', 'third')
    fragments = []
    for i in range(6):
        for c, x in enumerate((10, 210, 410)):
            fragments.append((x, 10 + i * 20, 180, 'text of the %s column %d' % (names[c], i)))
    page = build(fragments)
    assert page.column_count == 3
    assert texts_of(page) == ['text of the %s column %d' % (n, i)
                              for n in names for i in range(6)]


def test_gutters():
    page = build(two_columns(), join=False)
    gutters = page.find_gutters()
    assert len(gutters) == 1
    start, end = gutters[0]
    assert 210 <= start < end <= 250, gutters[0]


def test_paragraphs_are_not_merged_across_a_gutter():
    # The last line of one column and the first of the next line up
    # vertically in a way that used to look like a paragraph continuing
    page = build(two_columns())
    left_last = [t for t in page.texts if t.column == (0, 0)][-1]
    right_first = [t for t in page.texts if t.column == (0, 1)][0]
    assert left_last.column != right_first.column

# }}}


# Spanning elements {{{

HEADING = 'A Full Width Heading Over The Page'


def heading_over_columns(rows):
    return [(10, 5, 440, HEADING, 20)] + [
        (x, 45 + i * 20, 200, '%s %d' % (name, i)) for i in range(rows)
        for x, name in ((10, LEFT_LINE), (250, RIGHT_LINE))]


def test_heading_over_two_columns():
    page = build(heading_over_columns(6))
    assert page.column_count == 2
    assert texts_of(page)[0] == HEADING
    assert texts_of(page)[1:] == (['%s %d' % (LEFT_LINE, i) for i in range(6)]
                                  + ['%s %d' % (RIGHT_LINE, i) for i in range(6)])


def test_heading_over_a_short_page():
    # Few enough rows that the allowance for rows crossing a gutter rounds
    # down to none, so the heading would otherwise hide the gutter
    page = build(heading_over_columns(4))
    assert page.column_count == 2
    assert texts_of(page)[0] == HEADING


def test_heading_in_the_middle_starts_a_new_band():
    fragments = []
    for i in range(4):
        fragments.append((10, 10 + i * 20, 200, '%s %d' % (LEFT_LINE, i)))
        fragments.append((250, 10 + i * 20, 200, '%s %d' % (RIGHT_LINE, i)))
    fragments.append((10, 100, 440, 'A Mid Page Heading Over The Page', 18))
    for i in range(4, 8):
        fragments.append((10, 50 + i * 20, 200, '%s %d' % (LEFT_LINE, i)))
        fragments.append((250, 50 + i * 20, 200, '%s %d' % (RIGHT_LINE, i)))
    page = build(fragments)
    assert texts_of(page) == (
        ['%s %d' % (LEFT_LINE, i) for i in range(4)]
        + ['%s %d' % (RIGHT_LINE, i) for i in range(4)]
        + ['A Mid Page Heading Over The Page']
        + ['%s %d' % (LEFT_LINE, i) for i in range(4, 8)]
        + ['%s %d' % (RIGHT_LINE, i) for i in range(4, 8)])


def test_a_spanning_element_is_not_joined_to_a_column():
    # The heading sits above the body, it does not overlap the first row
    page = build(heading_over_columns(6))
    assert HEADING in texts_of(page)
    for text in texts_of(page):
        if 'Heading' in text:
            assert text == HEADING

# }}}


# Tables {{{

def table(rows=12):
    ans = []
    for i in range(rows):
        ans.append((10, 10 + i * 20, 80, 'Item %d' % i))
        ans.append((230, 10 + i * 20, 60, '%d' % (i * 11)))
        ans.append((430, 10 + i * 20, 60, '%d' % (i * 37)))
    return ans


def test_a_table_is_not_split_into_columns():
    assert build(table()).column_count == 1


def test_the_rows_of_a_table_stay_together():
    page = build(table())
    assert len(page.texts) == 12
    for i, text in enumerate(texts_of(page)):
        assert 'Item %d' % i in text
        assert str(i * 11) in text
        assert str(i * 37) in text


def test_a_two_column_list_of_short_entries_is_left_alone():
    # Conservative: without a lineful of text on each row there is no way
    # to tell a two column list from a table, so it is not split
    fragments = []
    for i in range(10):
        fragments.append((10, 10 + i * 20, 80, 'Apples %d' % i))
        fragments.append((330, 10 + i * 20, 80, 'Pears %d' % i))
    assert build(fragments).column_count == 1

# }}}


# Page boundaries {{{

BODY = 'Some ordinary text that fills up most of the width of a line'


def convert_pages(pages, tmp_path, monkeypatch):
    """Convert a document whose pages are lists of (left, top, width, text,
    font) fragments, returning the generated HTML."""
    parts = ['<pdf2xml>']
    for num, fragments in enumerate(pages, start=1):
        parts.append('<page number="%d" top="0" left="0" height="1349" width="1800">' % num)
        if num == 1:
            parts.append('<fontspec id="0" size="24" family="Body" color="#000000"/>')
            parts.append('<fontspec id="1" size="31" family="Heading" color="#000000"/>')
            parts.append('<fontspec id="2" size="21" family="Caption" color="#000000"/>')
        for left, top, width, text, font in fragments:
            parts.append('<text top="%d" left="%d" width="%d" height="29" font="%d">%s</text>'
                         % (top, left, width, font, text))
        parts.append('</page>')
    parts.append('</pdf2xml>')
    opts = Opts()
    opts.pdf_header_skip = opts.pdf_footer_skip = -1
    monkeypatch.chdir(tmp_path)
    PDFDocument(''.join(parts).encode('utf-8'), opts, default_log)
    return (tmp_path / 'index.html').read_text(encoding='utf-8')


def text_page(num, heading='', page_number=True):
    # Vary the text so that it is not mistaken for a header or footer
    words = 'alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu'.split()
    ans = [(337, 132, 800, heading, 1)] if heading else []
    ans += [(337, 223 + i * 35, 1100, '%s %s %s.' % (BODY, words[num % len(words)], words[i]), 0)
            for i in range(12)]
    if page_number:
        ans.append((892, 1212, 15 * len(str(num)), str(num), 0))
    return ans


def test_bare_page_numbers_are_removed(tmp_path, monkeypatch):
    html = convert_pages([text_page(i + 2) for i in range(6)], tmp_path, monkeypatch)
    assert '%s gamma alpha.' % BODY in html
    for i in range(6):
        assert '>%d<' % (i + 2) not in html


def test_caption_is_not_merged_with_next_page(tmp_path, monkeypatch):
    # A centred image caption at the bottom of one page followed by a
    # heading at the top of the next must remain separate paragraphs, even
    # though the caption ends with whitespace
    pages = [text_page(i, page_number=False) for i in range(6)]
    pages[2] = [(659, 1045, 480, 'Caption of the image, 2026. ', 2)]
    pages[3] = text_page(3, heading='The heading after the caption', page_number=False)
    paras = [p for p in convert_pages(pages, tmp_path, monkeypatch).splitlines()
             if p.startswith('<p')]
    assert len([p for p in paras if 'Caption of the image' in p]) == 1
    for p in paras:
        if 'Caption of the image' in p:
            assert 'The heading after the caption' not in p


def test_a_paragraph_continues_across_a_page_break(tmp_path, monkeypatch):
    # The last line of a page that ends mid sentence is joined to the first
    # line of the next page
    pages = [text_page(i + 2) for i in range(4)]
    pages[1][-2] = (337, 223 + 11 * 35, 1100, 'this line of the paragraph runs on to the', 0)
    pages[2][0] = (337, 223, 1100, 'next page where it finishes. %s' % pages[2][0][3], 0)
    html = convert_pages(pages, tmp_path, monkeypatch)
    assert 'runs on to the next page where it finishes.' in html


def test_outline_becomes_a_toc(tmp_path, monkeypatch):
    pages = [text_page(i + 2) for i in range(3)]
    parts = ['<pdf2xml>']
    for num, fragments in enumerate(pages, start=1):
        parts.append('<page number="%d" top="0" left="0" height="1349" width="1800">' % num)
        if num == 1:
            parts.append('<fontspec id="0" size="24" family="Body" color="#000000"/>')
        for left, top, width, text, font in fragments:
            parts.append('<text top="%d" left="%d" width="%d" height="29" font="%d">%s</text>'
                         % (top, left, width, font, text))
        parts.append('</page>')
    parts.append('<outline><item page="1">One</item><item page="2">Two</item>'
                 '<item page="3">Three</item></outline></pdf2xml>')
    opts = Opts()
    monkeypatch.chdir(tmp_path)
    PDFDocument(''.join(parts).encode('utf-8'), opts, default_log)
    ncx = (tmp_path / 'toc.ncx').read_text(encoding='utf-8')
    assert 'Two' in ncx and 'index.html#page_2' in ncx

# }}}


# Images {{{

def image_html(width, height, page_width=1800, page_height=1349):
    img = safe_xml_fromstring('<image top="10" left="10" width="%d" height="%d" src="x.jpg"/>'
                              % (width, height))
    return Image(img, page_width, page_height, Opts(), default_log, iter(range(10))).to_html()


def test_image_size_is_not_fixed():
    html = image_html(1313, 984)
    assert 'width=' not in html
    assert 'height' not in html


def test_small_image_keeps_its_size_relative_to_the_page():
    assert 'style="max-width:20%"' in image_html(360, 200)


def test_large_image_can_fill_the_screen():
    # Fills the height of a landscape page but not its width
    assert 'style="max-width:100%"' in image_html(721, 900)
    assert 'style="max-width:100%"' in image_html(1313, 300)

# }}}


# bidi: the parts that do not need ICU {{{

HEBREW = 'שלום עולם'
ARABIC = 'مرحبا بالعالم'
ENGLISH = 'The quick brown fox'
ENGLISH_HEBREW = 'The word שלום here'


def test_has_rtl_detects_rtl_scripts():
    for text in (HEBREW, ARABIC, 'جمله فارسی', 'ܐܠܗܐ ܒܪܐ', 'ދިވެހި', ENGLISH_HEBREW):
        assert has_rtl(text), text
    for text in (ENGLISH, '', '12345', 'Ελληνικά', 'Русский', '日本語'):
        assert not has_rtl(text), text


def test_has_rtl_covers_every_rtl_character():
    import unicodedata
    missed = [cp for cp in range(0x110000)
              if unicodedata.bidirectional(chr(cp)) in ('R', 'AL') and not has_rtl(chr(cp))]
    assert missed == []


def test_is_predominantly_rtl():
    for text in (HEBREW, ARABIC, 'יש כאן (סוגריים) בסוף.', 'שנת 2024 טובה'):
        assert is_predominantly_rtl(text), text
    for text in (ENGLISH, ENGLISH_HEBREW, 'See Genesis (בראשית) chapter 1', '', '2024'):
        assert not is_predominantly_rtl(text), text


def markup_round_trip(raw):
    runs = []
    flatten(parse_markup(raw), (), runs)
    return rebuild(runs)


@pytest.mark.parametrize('raw', [
    'plain text',
    'text <b>bold</b> more',
    '<b>bold <i>and italic</i></b>',
    'a <a href="#x">link</a> b',
    'before <img src="x.png"/> after',
    'page <a id="p1"></a> anchor',
    'a <a href="#x"><img src="x.png"/></a> b',
    'a <b><br/></b> b',
    'a <b><!-- c --></b> b',
    '<span style="font-size:1.2em">big</span>',
    '',
    'a &amp; b', '&lt;tag&gt;', 'x &amp; <b>y &lt; z</b>',
])
def test_markup_round_trip(raw):
    assert markup_round_trip(raw) == raw


def test_text_free_elements_become_objects():
    runs = []
    flatten(parse_markup('a <a id="p1"></a> b'), (), runs)
    assert [t for t, c in runs] == ['a ', OBJECT_REPLACEMENT, ' b']


@pytest.mark.parametrize('raw', [
    'unclosed <b>bold', 'stray </b> close', '<b>overlapping <i>tags</b> here</i>',
    'a < b', '<b><i>deep</b>', 'text <br> more',
])
def test_malformed_markup_loses_no_text(raw):
    assert markup_to_text(markup_round_trip(raw)) == markup_to_text(raw)


def test_markup_to_text():
    assert markup_to_text('<b>bold </b><i>and italic</i>') == 'bold and italic'
    assert markup_to_text('a <img src="x.png"/>b') == 'a b'
    assert markup_to_text('a &amp; b') == 'a & b'
    assert markup_to_text('<a id="p1"></a>') == ''
    assert markup_to_text('a <a href="#x"><img src="x.png"/></a>b') == 'a b'
    assert markup_to_text(OBJECT_REPLACEMENT) == OBJECT_REPLACEMENT


def test_left_to_right_lines_are_untouched():
    for raw in ('plain english text', 'text <b>bold</b> more', 'a <a href="#x">link</a> b',
                'a &amp; b', '', 'a < b > c', 'Ελληνικά 123'):
        assert fix_markup_line(raw) is raw
        assert visual_to_logical(raw) is raw
    doc = '<html><body>first line<br>second line<br></body></html>'
    assert fix_pdftohtml_html(doc) is doc
    for raw in ('', 'שלום', '<html></html>'):
        fix_pdftohtml_html(raw)  # must not raise


def reverse_convert(text, want_map=False):
    """A stand-in for ICU that simply reverses the line, with the index map
    ICU would report. Enough to exercise the markup-aware reordering."""
    n = len(text)
    if want_map:
        return text[::-1], tuple(n - 1 - i for i in range(n))
    return text[::-1]


def test_reorder_runs_keeps_context_with_its_text():
    runs = [('cba', 'a'), (' ', 'b'), ('fed', 'c')]
    assert reorder_runs(runs, reverse_convert) == [('def', 'c'), (' ', 'b'), ('abc', 'a')]
    assert reorder_runs([], reverse_convert) == []
    assert reorder_runs([('םלוע םולש', 'ctx')], reverse_convert) == [('שלום עולם', 'ctx')]


def test_fix_markup_line_with_a_converter():
    assert fix_markup_line('<b>םולש</b> םלוע', reverse_convert) == 'עולם <b>שלום</b>'
    # Link targets at the edges of the line are not moved
    assert fix_markup_line('<a id="p1"></a>םלוע םולש', reverse_convert) == '<a id="p1"></a>שלום עולם'
    # Objects in the middle of the line travel with the reading order
    assert fix_markup_line('ינש <img src="x.png"/> ןושאר', reverse_convert) == 'ראשון <img src="x.png"/> שני'
    assert fix_markup_line('םולש &amp; םלוע', reverse_convert) == 'עולם &amp; שלום'


def test_fix_pdftohtml_html_with_a_converter():
    doc = '<html lang="he"><body><a id="p1"></a>%s<br>%s<br></body></html>' % ('םלוע םולש', 'ןאכ שי')
    ans = fix_pdftohtml_html(doc, reverse_convert)
    assert '<body><a id="p1"></a>שלום עולם<br>יש כאן<br>' in ans
    assert '<html lang="he" dir="rtl">' in ans


def test_rtl_text_is_left_alone_without_a_converter(caplog, monkeypatch):
    monkeypatch.setattr(bidi, '_rtl_notice_shown', False)
    visual = 'םלוע םולש'
    with caplog.at_level('WARNING', logger='ebook-convert'):
        assert fix_markup_line(visual) == visual
        assert visual_to_logical(visual) == visual
        doc = '<html><body>%s<br></body></html>' % visual
        assert fix_pdftohtml_html(doc) == doc
    # The notice is logged once, not per line
    assert len([r for r in caplog.records if 'Right-to-left' in r.getMessage()]) == 1


def test_reflow_page_with_rtl_fragments_keeps_lines_apart():
    # Reflow's own line detection is unaffected by the missing reordering
    page = build([(10, 10, 40, 'םלוע'), (55, 10, 40, 'םולש'), (10, 40, 40, 'רחמ')])
    for t in page.texts:
        t.convert_visual_order_to_logical()
    assert len(page.texts) == 2
    assert page.texts[0].left == 10 and page.texts[0].top == 10
    t = page.texts[0]
    assert markup_to_text(t.raw) == t.text_as_string


def test_a_tall_initial_does_not_merge_lines():
    # A drop cap is much taller than the lines beside it; the lines below
    # it must not be pulled into it
    page = build([(10, 10, 30, 'א'), (50, 10, 60, 'תחא'), (50, 30, 60, 'םייתש'),
                  (50, 50, 60, 'שולש')])
    assert len(page.texts) == 3

# }}}
