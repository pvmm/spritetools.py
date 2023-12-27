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
import contextlib
import math

from argparse import ArgumentParser
from itertools import permutations
from itertools import combinations
from PIL import Image

__version__ = "1.1"

MAX_COLORS = 16
DEF_W = 16
DEF_H = 16

IMG_TRANS = (255, 0, 255)
MSX_TRANS = (0, 0, 0)
FAKE_PAL = [(-1, -1, -1)] * MAX_COLORS

# Enable/disable DEBUG mode
if os.environ.get('DEBUG', False):
    debug = lambda *x, **y: print(*x, **y, file=sys.stderr)
else:
    debug = lambda *x, **y: None


def to_hex_list_str(src):
    """Writes sprites as C-style hexadecimal data."""
    out = ""
    for i in range(0, len(src), 8):
        out += ', '.join(["0x%02x" % b for b in src[i:i + 8]]) + ',\n'
    return out


def to_hex_list_str_asm(src):
    """Writes sprites as assembly-style hexadecimal data."""
    out = ""
    for i in range(0, len(src), 8):
        out += '\tdb ' + ', '.join(["#0x%02x" % b for b in src[i:i + 8]])
        out += '\n'
    return out


def to_hex_list_str_basic(src):
    """Writes sprites as BASIC-style hexadecimal data."""
    return "DATA %s\n" % ', '.join(["&H%02X" % b for b in src])


def lookup_combination(index):
    combinations = { 3: [1, 2], 5: [1, 4], 7: [1, 2, 4], 9: [1, 8] }
    return combinations[index]


def decombine_colors(indexes):
    debug('decombining colors:', indexes)
    rest = list(indexes) # 1,4,5
    cur = rest.pop()
    debug(f'{cur = }')
    removed = {}
    factors = []
    factor = True

    if cur > 1 and len(rest) > 1:
        for c1, c2 in permutations(rest, 2):
            debug(f'{c1 = }, {c2 = }')
            if (c1 | c2) == cur: # 1,4,5
                factor = False
                debug(f'[1] decombine_colors({rest})')
                nremoved, rest, nfactors = decombine_colors(rest)
                if c2 in nfactors:
                    if removed.get(cur, False):
                        debug(f'(0) removed[{cur}].append({c2})')
                        removed[cur].append(c2)
                    else:
                        debug(f'(1) removed[{cur}] = [{c2}]')
                        removed[cur] = [c2]
                elif nremoved.get(c2, False):
                    if removed.get(cur, False):
                        debug(f'(2) removed[{cur}].append({nremoved[c2]})')
                        removed[cur].append(nremoved[c2])
                    else:
                        debug(f'(3) removed[{cur}] = {nremoved[c2]}')
                        removed[cur] = list(nremoved[c2])
                removed.update(nremoved)
                factors.extend(nfactors)

                if len(rest):
                    debug(f'[2] decombine_colors({rest})')
                    nremoved, rest, nfactors = decombine_colors(rest)
                    if c1 in nfactors:
                        if removed.get(cur, False):
                            debug(f'(4) removed[{cur}].append({c1})')
                            removed[cur].append(c1)
                        else:
                            debug(f'(5) removed[{cur}] = [{c1}]')
                            removed[cur] = [c1]
                else:
                    if removed.get(cur, False):
                        debug(f'(6) removed[{cur}].append({c1})')
                        removed[cur].append(c1)
                    else:
                        debug(f'(7) removed[{cur}] = [{c1}]')
                        removed[cur] = [c1]

                debug(f'non-factor: returning removed={removed}, rest={rest}, factors={factors}, cur={cur}')
                return removed, rest, factors

    if factor:
        if len(rest) > 2:
            debug(f'[3] decombine_colors({rest})')
            nremoved, rest, nfactors = decombine_colors(rest)
            removed.update(nremoved)
            factors.append(cur)
            factors.extend(nfactors)
            debug(f'(1) factor: returning removed={removed}, rest={rest}, factors={factors}, cur={cur}')
            return removed, rest, factors
        factors.extend(indexes)
        debug(f'(2) factor: returning removed={removed}, rest={[]}, factors={factors}, cur={cur}')
        return removed, [], factors

    debug(f'finished: returning removed={removed}, rest={rest}, factors={factors}')
    return removed, rest, factors


