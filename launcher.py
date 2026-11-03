"""Thin entry point for PyInstaller; `python -m slideshow_maker` is the same thing."""

import sys

from slideshow_maker.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
