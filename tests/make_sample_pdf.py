"""Generate tests/fixtures/sample.pdf, a small text PDF written by hand.

The fixture exercises the PDF input engines: every page has the running
header "My Book Title", a bare page number as footer and body text set in
Helvetica, with paragraphs that straddle page breaks. The PDF also carries an
outline (bookmarks) and an Info dictionary. No dates or random data go in, so
the output is byte for byte reproducible::

    python -m tests.make_sample_pdf          # rewrite tests/fixtures/sample.pdf
"""
import pathlib
import textwrap

FIXTURE = pathlib.Path(__file__).parent / 'fixtures' / 'sample.pdf'

HEADER = 'My Book Title'
TITLE = 'Sample Book'
AUTHOR = 'Test Author'

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
LEFT = 72
FONT_SIZE = 11
LEADING = 14
HEADER_Y = 752
BODY_TOP_Y = 700
FOOTER_Y = 40
LINES_PER_PAGE = 10
WRAP_WIDTH = 78

# Original prose, one string per paragraph. The chapter headings are the
# outline targets. Keep the text free of parentheses and backslashes, which
# would need escaping in PDF strings.
PARAGRAPHS = [
    'Chapter One',
    'The lighthouse keeper had counted the ships for forty years, and in all '
    'that time he had never once seen the same vessel twice. Each morning he '
    'wrote the names in a ledger bound in green cloth, and each evening he '
    'read the names back to himself as other men might read a prayer. The '
    'ledger was nearly full now, and he wondered whether he should order '
    'another or whether the sea would simply stop sending ships when the last '
    'page was written.',
    'His daughter visited on Sundays, bringing bread and the week of '
    'newspapers that the village had already finished with. She would sit on '
    'the stone step while he climbed to polish the great lens, and she would '
    'call up to him the headlines she thought he would like, which were '
    'mostly about weather and never about war. When the lamp flickered and '
    'the shadows crept along the wall of the tower, she knew it was time to '
    'walk back along the cliff path before the dark caught her.',
    'There was a story in the village that the keeper could name a ship from '
    'the sound of its engine alone, and that he had once turned a trawler '
    'away from the rocks by shouting its name into the fog. He denied it when '
    'asked, but he denied it in the manner of a man who would rather the '
    'story be told than forgotten, and so the children went on telling it.',
    'Chapter Two',
    'The winter that the ledger ran out was the coldest anyone could '
    'remember. Ice formed on the inside of the lantern room and the keeper '
    'spent his nights scraping it from the glass with the edge of a brass '
    'rule. The ships came anyway, fewer of them and slower, their lights '
    'smeared by the frost into long yellow streaks that he followed with his '
    'eyes until they vanished past the headland and left him alone again with '
    'the sound of the wind.',
    'On the last night of the year a steamer passed so close that he could '
    'hear the men singing on her deck, and he stood with his pen above the '
    'final empty line and could not bring himself to write. He told his '
    'daughter afterwards that he had not caught the name, but she had seen '
    'the lights too and she knew that the keeper did not miss names. She '
    'bought him a new ledger in the spring, bound in blue this time, and he '
    'filled the first page before the week was out.',
    'Chapter Three',
    'The new ledger outlasted him, as he had known it would. When the '
    'lighthouse was finally automated the engineers found both books on the '
    'shelf beside the clockwork, the green one full and the blue one not, and '
    'they sent them to the daughter with a polite letter that she kept folded '
    'inside the back cover. On quiet evenings she still reads the names '
    'aloud, slowly, in the order he wrote them down, so that for a little '
    'while the ships are counted once again.',
]


def pdf_string(text):
    "A PDF literal string, the text being plain ASCII"
    text.encode('ascii')
    for ch in '()\\':
        if ch in text:
            raise ValueError('%r needs escaping in a PDF string' % ch)
    return '(' + text + ')'


def layout_pages():
    """Wrap the paragraphs into lines and split them into pages.

    Returns ``(pages, chapters)``: pages is a list of lists of lines, with
    ``None`` for the blank line between paragraphs, and chapters a list of
    ``(heading, page_index)`` pairs for the outline.
    """
    pages, current, chapters = [], [], []
    for para in PARAGRAPHS:
        if current:
            current.append(None)
        if para.startswith('Chapter '):
            chapters.append((para, len(pages)))
        for line in textwrap.wrap(para, WRAP_WIDTH):
            current.append(line)
            if len(current) == LINES_PER_PAGE:
                pages.append(current)
                current = []
    if current:
        pages.append(current)
    return pages, chapters


