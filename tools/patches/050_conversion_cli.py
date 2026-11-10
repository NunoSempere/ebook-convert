"""ebooks/conversion/cli.py: recipes (news download) need calibre.web, which
is not vendored, so the --list-recipes option is dropped.  Also point the
usage text at this project."""

TARGET = 'ebooks/conversion/cli.py'

REPLACEMENTS = [
    (
        """    if '--list-recipes' in args:
        from ebook_convert.web.feeds.recipes.collection import get_builtin_recipe_titles

        log('Available recipes:')
        titles = sorted(get_builtin_recipe_titles())
        for title in titles:
            try:
                log('\\t' + title)
            except Exception:
                log('\\t' + repr(title))
        log(f'{len(titles)} recipes available')
        raise SystemExit(0)
""",
        "",
    ),
    (
        """    parser = OptionParser(usage=USAGE)
    parser.add_option(
        '--list-recipes',
        default=False,
        action='store_true',
        help=_('List builtin recipe names. You can create an e-book from a builtin recipe like this: ebook-convert "Recipe Name.recipe" output.epub'),
    )
    return parser
""",
        """    parser = OptionParser(usage=USAGE)
    return parser
""",
    ),
    (
        "    + localize_user_manual_link('https://manual.calibre-ebook.com/conversion.html')\n",
        "    + 'https://manual.calibre-ebook.com/conversion.html'\n"
        "    + '\\n\\nThis is ebook-convert, the Calibre conversion pipeline packaged as a standalone,\\n'\n"
        "    'Qt-free command (https://github.com/NunoSempere/ebook-convert).'\n",
    ),
]

# Log to stderr so that stdout stays free for the caller (calibre logs to
# stdout); the conversion log is diagnostics, not output.
REPLACEMENTS.append(
    (
        """    log = Log()
    parser, plumber = create_option_parser(args, log)
""",
        """    log = Log()
    from ebook_convert.utils.logging import ANSIStream

    log.outputs = [ANSIStream(sys.stderr)]  # ebook-convert: diagnostics go to stderr
    parser, plumber = create_option_parser(args, log)
""",
    )
)
