"""Draw the pipeline figure for the README, once for a light page and once for a dark one.

usage: python docs/make_pipeline.py        writes docs/pipeline-light.svg and docs/pipeline-dark.svg
"""
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

THEMES = {
    "light": {
        "panel": "#f6f8fa", "panel_line": "#d0d7de", "text": "#1f2328", "muted": "#59636e", "arrow": "#818b98",
        "source": ("#ffffff", "#afb8c1"), "claude": ("#f3efff", "#8250df"), "script": ("#eef2f6", "#6e7781"),
        "paid": ("#fff0ea", "#cf5a30"), "you": ("#e3f6f0", "#178a6b"),
    },
    "dark": {
        "panel": "#151b23", "panel_line": "#3d444d", "text": "#f0f6fc", "muted": "#9198a1", "arrow": "#768390",
        "source": ("#0d1117", "#656c76"), "claude": ("#251c42", "#a48bfa"), "script": ("#1e242c", "#7d8590"),
        "paid": ("#3b1e14", "#ef8a62"), "you": ("#0e2f27", "#3fb98f"),
    },
}
TAGS = {"source": "INPUT", "claude": "CLAUDE", "script": "SCRIPT", "paid": "PAID", "you": "YOU"}

STAGES = [
    ("Prepare", [
        ("source", "One launch", "a source video, a language, a budget", "--language es --budget 3"),
        ("script", "Separate voice from music", "BS-Roformer, on your machine", "stems/"),
        ("claude", "Draft the scene", "who speaks, when, and where", "scene.json"),
        ("script", "Measure the original", "phrases, talk time, level, pitch", "measure.json"),
        ("claude", "Translate to fit", "target language, sized to each phrase", "scene.json"),
    ]),
    ("Perform", [
        ("paid", "Design the voices", "Voice Design, three takes each", "--language es"),
        ("script", "Choose the voices", "most distinct takes, or by ear if you ask", "cast.json"),
        ("claude", "Add emotion tags", "from the original actor's delivery", "[shouts] [weary]"),
        ("paid", "Generate the dialogue", "Text to Dialogue v4, block by block", "--language es"),
        ("paid", "Cut into takes", "Scribe finds where each line was said", "takes/"),
    ]),
    ("Fit and mix", [
        ("script", "Fit to the original", "up to 1.22x; lines still over are redone", "fit.json"),
        ("script", "Process and mix", "original voice -14 dB, music -5 dB", "out/dub_mix.wav"),
        ("script", "Check the levels", "finds parts that sink into the music", "check_levels.py"),
        ("script", "Render", "-18 LUFS, plus a timing check", "dub.mp4"),
        ("you", "Listen, if you want", "the report says where to listen", "optional"),
    ]),
]

WIDTH, MARGIN, GAP = 960, 16, 20
PANEL_W = (WIDTH - 2 * MARGIN - 2 * GAP) // 3
INSET, CARD_H, ROW_GAP, TOP = 16, 68, 14, 60
CARD_W = PANEL_W - 2 * INSET
ROWS = 5
PANEL_BOTTOM = TOP + ROWS * CARD_H + (ROWS - 1) * ROW_GAP + 16
REDO_Y = PANEL_BOTTOM + 18
LEGEND_Y = REDO_Y + 32
HEIGHT = LEGEND_Y + 26


def panel_x(col):
    return MARGIN + col * (PANEL_W + GAP)


def card_x(col):
    return panel_x(col) + INSET


def card_y(row):
    return TOP + row * (CARD_H + ROW_GAP)


def text(x, y, value, fill, size=12, weight=None, family=SANS, anchor=None):
    extra = (f' font-weight="{weight}"' if weight else "") + (f' text-anchor="{anchor}"' if anchor else "")
    return f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-family="{family}"{extra}>{escape(value)}</text>'


