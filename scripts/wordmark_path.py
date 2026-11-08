"""Print the SVG path for the "Ninsei" wordmark from DotGothic16 (pasted into ui/30_parts.js as WORDMARK_PATH).

The letters are placed by their ink, not by the font's advance widths: DotGothic16 is monospaced, so its own
spacing leaves wide gaps around both i's. Every gap between two letters is GAP units (two of the font's pixels),
and the ink starts at x = MARGIN; the viewBox in ui/30_parts.js is that ink width plus MARGIN on each side
(tests/test_brand.py checks the gaps and the viewBox).

Needs fontTools (not a Ninsei dependency; use a throwaway venv) and DotGothic16-Regular.ttf from
https://github.com/google/fonts/tree/main/ofl/dotgothic16 (SIL OFL 1.1, docs/fonts/DotGothic16-OFL.txt).
Usage: python scripts/wordmark_path.py DotGothic16-Regular.ttf"""
import sys

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

GAP = 124     # two of DotGothic16's 62-unit pixels
MARGIN = 28   # the N's own left side bearing, kept so the old crop still fits

font = TTFont(sys.argv[1])
glyphs, cmap, ascent = font.getGlyphSet(), font.getBestCmap(), font["hhea"].ascent
pen, x = SVGPathPen(glyphs), MARGIN
for ch in "Ninsei":
    g = glyphs[cmap[ord(ch)]]
    bounds = BoundsPen(glyphs)
    g.draw(bounds)
    x_min, _, x_max, _ = bounds.bounds
    g.draw(TransformPen(pen, (1, 0, 0, -1, x - x_min, ascent)))  # flip y; the ink starts at x
    x += (x_max - x_min) + GAP
print(pen.getCommands())
print(f"viewBox width: {round(x - GAP + MARGIN)}", file=sys.stderr)