class Sprite:
    def __init__(self, palette):
        self.colors = set()
        self.components = 0
        self.data = []
        self.pos = None
        for i in range(16):
            self.data.append(dict())

    def add_line(self, line_num, color, cell, pattern, combine=False):
        self.colors.add(color)
        if color not in self.data[line_num]:
            self.data[line_num][color] = [0, 0]
        self.data[line_num][color][cell] = pattern
        if combine:
            self.data[line_num][color][0] = -abs(self.data[line_num][color][0])
        self.components = max(self.components, len(self.data[line_num]))

    def get_component(self, idx):
        data = { 'colors': [], 'patterns': [] }

        for cell in range(2):
            for line_num in range(16):
                color = 0
                try:
                    color = sorted(self.data[line_num].keys())[idx]
                    byte = 0
                    with contextlib.suppress(KeyError):
                        byte = self.data[line_num][color][cell]
                    if not cell: data['colors'].append(color + (64 if byte < 0 else 0))
                    data['patterns'].append(abs(byte))
                except IndexError:
                    if not cell: data['colors'].append(0)
                    data['patterns'].append(0)

        return data

    def size(self):
        return 16 * self.components, 32 * self.components


def build_lookup_table(palette):
    """Return map where key is (r, g, b) and value is the palette index."""
    lookup = {c: i for i, c in enumerate(palette)} # palette lookup

    if len(palette) > MAX_COLORS:
        raise IndexError
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
            pixel = data[x + y * DEF_W]
            if pixel == IMG_TRANS: continue
            palette.add(pixel)

    return ([IMG_TRANS] + sorted(palette))


def get_min_combination_size(image, palette):
    """Get number of sprites needed for colour combinations (including OR-colours) for the whole image."""
    data = image.getdata()
    num_colors = 0
    w, h = image.size

    # iterate over each sprite individually
    for y in range(0, h, DEF_H):
        for x in range(0, w, DEF_W):
            # current sprite pattern
            pattern = [data[x + i + ((y + j) * w)]
                       for j in range(DEF_H) for i in range(DEF_W)]
            cols = set([c for c in pattern if c != IMG_TRANS])
            # detect colour not found in palette (for a user-defined palette)
            if len(xcols := [c for c in cols if not c in palette]) > 0:
                raise LookupError(xcols)

            # mark simultaneously used colours on a single line
            for start in range(0, len(pattern), DEF_W):
                num_colors = max(num_colors, len(set(pattern[start : start + DEF_W]) - {IMG_TRANS}))

    #debug(f'{num_colors = }')
    return max(0, math.ceil(math.log2(num_colors+0.00001)))


def decompose_colors(colors, prime=set(), comb=set()):
    """Count how many colours were removed in a sprite line."""
    primes = set()
    combs = set()

    if len(colors) > 2:
        for c in combinations(colors, 2):
            if combs.intersection(c):
                continue
            # check third colour in OR-colour combination
            third = c[0] | c[1]
            if third in colors:
                colors -= {third}
                combs.add(third)
                primes.add(c[0])
    return combs, set(colors) - combs


