#!/usr/bin/env python3
#
# Copyright (C) 2023 by Pedro de Medeiros <pedro.medeiros@gmail.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import os
import sys

from argparse import ArgumentParser
from itertools import combinations
from functools import reduce
from PIL import Image

__version__ = "0.1"

MAX_COLORS = 16
DEF_W = 16
DEF_H = 16
TRANS = (0, 0, 0)

# Enable/disable DEBUG mode
if os.environ.get('DEBUG', False):
    DEBUG = 1
    debug = lambda *x, **y: print(*x, **y, file=sys.stderr)
else:
    DEBUG = 0
    debug = lambda *x, **y: None


def get_palette_from_image(image):
    bytes_ = image.getpalette()
    palette = []

    for start in range(0, 48, 3):
        if bytes_[start:start + 3]:
            palette.append(tuple(bytes_[start:start + 3]))

    return palette


def check_line(spriteno, lineno, colors, max_sprites):
    debug(f'line number:', lineno)
    errors = []
    found = True

    for indexes in combinations(colors, max_sprites + 1):
        found = False
        for operators in combinations(indexes, max_sprites):
            result = (set(indexes) - set(operators)).pop()
            mask = reduce(int.__or__, operators)
            if result == mask:
                debug(f'{operators=}, {result=}, {mask=}, found: {result==mask}')
                found = True
    if not found:
        debug('results: not found')
        errors.append(f'sprite #{spriteno} at line #{lineno} cannot combine colors {colors} with only {max_sprites} sprites')

    return errors


def check_combinations(image, max_sprites, palette):
    """Get number of colours used in OR-colour combinations for the whole image."""
    data = image.getdata()
    w, h = image.size
    all_errors = []
    TRANS_SET = set([palette.index(TRANS)])
    debug('Transparent colour index =', palette.index(TRANS))

    for y in range(0, h, DEF_H):
        for spriteno, x in enumerate(range(0, w, DEF_W), start=1):
            # separate current sprite data
            pattern = [data[x + i + ((y + j) * w)]
                       for j in range(DEF_H) for i in range(DEF_W)]

            for lineno, start in enumerate(range(0, 256, DEF_W), start=1):
                colors = set(pattern[start : start + DEF_W]) - TRANS_SET
                if len(colors):
                    all_errors.extend(check_line(spriteno, lineno, colors, max_sprites))

    return all_errors


def main():
    parser = ArgumentParser(description="Sprite Checker for MSX2 sprites",
                            epilog="""Copyright (C) 2023 Pedro de Medeiros <pedro.medeiros@.gmail.com>"""
                            )

    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument("-c", "--count", dest="max_sprites", default=2, type=int,
                        help="maximum sprites per slot (default: 2)")

    parser.add_argument("image", help="image to examine")

    args = parser.parse_args()

    try:
        image = Image.open(args.image)
    except IOError:
        parser.error("failed to open the image")

    if image.mode != 'P':
        parser.error("not an indexed image (%s detected)" % image.mode)

    palette = get_palette_from_image(image)
    if DEBUG:
        debug('Palette:')
        debug('--------')
        for i, (r, g, b) in enumerate(palette):
            if (r, g, b) == (-1, -1, -1): continue
            debug(f'{i}: {r:02X}{g:02X}{b:02X}')

    if len(palette) > MAX_COLORS:
        parser.error("palette too big (maximum of 16 colors expected, got %i)" % len(palette))

    w, h = image.size

    if w % DEF_W or h % DEF_H:
        parser.error("%s size is not multiple of sprite size (%s, %s)" %
                     (args.image, DEF_W, DEF_H))

    errors = check_combinations(image, args.max_sprites, palette)
    if errors:
        for error in errors:
            print(error)
    else:
        print('no errors detected')


if __name__ == "__main__":
    main()
