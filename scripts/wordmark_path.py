"""Print the SVG path for the "Ninsei" wordmark from DotGothic16 (pasted into ui/30_parts.js as WORDMARK_PATH).

Needs fontTools (not a Ninsei dependency; use a throwaway venv) and DotGothic16-Regular.ttf from
https://github.com/google/fonts/tree/main/ofl/dotgothic16 (SIL OFL 1.1, docs/fonts/DotGothic16-OFL.txt).
Usage: python scripts/wordmark_path.py DotGothic16-Regular.ttf"""
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

font = TTFont(sys.argv[1])
glyphs, cmap, ascent = font.getGlyphSet(), font.getBestCmap(), font["hhea"].ascent
pen, x = SVGPathPen(glyphs), 0
for ch in "Ninsei":
    g = glyphs[cmap[ord(ch)]]
    g.draw(TransformPen(pen, (1, 0, 0, -1, x, ascent)))  # flip y; glyphs sit 500 units apart
    x += g.width
print(pen.getCommands())
