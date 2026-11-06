"""Build one self-contained HTML page for choosing a voice per character by ear.

usage: build_audition_page.py CHARACTERS.json PREVIEWS_DIR OUT.html
"""
import base64
import html
import json
import os
import re
import sys

STYLE = """
:root { --bg:#faf9f6; --card:#fff; --ink:#1f1e1b; --muted:#6b6962; --line:#e3e0d8; --accent:#a8492b; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#1a1917; --card:#24231f; --ink:#ece9e1; --muted:#a19e95; --line:#3a3832; --accent:#e08a66; } }
:root[data-theme="dark"] { --bg:#1a1917; --card:#24231f; --ink:#ece9e1; --muted:#a19e95; --line:#3a3832; --accent:#e08a66; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
main { max-width:720px; margin:0 auto; padding:24px 16px 120px; }
h1 { font-size:24px; margin:0 0 6px; }
.lead { color:var(--muted); margin:0 0 24px; }
section { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:16px; }
h2 { font-size:18px; margin:0; }
.role { color:var(--muted); font-size:14px; margin:2px 0 8px; }
.line { font-size:14px; color:var(--muted); margin:0 0 12px; }
label { display:grid; grid-template-columns:auto 1.4em 1fr auto; gap:8px; align-items:center; padding:6px 0; cursor:pointer; }
label b { color:var(--accent); }
audio { width:100%; height:36px; min-width:0; }
.dur { font-size:13px; color:var(--muted); font-variant-numeric:tabular-nums; min-width:3em; text-align:right; }
.bar { position:fixed; left:0; right:0; bottom:0; background:var(--card); border-top:1px solid var(--line); padding:12px 16px; }
.bar div { max-width:720px; margin:0 auto; display:flex; gap:12px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
button { font:inherit; padding:6px 14px; border-radius:8px; border:1px solid var(--accent); background:transparent; color:var(--accent); cursor:pointer; }
"""

SCRIPT = """
const keys = [...document.querySelectorAll('section')].map(s => s.dataset.name);
function summary() {
  return [...document.querySelectorAll('section')].map(s => {
    const c = s.querySelector('input:checked');
    return s.dataset.name + ' ' + (c ? c.value : '?');
  }).join(', ');
}
function update() { document.getElementById('choice').textContent = summary(); }
document.addEventListener('change', update);
document.getElementById('copy').addEventListener('click', async e => {
  try { await navigator.clipboard.writeText(summary()); e.target.textContent = 'Скопировано'; }
  catch (_) { e.target.textContent = 'Выдели текст слева'; }
});
document.querySelectorAll('audio').forEach(a => {
  const show = () => { a.closest('label').querySelector('.dur').textContent = a.duration.toFixed(1) + ' с'; };
  if (a.readyState >= 1) show(); else a.addEventListener('loadedmetadata', show);
  a.addEventListener('play', () => document.querySelectorAll('audio').forEach(o => { if (o !== a) o.pause(); }));
});
update();
"""


def main():
    cfg = json.load(open(sys.argv[1]))
    previews_dir, out = sys.argv[2], sys.argv[3]
    parts = []
    for c in cfg["characters"]:
        meta = json.load(open(os.path.join(previews_dir, f"{c['key']}.json")))
        spoken = re.sub(r"\[[^\]]*\]\s*", "", c["text"])
        rows = []
        for p in meta["previews"]:
            data = base64.b64encode(open(os.path.join(previews_dir, p["file"]), "rb").read()).decode()
            rows.append(
                f'<label><input type="radio" name="{c["key"]}" value="{p["letter"]}">'
                f'<b>{p["letter"]}</b>'
                f'<audio controls preload="metadata" src="data:audio/mpeg;base64,{data}"></audio>'
                f'<span class="dur"></span></label>'
            )
        parts.append(
            f'<section data-name="{html.escape(c["name"])}"><h2>{html.escape(c["name"])}</h2>'
            f'<p class="role">{html.escape(c["role"])}</p>'
            f'<p class="line">{html.escape(spoken)}</p>{"".join(rows)}</section>'
        )
    page = (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Голоса {html.escape(cfg.get('project', ''))}</title><style>{STYLE}</style></head><body><main>"
        "<h1>Голоса персонажей</h1>"
        '<p class="lead">У каждого персонажа три варианта с одним и тем же текстом. '
        "Отметь лучший, потом пришли мне строку снизу.</p>"
        + "".join(parts)
        + '</main><div class="bar"><div><span id="choice"></span><button id="copy" type="button">Скопировать</button></div></div>'
        f"<script>{SCRIPT}</script></body></html>"
    )
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"{out}: {len(page) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
