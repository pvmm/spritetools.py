#!/usr/bin/env python3
#
# Copyright (C) 2019 by Juan J. Martinez <jjm@usebox.net>
# Copyright (C) 2022 by Pedro de Medeiros <pedro.medeiros@gmail.com>
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
import math
import contextlib

from argparse import ArgumentParser
from itertools import permutations
from itertools import combinations
from functools import reduce
from multiprocessing.pool import ThreadPool
from PIL import Image

__version__ = "1.2"

MAX_COLORS = 16
DEF_W = 16
DEF_H = 16
ENDL = '%s%s' % (chr(0x0d), chr(0x0a))
PROCESSES = 10000

IMG_TRANS = (255, 0, 255)
MSX_TRANS = (0, 0, 0)
FAKE_PAL = [(-1, -1, -1)] * MAX_COLORS

# Enable/disable DEBUG mode
if os.environ.get('DEBUG', False):
    DEBUG = 1
    debug = lambda *x, **y: print(*x, **y, file=sys.stderr)
else:
    DEBUG = 0
    debug = lambda *x, **y: None


def to_hex_list_str(src):
    """Writes sprites as C-style hexadecimal data."""
    out = ''
    for i in range(0, len(src), 8):
        out += ', '.join(['0x%02x' % b for b in src[i:i + 8]]) + ',\n'
    return out


def to_hex_list_str_asm(src):
    """Writes sprites as assembly-style hexadecimal data."""
    out = ''
    for i in range(0, len(src), 8):
        out += '\tdb ' + ', '.join(['#0x%02x' % b for b in src[i:i + 8]])
        out += '\n'
    return out


def to_hex_list_str_basic(src):
    """Writes sprites as BASIC-style hexadecimal data."""
    return 'DATA %s%s' % (', '.join(['&H%02X' % b for b in src]), ENDL)


def rgb_list_to_str(lst):
    """Writes output as C-style hexadecimal data."""
    return ', '.join(['(%i, %i, %i)' % (r, g, b) for r, g, b in lst])


def rgb_list_to_hex_str(lst):
    """Writes output as C-style hexadecimal data."""
    return ', '.join(['(%x, %x, %x)' % (r, g, b) for r, g, b in lst])


def lookup_combination(index):
    # OR-colour combinations
    combinations = { 3: (1, 2), 5: (1, 4), 6: (2, 4), 7: (1, 2, 4), 9: (1, 8), 10: (2, 8),
                    11: (1, 2, 8), 13: (1, 4, 8), 14: (2, 4, 8), 15: (1, 2, 4, 8) }
    if index in combinations:
        return combinations[index]
    return (index,)


def x_at_once(x, spread=2):
    y = permutations(x)
    while True:
        result = tuple(map(lambda _: next(y), [1]*spread))
        if not result: return
        yield result


class SpriteLine:
    def __init__(self, pattern_a=0, pattern_b=0):
        self.cc = False
        self.patterns = [pattern_a, pattern_b]

    def __getitem__(self, n):
        return self.patterns[n]

    def __setitem__(self, n, pattern):
        self.patterns[n] = pattern

    def set_cc(self, bit):
        self.cc = bit

    def cc_bit(self):
        return 64 * self.cc

    def __str__(self):
        return '%s,%s' % (self.patterns[0], self.patterns[1])


class Sprite:
    def __init__(self, palette):
        self.colors = set()
        self.components = 0
        self.data = [dict() for i in range(DEF_H)]
        self.pos = None

    def add_line(self, line_num, color, cell, pattern, or_color_bit = False):
        self.colors.add(color)
        # Add new pattern data for a new colour if necessary
        if color not in self.data[line_num]:
            # 0: left pattern, 1: right pattern
            self.data[line_num][color] = SpriteLine()
        self.data[line_num][color][cell] = pattern
        # Activate CC (OR-colour flag)
        self.data[line_num][color].set_cc(or_color_bit)
        debug(f'** color {color} on line {line_num} set to {or_color_bit}')
        self.components = max(self.components, len(self.data[line_num]))
        debug(f'** sprite line has {self.components} components')

    def get_component(self, idx):
        data = { 'colors': [], 'patterns': [] }

        for cell in range(2):
            for line_num in range(16):
                try:
                    # Convert position index into colour index
                    color = sorted(self.data[line_num].keys())[idx]
                    debug(f'{line_num}: {idx=} -> {color=}, colors:', sorted(self.data[line_num]))

                    try:
                        byte = self.data[line_num][color][cell]
                    except KeyError:
                        byte = 0

                    # Activate OR-colour bit in colour if needed.
                    if cell == 0:
                        data['colors'].append(color + self.data[line_num][color].cc_bit())
                    data['patterns'].append(byte)
                except IndexError:
                    if not cell: data['colors'].append(0)
                    data['patterns'].append(0)

        return data

    def size(self):
        return 16 * self.components, 32 * self.components # bytes


