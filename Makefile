.PHONY: build test clean

PLUGIN_NAME = BlogRatingSync.zip

build:
	cd plugin && zip -r ../$(PLUGIN_NAME) . -x '__pycache__/*' '*.pyc'

test:
	uv run pytest

clean:
	rm -f $(PLUGIN_NAME)
