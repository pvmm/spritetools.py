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

import sys
import contextlib

from argparse import ArgumentParser
from itertools import permutations
from PIL import Image

__version__ = "1.0"

DEF_W = 16
DEF_H = 16

TRANS = (255, 0, 255)
debug = lambda *x: None


def to_hex_list_str(src):
    out = ""
    for i in range(0, len(src), 8):
        out += ', '.join(["0x%02x" % b for b in src[i:i + 8]]) + ',\n'
    return out


def to_hex_list_str_asm(src):
    out = ""
    for i in range(0, len(src), 8):
        out += '\tdb ' + ', '.join(["#%02x" % b for b in src[i:i + 8]])
        out += '\n'
    return out


def to_hex_list_str_basic(line_num, src):
    out = ""
    for i in range(0, len(src), 8):
        out += "%04d DATA %s\n" % (line_num, ', '.join(["&H%02X" % b for b in src[i:i + 8]]))
        line_num += 10
    return line_num, out


def decombine_colors(indexes):
    tmp = list(indexes)
    curr = tmp.pop()
    removed = {}

    while curr > 1 and len(tmp) > 1:
        for c1, c2 in permutations(tmp, 2):
           if c1 | c2 == curr:
               indexes.pop(indexes.index(curr))
               removed[curr] = (c1, c2)
               break
        curr = tmp.pop()

    return removed, indexes


class Sprite:
    def __init__(self):
        self.colors = set()
        self.components = 0
        self.data = []
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
            for line_num in range(0, 16):
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


def main():

    parser = ArgumentParser(description="PNG to MSX2 sprites",
                            epilog="""Copyright (C) 2022 Pedro de Medeiros <pedro.medeiros@.gmail.com>"""
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

    parser.add_argument("image", help="image to convert")

    args = parser.parse_args()

    try:
        image = Image.open(args.image)
    except IOError:
        parser.error("failed to open the image")

    if image.mode != "RGB":
        parser.error("not a RGB image (%s detected)" % image.mode)

    with open(args.pal_file, 'r') as pal_file:
        pal = list(eval(pal_file.read()))
        lookup = {y:x for x, y in enumerate(pal)} # palette lookup
        if len(pal) != 16:
            parser.error("wrong palette size (16 colors expected, got %i)" % len(pal))
        for (r, g, b) in pal:
            if not(int == type(r) == type(g) == type(b)):
                parser.error("wrong palette type")

    (w, h) = image.size

    if w % DEF_W or h % DEF_H:
        parser.error("%s size is not multiple of sprite size (%s, %s)" %
                     (args.image, DEF_W, DEF_H))

    data = image.getdata()
    sprites = []
    for i in range(w // DEF_W * h // DEF_H):
        sprites.append(Sprite())

    debug("sprite map size = %i" % len(sprites))
    total_bytes = 0

    for y in range(0, h, DEF_H):
        for x in range(0, w, DEF_W):
            tile = [data[x + i + ((y + j) * w)]
                    for j in range(DEF_H) for i in range(DEF_W)]
            cols = set([c for c in tile if c is not TRANS])
            if len([c for c in cols if not c in pal]) > 0:
                parser.error("Colors used in the image must be present in the palette")

            if not cols: continue

            for j in range(16):
                line = set() # all colors on current line
                for i in range(16):
                    idx = lookup[tile[i + j * 16]]
                    if idx: line.add(idx)

                if not line: continue
                removed, line = decombine_colors(list(line))

                for cell, i in ((0, 0), (1, 8)):
                    sprite = sprites[(x // DEF_W) + (y // DEF_H) * (w // DEF_W)]
                    byte = [0] * 16
                    p = 7
                    comb = {}
                    for k in range(8):
                        idx = lookup[tile[i + j * 16 + k]]
                        if idx in removed:
                            c1, c2 = removed[idx]
                            byte[c1] |= 1 << p
                            byte[c2] |= 1 << p
                            comb[max(c1, c2)] = True
                        elif idx > 0:
                            byte[idx] |= 1 << p
                        p -= 1

                    for color in line:
                        if byte[color] != 0:
                            sprite.add_line(j, color, cell, byte[color], comb.get(color, False))

            total_bytes += sprite.components * 32 
            total_bytes += sprite.components * 16

    debug(f'components = {sprite.components}')
    out = []

    for sprite in sprites:
        for count in range(sprite.components):
            out.append(sprite.get_component(count))

    debug(f'total_bytes = {total_bytes}')

    if args.basic:
        line_num = 1000
        print("%d REM %s_TOTAL = %d" % (line_num, args.id.upper(), total_bytes))
        line_num += 10

        color_out = ""; pattern_out = ""
        for i, count in enumerate(range(len(out))):
            print("%d REM %s_COLORS(%d)" % (line_num, args.id.upper(), i))
            line_num, data = to_hex_list_str_basic(line_num + 10, out[count]['colors'])
            print(data, end='')
            print("%d REM %s_PATTERN(%d)" % (line_num, args.id.upper(), i))
            line_num, data = to_hex_list_str_basic(line_num + 10, out[count]['patterns'])
            print(data, end='')

    elif args.asm:
        print("%s_TOTAL = %d\n" % (args.id.upper(), total_bytes))
        print("%s:\n" % args.id)

        color_out = ""; pattern_out = ""
        for i, count in enumerate(range(len(out))):
            print("%s_color%d:" % (args.id, i))
            print(to_hex_list_str_asm(out[count]['colors']))
            print("%s_pattern%d:" % (args.id, i))
            print(to_hex_list_str_asm(out[count]['patterns']))
    else:
        print("#ifndef _%s_H" % args.id.upper())
        print("#define _%s_H\n" % args.id.upper())
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
