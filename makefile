#!/bin/bash

install:
	sudo apt install libxml2-dev libxslt-dev
	uv venv
	source .venv/bin/activate
	uv pip install .
	# python3 -m venv venv
	# . venv/bin/activate
	# pip3 install .