def build_lookup_table(palette):
    """Return map where key is (r, g, b) and value is the palette index."""
    if len(palette) > MAX_COLORS:
        debug(f'{palette = }')
        raise IndexError

    lookup = {c: i for i, c in enumerate(palette)} # palette lookup

    for color in palette:
        if not all([type(c) == int for c in color]):
            raise TypeError

    return lookup


def get_palette_from_image(image):
    data = image.getdata()
    w, h = image.size
    palette = set()

    for y in range(h):
        for x in range(w):
            pixel = data[x + y * w]
            if pixel != IMG_TRANS:
                palette.add(pixel)

    palette = [IMG_TRANS] + sorted(palette)
    debug(f'get_palette_from_image: {palette}')
    return palette


def get_min_combination_size(image, palette):
    """Get number of sprites needed for colour combinations (including OR-colours) for the whole image."""
    data = image.getdata()
    new_data = []
    num_colors = 0
    w, h = image.size
    combs = set()

    # iterate over each sprite individually
    for y in range(0, h):
        for x in range(0, w, DEF_W):
            # 8x1 pattern
            pattern = [data[(x + i) + y * w] for i in range(DEF_W)]
            cols = set(pattern) #- {IMG_TRANS}
            # detect colour not found in palette (for a user-defined palette)
            if len(xcols := [c for c in cols if not c in palette]) > 0:
                xcols = 'colours %s' % rgb_list_to_hex_str(xcols)
                raise LookupError(xcols + f' near {x = }..{x + 16}, {y = }')
            # Writes down combinations of what is possible inside a 16x1 block
            combs.add(tuple(cols - {IMG_TRANS}))

    # Fill data with a multiple of 16x16 patterns
    new_data = (math.ceil(len(new_data) / 128) * 128 - len(new_data)) * [(0, 0, 0)] + list(cols)

    # Build sprite sheets for generated image
    min_components, _, new_palette, _ = build_sprite_sheet(new_data, 16, len(new_data) // 16, palette, 15, True)
    return min_components, new_palette


def decompose_indexes(colors, prime=set(), comb=set()):
    """Count how many colours were removed in a sprite line."""
    primes = set()
    combs = set()

    if len(colors) > 2:
        for c in combinations(colors, 2):
            debug(f'{c = }')
            if combs.intersection(c):
                continue
            # check third colour in OR-colour combination
            #1 | 3 = 3
            third = c[0] | c[1]
            if (not third in c) and (third in colors):
                combs.add(third)
                primes.add(c[0])
                primes.add(c[1])
    return combs, set(colors) - combs


class DeadEnd(Exception):
    """Abort when dead end is reached."""
    ...


class Found(Exception):
    """Found parameters when done."""

    def __init__(self, *args):
        self.args = args


def build_sprites(data, w, h, palette, prev_components):
    debug(f'{w=} x {h=}')
    lookup = build_lookup_table(palette)
    debug(f'** {lookup = }')
    index_lookup = lambda rgb: lookup[rgb]
    sprites = []

    # Create sprites for each 16x16 block from the image.
    for i in range(w // DEF_W * h // DEF_H):
        sprites.append(Sprite(palette))

    total_bytes = 0
    max_components = 0

    for y in range(0, h, DEF_H):
        for x in range(0, w, DEF_W):
            sprite = sprites[(x // DEF_W) + (y // DEF_H) * (w // DEF_W)]
            # current sprite pattern
            pattern = [data[x + i + ((y + j) * w)]
                    for j in range(DEF_H) for i in range(DEF_W)]
            cols = set([c for c in pattern]) - {IMG_TRANS}
            # empty sprite: do nothing and go to the next one
            if not cols: continue

            for j in range(DEF_H):
                debug(f'building sprite line {j}')
                cols = set([c for c in pattern[j * DEF_W: (j + 1) * DEF_W]]) - {IMG_TRANS}
                # indexes receives colours from the line
                indexes = list(map(index_lookup, cols))
                debug(f'line colours: {indexes} = ({cols})')
                # empty indexes: do nothing and go to the next one
                if not indexes: continue
                removed, primes = decompose_indexes(set(indexes))
                debug(f'decomposed colours: {removed = }, {primes = }')
                cc_bit_set = set()

                # Fill line pattern data on the left and right.
                for cell, i in ((0, 0), (1, 8)):
                    debug(f'sprite byte: {cell}')
                    sprite = sprites[(x // DEF_W) + (y // DEF_H) * (w // DEF_W)]
                    debug(f'sprite {x = }, {y = }')
                    # TODO: check if I can remove this
                    sprite.pos = x, y
                    # bytes for all 16 possible colours
                    byte = [0] * 16
                    bit = 7
                    # Iterate over each bit of the left and right
                    for k in range(8):
                        index = lookup[pattern[i + j * 16 + k]]
                        if index in removed:
                            # Draw pixel for colour combination.
                            colors = lookup_combination(index)
                            debug(f'combo colour {index} decomposed to colours: {colors}')
                            for c in colors:
                                debug(f'* combo: set pixel at {bit=} to colour={c}')
                                byte[c] |= 1 << bit
                            # Set CC bit on all sprites with lower priority.
                            for c1, c2 in combinations(colors, 2):
                                debug(f'** adding CC bit to line of colour {c2}') 
                                cc_bit_set.add(c2)
                        elif index > 0:
                            # Draw pixel for prime colour.
                            debug(f'* prime: set pixel at {bit=} to colour={index}')
                            byte[index] |= 1 << bit
                        bit -= 1

                    for color in indexes:
                        # Add to sprite only the used bytes.
                        if byte[color] != 0:
                            sprite.add_line(j, color, cell, byte[color], color in cc_bit_set)
                            # Abort if number of components remains the same
                            if sprite.components == prev_components:
                                raise DeadEnd()

                # debug sprite line
                debug('***', sprite.data[j])

            # Gather current sprite data.
            max_components = max(sprite.components, max_components)
            total_bytes += sprite.components * 32
            total_bytes += sprite.components * 16

    return sprites, max_components, total_bytes


def get_permutation_size(length):
    return reduce(lambda x, y: x * y, range(1, length + 1))


def build_sprite_sheet(data, width, height, palette, min_components, minimise):
    total_bytes = 0
    cur_components = 0
    cur_sprites = None
    cur_pal = None
    size = get_permutation_size(len(palette) - 1) if minimise else 1

    debug('** begin sprite sheet building...')
    prev_components = 15 # min_components + 2
    count = 0

    for partition in x_at_once(palette[1:], spread=1000):
        for tmp in partition:
            # Print progress update
            if DEBUG == 0:
                print('\rProgress: %.4f%%' % (count / size * 100), end='', file=sys.stderr)

            # Fix palette position 0 (transparent colour)
            pal = (IMG_TRANS,) + tmp
            debug(f'** current palette: {pal}')

            try:
                count += 1
                sprites, components, total_bytes = build_sprites(data, width, height,
                                                                 pal, prev_components)
                prev_components = components
            except DeadEnd:
                continue

            debug(f'** current loop components count: {components}')
            debug('========================================')
            # Get it out there first.
            if not cur_sprites:
                cur_components = components
                cur_sprites = sprites
                cur_pal = pal
            # Optimise.
            if minimise and components == min_components:
                # Abort execution when done.
                debug('Minimum component configuration found.')
                if DEBUG == 0: print(end='\n', file=sys.stderr)
                raise Found(components, sprites, pal, total_bytes)
            if minimise and components < cur_components:
                debug(f'Better component configuration found: {components} < {cur_components}')
                cur_components = components
                cur_sprites = sprites
                cur_pal = pal

            count += 1

    if DEBUG == 0: print(end='\n', file=sys.stderr)
    return cur_components, cur_sprites, cur_pal, total_bytes


def main():
    parser = ArgumentParser(description="PNG to MSX2 sprites",
                            epilog="""Copyright (C) 2022-2023 Pedro de Medeiros <pedro.medeiros@.gmail.com>"""
                            )

    parser.add_argument(
        "--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument("-i", "--id", dest="id", default="sprites", type=str,
                        help="variable name (default: sprites)")
    parser.add_argument("-b", "--basic", dest="basic", action="store_true",
                        help="BASIC output (default: C header)")
    parser.add_argument("-a", "--asm", dest="asm", action="store_true",
                        help="ASM output (default: C header)")
    parser.add_argument("-c", "--colors", dest="palette_colors", action="store_true",
                        help="include palette colors in C or ASM output") # TODO
    parser.add_argument("-p", "--palette", dest="pal_file", type=str,
                        help="set of colors to use from file")
    parser.add_argument("-m", "--minimise", dest="min", action="store_true",
                        help="try to minimise palette by brute force")
    parser.add_argument("--pal-only", dest="pal_only", action="store_true",
                        help="just output the palette")

    parser.add_argument("image", help="image to convert")

    args = parser.parse_args()

    try:
        image = Image.open(args.image)
    except IOError:
        parser.error('failed to open image "%s"' % args.image)

    if image.mode != 'RGB':
        parser.error('not a RGB image (%s detected)' % image.mode)

    if args.pal_file:
        with open(args.pal_file, 'r') as pal_file:
            palette = list(eval(pal_file.read()))
            if len(palette) > MAX_COLORS:
                parser.error('palette too big (maximum of 16 colors expected, got %i)' % len(palette))
            for (r, g, b) in palette:
                if not(int == type(r) == type(g) == type(b)):
                    parser.error('wrong palette type')
    else:
        palette = get_palette_from_image(image)
        if len(palette) > MAX_COLORS:
            parser.error('palette too big (maximum of 16 colors expected, got %i)' % len(palette))
        debug('** Using embedded palette: ', palette)

    if image.size[0] % DEF_W or image.size[1] % DEF_H:
        parser.error('%s size is not multiple of sprite size (%s, %s)' %
                     (args.image, DEF_W, DEF_H))

    #lookup = {y:x for x, y in enumerate(palette)} # palette lookup
    try:
        # Get mininum possible component size
        min_components, palette = get_min_combination_size(image, palette)
        debug(f'Minimal sprite count: {min_components}')
    except LookupError as e:
        parser.error('colors used in the image must be present in the palette: %s' % e)

    try:
        cur_components, cur_sprites, cur_pal, total_bytes = build_sprite_sheet(image.getdata(),
                                                                               image.width,
                                                                               image.height,
                                                                               palette,
                                                                               min_components,
                                                                               False)
    except Found as found:
        cur_components, cur_sprites, cur_pal, total_bytes = f.args

    debug(f'Sprite components: {cur_components}')
    out = []
    pos = []

    for sprite in cur_sprites:
        for count in range(sprite.components):
            out.append(sprite.get_component(count))
            pos.append(sprite.pos)

    debug(f'patterns = ', out)
    debug(f'Total bytes: {total_bytes}')
    debug(f'Current palette: {cur_pal}')

    if args.basic:
        line_num = 100
        if not args.pal_only:
            println = lambda *x: print(*x, end=ENDL)
            println('%d SCREEN 5,2' % line_num)
            # set same background color of the original image
            line_num += 10; println('%d VDP(9)=VDP(9) OR &H20: COLOR 15,0,0' % line_num)
            line_num += 10
        println('%d REM PALETTE' % line_num)
        for index, color in enumerate(cur_pal):
            if color != (-1, -1, -1):
                msx_color = round(color[0] / 255 * 7), round(color[1] / 255 * 7), round(color[2] / 255 * 7)
                line_num += 10; println('%d COLOR=%s: REM RGB=%s' % (line_num, (index,) + msx_color, color))
        if not args.pal_only:
            for i in range(len(out)):
                line_num += 10; println('%d REM READ %s_COLORS(%d)' % (line_num, args.id.upper(), i))
                line_num += 10; println('%d A$="":FOR I = 1 TO 16:READ A%%:A$=A$+CHR$(A%%):NEXT:COLOR SPRITE$(%d)=A$' % (line_num, i))
                line_num += 10; println('%d REM READ %s_PATTERN(%d)' % (line_num, args.id.upper(), i))
                line_num += 10; println('%d A$="":FOR I = 1 TO 32:READ A%%:A$=A$+CHR$(A%%):NEXT:SPRITE$(%d)=A$' % (line_num, i))
            line_num += 10; println('%d REM PUT %s SPRITE ON SCREEN' % (line_num, args.id.upper()))
            for i in range(len(out)):
                screen_pos = 100 + pos[i][0], 100 + pos[i][1]
                line_num += 10; println('%d PUT SPRITE %d,%s,,%d' % (line_num, i, screen_pos, i))
            line_num += 10; println('%d IF INKEY$ = "" GOTO %d' % (line_num, line_num))
            line_num += 10; println('%d END' % line_num)
            line_num  = 10**(math.ceil(math.log10(line_num)+0.00001))
            println('%d REM %s_TOTAL = %d' % (line_num, args.id.upper(), total_bytes))
            for i in range(len(out)):
                line_num += 10; println('%d REM %s_COLORS(%d)' % (line_num, args.id.upper(), i))
                line_num += 10; print('%d %s' % (line_num, to_hex_list_str_basic(out[i]['colors'])), end='')
                line_num += 10; println('%d REM %s_PATTERN(%d)' % (line_num, args.id.upper(), i))
                line_num += 10; print('%d %s' % (line_num, to_hex_list_str_basic(out[i]['patterns'])), end='')
        println('')

    elif args.asm:
        if not args.pal_only:
            print('%s_TOTAL = %d\n' % (args.id.upper(), total_bytes))

        print('%s_palette:' % args.id)
        for index, color in enumerate(cur_pal):
            if color != (-1, -1, -1):
                msx_color = round(color[0] / 255 * 7), round(color[1] / 255 * 7), round(color[2] / 255 * 7)
                print('\tdb #0x%i%i, #0x%i\t\t; %i: RGB = %i, %i, %i' % ((msx_color[0], msx_color[2], msx_color[1], index) + color))
        print()

        if not args.pal_only:
            color_out = ''; pattern_out = ''
            for i in range(len(out)):
                print('%s_color%d:' % (args.id, i))
                print(to_hex_list_str_asm(out[i]['colors']))
                print('%s_pattern%d:' % (args.id, i))
                print(to_hex_list_str_asm(out[i]['patterns']))
    else:
        if not args.pal_only:
            print('#ifndef _%s_H' % args.id.upper())
            print('#define _%s_H\n' % args.id.upper())

        print('// palette data\n\nconst unsigned char %s_palette[] =\n{' % args.id)
        for index, color in enumerate(cur_pal):
            if color != (-1, -1, -1):
                msx_color = round(color[0] / 255 * 7), round(color[1] / 255 * 7), round(color[2] / 255 * 7)
                print('\t0x%i%i, 0x%i\t\t// %i: RGB = %i, %i, %i' % ((msx_color[0], msx_color[2], msx_color[1], index) + color))
        print('}\n')

        if not args.pal_only:
            print('#define %s_TOTAL %d\n' % (args.id.upper(), total_bytes))
            color_out = ''; pattern_out = ''
            for count in range(len(out)):
                color_out   += '{\n' + to_hex_list_str(out[count]['colors']) + '},\n'
                pattern_out += '{\n' + to_hex_list_str(out[count]['patterns']) + '}'

            print('#ifdef LOCAL\n')
            print('const unsigned char %s_colors[%d][%d] = {\n%s\n};\n' % (
                  args.id, len(out), len(out[0]['colors']), color_out))

            print('const unsigned char %s_patterns[%d][%d] = {\n%s\n};\n' % (
                  args.id, len(out), len(out[0]['patterns']), pattern_out))

            print('#else\n')
            print('extern const unsigned char %s_colors[%d][%d];' %
                  (args.id, len(out), len(out[0]['colors'])))

            print('extern const unsigned char %s_patterns[%d][%d];' %
                  (args.id, len(out), len(out[0]['patterns'])))
            print('\n#endif // LOCAL')
            print('#endif // _%s_H\n' % args.id.upper())


if __name__ == '__main__':
    main()
