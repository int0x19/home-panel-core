PYTHON ?= .venv/bin/python

.PHONY: build test
build:
	"$(PYTHON)" -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .

test:
	"$(PYTHON)" -m unittest discover -s tests -v