def draw(theme):
    t = THEMES[theme]
    arrow = f'stroke="{t["arrow"]}" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title">',
        '<title id="title">The anime-redub pipeline, from source video to finished dub</title>',
        f'<defs><marker id="head" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="{t["arrow"]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>',
    ]
    links = []  # drawn after every panel, or the next panel would cover them
    for col, (title, steps) in enumerate(STAGES):
        out.append(f'<rect x="{panel_x(col)}" y="{MARGIN}" width="{PANEL_W}" height="{PANEL_BOTTOM - MARGIN}" rx="12" fill="{t["panel"]}" stroke="{t["panel_line"]}"/>')
        out.append(text(card_x(col), MARGIN + 28, title, t["text"], size=15, weight=600))
        for row, (role, name, detail, file_name) in enumerate(steps):
            x, y = card_x(col), card_y(row)
            fill, line = t[role]
            out.append(f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="8" fill="{fill}" stroke="{line}"/>')
            out.append(text(x + 14, y + 22, name, t["text"], size=14, weight=600))
            out.append(text(x + 14, y + 40, detail, t["muted"], size=12))
            out.append(text(x + 14, y + 57, file_name, t["muted"], size=11, family=MONO))
            out.append(text(x + CARD_W - 12, y + 57, TAGS[role], line, size=10, weight=600, anchor="end"))
            if row < ROWS - 1:
                cx = x + CARD_W // 2
                out.append(f'<path d="M{cx} {y + CARD_H} V{y + CARD_H + ROW_GAP - 2}" {arrow} marker-end="url(#head)"/>')
        if col < len(STAGES) - 1:
            # From the last card of this stage, up the gap, into the first card of the next stage.
            x0, x1 = card_x(col) + CARD_W, card_x(col + 1) - 2
            y0, y1 = card_y(ROWS - 1) + CARD_H // 2, card_y(0) + CARD_H // 2
            mid = panel_x(col) + PANEL_W + GAP // 2
            links.append(f'<path d="M{x0} {y0} H{mid} V{y1} H{x1}" {arrow} marker-end="url(#head)"/>')
    out += links

    redo =f'stroke="{t["you"][1]}" stroke-width="1.5" fill="none" stroke-dasharray="5 4" stroke-linecap="round" stroke-linejoin="round"'
    ear_x, ear_y = card_x(2), card_y(4)
    # Remix for free: from the ear back up to the mix.
    right = ear_x + CARD_W + 8
    out.append(f'<path d="M{ear_x + CARD_W} {ear_y + CARD_H // 2} H{right} V{card_y(1) + CARD_H // 2} H{ear_x + CARD_W + 2}" {redo} marker-end="url(#redo)"/>')
    # Regenerate, paid: from the ear under the panels and up into the generation step.
    gen_x, gen_y = card_x(1), card_y(3) + CARD_H // 2
    left = gen_x - 8
    ear_mid = ear_x + CARD_W // 2
    out.append(f'<path d="M{ear_mid} {ear_y + CARD_H} V{REDO_Y} H{left} V{gen_y} H{gen_x - 2}" {redo} marker-end="url(#redo)"/>')
    out[2] = out[2].replace("</defs>", f'<marker id="redo" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M2 1L8 5L2 9" fill="none" stroke="{t["you"][1]}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></marker></defs>')

    x = MARGIN
    for role, label, width in (("claude", "Claude decides", 118), ("script", "A script computes", 136), ("paid", "Paid, within your budget", 178), ("you", "Optional, by you", 128)):
        fill, line = t[role]
        out.append(f'<rect x="{x}" y="{LEGEND_Y - 11}" width="14" height="14" rx="3" fill="{fill}" stroke="{line}"/>')
        out.append(text(x + 20, LEGEND_Y, label, t["muted"]))
        x += width
    out.append(f'<path d="M{x} {LEGEND_Y - 4} H{x + 30}" {redo}/>')
    out.append(text(x + 38, LEGEND_Y, "Redo on request: a remix is free, a new block is paid", t["muted"]))
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    for theme in THEMES:
        with open(os.path.join(HERE, f"pipeline-{theme}.svg"), "w", encoding="utf-8") as f:
            f.write(draw(theme))


if __name__ == "__main__":
    main()
