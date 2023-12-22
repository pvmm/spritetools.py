![Original/sprites in OpenMSX](/docs/sprites.png "Original/sprites in OpenMSX")

png2sprites.py
==============

Converts png image into MSX2 sprites. Resulting sprites will always align perfectly over previous layer. Sample images are from the wiki https://www.msx.org/wiki/The_OR_Color. **png2sprites.py** is a heavily modified version of `png2sprites.py` script tool from reidrac's https://gitlab.com/reidrac/ubox-msx-lib set of tools and libraries.


Files
-----

* `README.md`: this file
* `png2sprites.py`: conversion script that reads PNG files in RGB and converts them into MSX2 compatible VRAM sprite data.
* `samples/wit.pal`: 16-colour palette triples (8-bit RGB values) that specify an MSX2 palette. The zeroth colour is used to eliminate PNG background colour.
* `samples/wit.png`: sample image of Wit from Treasure of Uşas.
* `samples/WIT.BAS`: simple BASIC code that displays Wit sprite in SCREEN 5.
* `samples/snake.pal`: 15 color triples (RGB) that specifies a MSX2 palette.
* `samples/snake.png`: sample image of Snake from Metal Gear 1.
* `samples/SNAKE.BAS`: simple BASIC code that displays Snake sprite in SCREEN 5.
* `samples/palette.pal`: 16-colour palette triples (8-bit RGB values) used in palette.png.
* `samples/palette.png`: sample image using all colours.
* `samples/PALETTE.BAS`: simple BASIC code the displays the sprite generated from palette.png.


How to use it
-------------

In addition to the source PNG image, png2sprites.py expects a palette file, which is basically a tuple of 16 RGB triplets and zeroth colour just removes the background from the original PNG file.

```
(255,0,255),(0,0,0),(145,109,0),(109,72,0),(36,36,36),(72,72,72),(109,109,109),(255,255,255),(109,109,109),(0,72,218),(255,0,0),(218,182,145),(182,109,0),(0,145,72),(0,72,36),(0,0,0)
```

Help message:

```
usage: png2sprites.py [-h] [--version] [-i ID] [-b] [-a] [-c] [-p PAL_FILE] [-m MIN] image

PNG to MSX2 sprites

positional arguments:
  image                 image to convert

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  -i ID, --id ID        variable name (default: sprites)
  -b, --basic           BASIC output (default: C header)
  -a, --asm             ASM output (default: C header)
  -c, --colors          include palette colors in C or ASM output
  -p PAL_FILE, --palette PAL_FILE
                        set of colors to use from file
  -m, --minimise        try to minimise palette by brute force
```

The `--minimise` option will attempt to minimise the number of sprites by or-color replacement after palette permutation and may take several seconds if not minutes. It is an experimental feature and may increase your carbon footprint and return stupid results.

You can refresh sample results with:

```
./png2sprites.py -i wit -b -p samples/wit.pal samples/wit.png > samples/WIT.BAS
./png2sprites.py -i snake -b -p samples/snake.pal samples/snake.png > samples/SNAKE.BAS
```


TODO
----

* palette export feature;
* ~~palette optimizations to reduce sprite count;~~
* ~~make palette file optional;~~
* add an option to optimise away palette file;
* make palette minimisation faster;
