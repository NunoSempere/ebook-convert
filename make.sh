#!/bin/bash
# Development helper. Usage: ./make.sh <target>
#
#   install   create .venv with uv and install the project in editable mode
#   test      run the test-suite
#   build     build sdist + wheel into dist/
#   binary    build a single-file executable into dist/ with PyInstaller
#   publish   upload dist/* to PyPI (needs UV_PUBLISH_TOKEN or trusted publishing)
#   clean     remove build artefacts
set -euo pipefail

install() {
	uv sync --all-extras
	echo "Done. Run with: uv run ebook-convert in.epub out.mobi"
}

test() {
	uv run --all-extras pytest "$@"
}

build() {
	rm -rf dist
	uv build
	# Same check PyPI applies to the README on upload.
	uvx twine check --strict dist/*
}

binary() {
	uv run pyinstaller --noconfirm --clean packaging/ebook-convert.spec
	echo "Binary written to dist/ebook-convert"
}

publish() {
	# Expects UV_PUBLISH_TOKEN (a PyPI API token) in the environment, or run
	# from the GitHub release workflow which uses trusted publishing.
	uv publish "$@"
}

clean() {
	rm -rf build dist ./*.egg-info .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
}

"${1:-install}" "${@:2}"