def build_sprites(image, palette):
    w, h = image.size
    data = image.getdata()
    lookup = build_lookup_table(palette)
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
                # indexes receives colors from the line
                indexes = set(map(lambda rgb: lookup[rgb], cols))
                # empty indexes: do nothing and go to the next one
                if not indexes: continue
                removed, primes = decompose_colors(indexes)
                debug(f'{removed = }, {primes = }')

                for cell, i in ((0, 0), (1, 8)):
                    sprite = sprites[(x // DEF_W) + (y // DEF_H) * (w // DEF_W)]
                    sprite.pos = x, y
                    byte = [0] * 16
                    p = 7
                    comb = set()
                    for k in range(8):
                        index = lookup[pattern[i + j * 16 + k]]
                        if index in removed:
                            debug(f'{ index = }')
                            colors = lookup_combination(index)
                            debug(f'colors={colors}')
                            for c in colors:
                                byte[c] |= 1 << p
                            for c1, c2 in permutations(colors, 2):
                                comb.add(max(c1, c2))
                        elif index > 0:
                            byte[index] |= 1 << p
                        p -= 1

                    for color in indexes:
                        if byte[color] != 0:
                            sprite.add_line(j, color, cell, byte[color], color in comb)

            max_components = max(sprite.components, max_components)
            total_bytes += sprite.components * 32
            total_bytes += sprite.components * 16

    return sprites, max_components, total_bytes


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
        parser.error("failed to open the image")

    if image.mode != "RGB":
        parser.error("not a RGB image (%s detected)" % image.mode)

    if args.pal_file:
        with open(args.pal_file, 'r') as pal_file:
            palette = list(eval(pal_file.read()))
            lookup = {y:x for x, y in enumerate(palette)} # palette lookup
            if len(palette) > MAX_COLORS:
                parser.error("palette too big (maximum of 16 colors expected, got %i)" % len(palette))
            for (r, g, b) in palette:
                if not(int == type(r) == type(g) == type(b)):
                    parser.error("wrong palette type")
    else:
        palette = get_palette_from_image(image)
        if len(palette) > MAX_COLORS:
            parser.error("palette too big (maximum of 16 colors expected, got %i)" % len(palette))
        debug('using embedded palette: ', palette)
        lookup = {y:x for x, y in enumerate(palette)} # palette lookup

    w, h = image.size

    if w % DEF_W or h % DEF_H:
        parser.error("%s size is not multiple of sprite size (%s, %s)" %
                     (args.image, DEF_W, DEF_H))

    # Get mininum possible size and try to match
    try:
        min_size = get_min_combination_size(image, palette)
        debug(f'min_size = {min_size}')
    except LookupError as e:
        parser.error("Colors used in the image must be present in the palette: %s" % e)

    min_components = 15
    best_sprites = None
    best_pal = None
    num = 0

    if args.min:
        collection = permutations(palette[1:])
    else:
        collection = (tuple(palette[1:]),)

    for tmp in collection:
        pal = (palette[0],) + tmp
        sprites, components, total_bytes = build_sprites(image, pal)
        if components < min_components:
            min_components = components
            debug('\nmin_components is now', min_components)
            best_sprites, best_pal = sprites, pal
        if components == min_size:
            break

    debug(f'components = {min_components}')
    out = []
    pos = []
    total_bytes = 0

    for sprite in best_sprites:
        for count in range(sprite.components):
            out.append(sprite.get_component(count))
            pos.append(sprite.pos)

    debug(f'total_bytes = {total_bytes}')
    debug(f'pal = {best_pal}')

    if args.basic:
        line_num = 100
        if not args.pal_only:
            print('%d SCREEN 5,2' % line_num)
            line_num += 10; print('%d VDP(9)=VDP(9) OR &H20: COLOR 15,0,0' % line_num) # set same background color of the original image
            line_num += 10
        print('%d REM PALETTE' % line_num)
        for index, color in enumerate(best_pal):
            if color != (-1, -1, -1):
                msx_color = round(color[0] / 255 * 7), round(color[1] / 255 * 7), round(color[2] / 255 * 7)
                line_num += 10; print('%d COLOR=%s: REM RGB=%s' % (line_num, (index,) + msx_color, color))
        if not args.pal_only:
            for i in range(len(out)):
                line_num += 10; print('%d REM READ %s_COLORS(%d)' % (line_num, args.id.upper(), i))
                line_num += 10; print('%d A$="":FOR I = 1 TO 16:READ A%%:A$=A$+CHR$(A%%):NEXT:COLOR SPRITE$(%d)=A$' % (line_num, i))
                line_num += 10; print('%d REM READ %s_PATTERN(%d)' % (line_num, args.id.upper(), i))
                line_num += 10; print('%d A$="":FOR I = 1 TO 32:READ A%%:A$=A$+CHR$(A%%):NEXT:SPRITE$(%d)=A$' % (line_num, i))
            line_num += 10; print('%d REM PUT %s SPRITE ON SCREEN' % (line_num, args.id.upper()))
            for i in range(len(out)):
                screen_pos = 100 + pos[i][0], 100 + pos[i][1]
                line_num += 10; print('%d PUT SPRITE %d,%s,,%d' % (line_num, i, screen_pos, i))
            line_num += 10; print('%d IF INKEY$ = "" GOTO %d' % (line_num, line_num))
            line_num += 10; print('%d END' % line_num)
            line_num  = 10**(math.ceil(math.log10(line_num)+0.00001))
            print("%d REM %s_TOTAL = %d" % (line_num, args.id.upper(), total_bytes))
            for i in range(len(out)):
                line_num += 10; print("%d REM %s_COLORS(%d)" % (line_num, args.id.upper(), i))
                line_num += 10; print("%d %s" % (line_num, to_hex_list_str_basic(out[i]['colors'])), end='')
                line_num += 10; print("%d REM %s_PATTERN(%d)" % (line_num, args.id.upper(), i))
                line_num += 10; print("%d %s" % (line_num, to_hex_list_str_basic(out[i]['patterns'])), end='')
        print()

    elif args.asm:
        if not args.pal_only:
            print("%s_TOTAL = %d\n" % (args.id.upper(), total_bytes))

        print('%s_palette:' % args.id)
        for index, color in enumerate(best_pal):
            if color != (-1, -1, -1):
                msx_color = round(color[0] / 255 * 7), round(color[1] / 255 * 7), round(color[2] / 255 * 7)
                print('\tdb #0x%i%i, #0x%i\t\t; %i: RGB = %i, %i, %i' % ((msx_color[0], msx_color[2], msx_color[1], index) + color))
        print()

        if not args.pal_only:
            color_out = ""; pattern_out = ""
            for i in range(len(out)):
                print("%s_color%d:" % (args.id, i))
                print(to_hex_list_str_asm(out[i]['colors']))
                print("%s_pattern%d:" % (args.id, i))
                print(to_hex_list_str_asm(out[i]['patterns']))
    else:
        if not args.pal_only:
            print("#ifndef _%s_H" % args.id.upper())
            print("#define _%s_H\n" % args.id.upper())

        print('// palette data\n\nconst unsigned char %s_palette[] =\n{' % args.id)
        for index, color in enumerate(best_pal):
            if color != (-1, -1, -1):
                msx_color = round(color[0] / 255 * 7), round(color[1] / 255 * 7), round(color[2] / 255 * 7)
                print('\t0x%i%i, 0x%i\t\t// %i: RGB = %i, %i, %i' % ((msx_color[0], msx_color[2], msx_color[1], index) + color))
        print('}\n')

        if not args.pal_only:
            print("#define %s_TOTAL %d\n" % (args.id.upper(), total_bytes))
            color_out = ""; pattern_out = ""
            for count in range(len(out)):
                color_out   += '{\n' + to_hex_list_str(out[count]['colors']) + '},\n'
                pattern_out += '{\n' + to_hex_list_str(out[count]['patterns']) + '}'

            print("#ifdef LOCAL\n")
            print("const unsigned char %s_colors[%d][%d] = {\n%s\n};\n" % (
                  args.id, len(out), len(out[0]['colors']), color_out))

            print("const unsigned char %s_patterns[%d][%d] = {\n%s\n};\n" % (
                  args.id, len(out), len(out[0]['patterns']), pattern_out))

            print("#else\n")
            print("extern const unsigned char %s_colors[%d][%d];" %
                  (args.id, len(out), len(out[0]['colors'])))

            print("extern const unsigned char %s_patterns[%d][%d];" %
                  (args.id, len(out), len(out[0]['patterns'])))
            print("\n#endif // LOCAL")
            print("#endif // _%s_H\n" % args.id.upper())


if __name__ == "__main__":
    main()