def page_content(number, lines):
    "The content stream of one page"
    parts = ['BT', '/F1 %d Tf' % FONT_SIZE, '%d %d Td' % (LEFT, HEADER_Y),
             pdf_string(HEADER) + ' Tj', 'ET',
             'BT', '/F1 %d Tf' % FONT_SIZE, '%d TL' % LEADING,
             '%d %d Td' % (LEFT, BODY_TOP_Y)]
    for line in lines:
        if line is None:
            parts.append('T*')
        else:
            parts.append(pdf_string(line) + ' Tj T*')
    parts += ['ET', 'BT', '/F1 %d Tf' % FONT_SIZE,
              '%d %d Td' % (PAGE_WIDTH // 2, FOOTER_Y),
              pdf_string(str(number)) + ' Tj', 'ET']
    return '\n'.join(parts).encode('ascii')


def build_pdf():
    "The bytes of the sample PDF"
    pages, chapters = layout_pages()
    n_pages = len(pages)

    # Object numbers: 1 catalog, 2 pages, 3 font, 4 info, then a page and its
    # content stream per page, then the outline root and its items
    first_page_obj = 5
    page_objs = [first_page_obj + 2 * i for i in range(n_pages)]
    outlines_obj = first_page_obj + 2 * n_pages
    item_objs = [outlines_obj + 1 + i for i in range(len(chapters))]

    objects = {}  # number -> body bytes, without "n 0 obj" / "endobj"
    objects[1] = ('<< /Type /Catalog /Pages 2 0 R /Outlines %d 0 R '
                  '/PageMode /UseOutlines >>' % outlines_obj).encode()
    objects[2] = ('<< /Type /Pages /Kids [%s] /Count %d >>' % (
        ' '.join('%d 0 R' % o for o in page_objs), n_pages)).encode()
    objects[3] = (b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica '
                  b'/Encoding /WinAnsiEncoding >>')
    objects[4] = ('<< /Title %s /Author %s /Producer (tests/make_sample_pdf.py) >>'
                  % (pdf_string(TITLE), pdf_string(AUTHOR))).encode()
    for i, (page_obj, page_lines) in enumerate(zip(page_objs, pages)):
        content = page_content(i + 1, page_lines)
        objects[page_obj] = (
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] '
            '/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>'
            % (PAGE_WIDTH, PAGE_HEIGHT, page_obj + 1)).encode()
        objects[page_obj + 1] = (b'<< /Length %d >>\nstream\n' % len(content)
                                 + content + b'\nendstream')
    objects[outlines_obj] = ('<< /Type /Outlines /First %d 0 R /Last %d 0 R '
                             '/Count %d >>' % (item_objs[0], item_objs[-1],
                                               len(item_objs))).encode()
    for i, (obj, (title, page_idx)) in enumerate(zip(item_objs, chapters)):
        parts = ['/Title %s' % pdf_string(title),
                 '/Parent %d 0 R' % outlines_obj,
                 '/Dest [%d 0 R /XYZ null null null]' % page_objs[page_idx]]
        if i > 0:
            parts.append('/Prev %d 0 R' % item_objs[i - 1])
        if i + 1 < len(item_objs):
            parts.append('/Next %d 0 R' % item_objs[i + 1])
        objects[obj] = ('<< %s >>' % ' '.join(parts)).encode()

    out = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += b'%d 0 obj\n' % num + objects[num] + b'\nendobj\n'
    size = max(objects) + 1
    xref = len(out)
    out += b'xref\n0 %d\n' % size
    out += b'0000000000 65535 f \n'
    for num in range(1, size):
        out += b'%010d 00000 n \n' % offsets[num]
    out += (b'trailer\n<< /Size %d /Root 1 0 R /Info 4 0 R >>\n'
            b'startxref\n%d\n%%%%EOF\n' % (size, xref))
    return bytes(out)


def main():
    FIXTURE.write_bytes(build_pdf())
    print('wrote', FIXTURE)


if __name__ == '__main__':
    main()
