"""Save manuscript versions and review their resolved content in a local HTML file."""
from __future__ import annotations

import argparse
import base64
from difflib import SequenceMatcher
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import sys
import subprocess
import tempfile
from urllib.parse import unquote

from atomic_io import write_text
from manuscript_snapshot import validate

ROOT = Path(__file__).resolve().parent.parent


def make_document(folder: Path) -> dict:
    """Read the Word projection structurally, including tables, math and citations.

    One Pandoc tree, however many reference lists the manuscript sets: the
    Supporting Information carries its own, and citeproc produces one list
    per run. export_docx.document does the splitting, so a review diff sees
    the same structure the Word export ships.
    """
    from export_docx import document
    return document((folder / "paper.word.typ").read_text(), folder,
                    note=lambda msg: print(msg.replace(
                        "citations use pandoc's default style",
                        "review uses pandoc's default style")))


def image_path(folder: Path, name: str) -> Path:
    path = (folder / unquote(name).lstrip("/")).resolve()
    if not path.is_relative_to(folder.resolve()) or not path.is_file():
        raise ValueError(f"image is outside or missing from snapshot: {name}")
    return path


def canonical(value, folder: Path):
    """Ignore soft wrapping and citation numbering, retain actual citation IDs."""
    if isinstance(value, list):
        return [canonical(v, folder) for v in value]
    if not isinstance(value, dict):
        return value
    if value.get("t") == "SoftBreak":
        return {"t": "Space"}
    if value.get("t") == "Cite":
        return {"t": "Cite", "c": canonical([
            {k: v for k, v in cite.items() if k not in ("citationHash", "citationNoteNum")}
            for cite in value["c"][0]], folder)}
    if value.get("t") == "Image":
        copy = json.loads(json.dumps(value))
        target = copy["c"][-1]
        target[0] = hashlib.sha256(image_path(folder, target[0]).read_bytes()).hexdigest()
        return copy
    return {k: canonical(v, folder) for k, v in value.items()}


def embed_images(value, folder: Path):
    if isinstance(value, list):
        return [embed_images(v, folder) for v in value]
    if not isinstance(value, dict):
        return value
    if value.get("t") in ("RawBlock", "RawInline"):
        # A report is a document, never a way to run embedded manuscript HTML.
        return {"t": "CodeBlock", "c": [["", [], []], value["c"][1]]} if value["t"] == "RawBlock" else {
            "t": "Code", "c": [["", [], []], value["c"][1]]}
    result = {k: embed_images(v, folder) for k, v in value.items()}
    if result.get("t") == "Image":
        target = result["c"][-1]
        path = image_path(folder, target[0])
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        target[0] = f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()
    return result


def render(blocks: list, document: dict, folder: Path) -> list[str]:
    """Render all blocks in one Pandoc call and keep their structural boundaries."""
    import pypandoc
    wrapped = []
    for i, block in enumerate(blocks):
        wrapped.extend([
            {"t": "RawBlock", "c": ["html", f"<!--review-block-{i}-->"]},
            embed_images(block, folder),
            {"t": "RawBlock", "c": ["html", "<!--/review-block-->"]},
        ])
    doc = {**document, "blocks": wrapped}
    html = pypandoc.convert_text(json.dumps(doc), "html5", format="json", extra_args=["--mathml"])
    parts = re.findall(r"<!--review-block-(\d+)-->(.*?)<!--/review-block-->", html, re.S)
    if [int(i) for i, _ in parts] != list(range(len(blocks))):
        raise ValueError("could not preserve review block boundaries")
    return [content.strip() for _, content in parts]


class Words(HTMLParser):
    """Highlight text nodes without damaging tables, links or MathML markup."""
    def __init__(self, marked=(), css=""):
        super().__init__(convert_charrefs=True)
        self.marked, self.css = set(marked), css
        self.words, self.output = [], []
        self.math_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "math":
            self.math_depth += 1
        self.output.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.output.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        self.output.append(f"</{tag}>")
        if tag == "math":
            self.math_depth -= 1

    def handle_data(self, data):
        for token in re.findall(r"\s+|[+−-]?\d+(?:[.,]\d+)*(?:[eE][+−-]?\d+)?|\w+(?:[’']\w+)*|[^\w\s]", data):
            word = not token.isspace()
            selected = word and len(self.words) in self.marked
            # Do not insert HTML elements into MathML. Equations remain visible
            # in the before/after block and the block is marked as changed.
            self.output.append(f'<mark class="{self.css}">{escape(token)}</mark>'
                               if selected and not self.math_depth else escape(token))
            if word:
                self.words.append(token)


def highlight(old: str, new: str) -> tuple[str, str]:
    left, right = Words(), Words()
    left.feed(old)
    right.feed(new)
    removed, added = set(), set()
    for op, a, b, c, d in SequenceMatcher(None, left.words, right.words, autojunk=False).get_opcodes():
        if op != "equal":
            removed.update(range(a, b))
            added.update(range(c, d))
    left, right = Words(removed, "removed"), Words(added, "added")
    left.feed(old)
    right.feed(new)
    return "".join(left.output), "".join(right.output)


STYLE = """
:root{font-family:system-ui,sans-serif;color:#26352f;background:#f4f5f1;--line:#dce2dc;--ink:#214c3d;--header:155px}
*{box-sizing:border-box}html{overflow-anchor:none}body{margin:0}button,select,input{font:inherit}button,select{border:1px solid #bac8bf;border-radius:7px;background:#fff;color:var(--ink);padding:8px 12px}
button{cursor:pointer}button:disabled{opacity:.4;cursor:default}a{color:var(--ink)}:focus-visible{outline:3px solid #387bba;outline-offset:3px}
header{position:sticky;top:0;z-index:3;background:#fffffff5;backdrop-filter:blur(12px);border-bottom:1px solid var(--line);padding:18px 28px}
.topline,.toolbar,.bar{display:flex;align-items:center;justify-content:space-between;gap:16px}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:11px;color:#60766a;font-weight:700}
h1{font-size:23px;letter-spacing:-.03em;margin:2px 0 4px}.comparison{font-size:13px;color:#637369;overflow-wrap:anywhere}.summary{font-size:13px;color:#52665a;text-align:right}.toolbar{justify-content:flex-start;flex-wrap:wrap;margin-top:16px;font-size:13px}.nav-controls{display:flex;align-items:center;gap:8px}#position{min-width:94px;text-align:center;font-variant-numeric:tabular-nums}
.legend{margin-left:auto;color:#637369;display:flex;gap:14px;font-size:12px}.legend span{padding:3px 7px;border-radius:3px}.legend .added{background:#d7eee2;border-bottom:2px solid #528567}.legend .removed{background:#f8e1df;text-decoration:line-through}
.layout{max-width:1700px;margin:auto;display:grid;grid-template-columns:250px minmax(0,1fr);gap:28px;padding:24px 28px}.layout.no-changes{grid-template-columns:1fr}
aside{position:sticky;top:calc(var(--header) + 18px);align-self:start;max-height:calc(100vh - var(--header) - 40px);overflow:auto;padding:6px 3px}
aside h2{font-size:12px;letter-spacing:.08em;text-transform:uppercase;margin:0 0 16px;color:#627569}.change-link{display:block;position:relative;text-decoration:none;padding:12px 12px 12px 34px;border-radius:8px;border:1px solid transparent;margin-bottom:5px;font-size:13px;line-height:1.45}
.change-link:before{content:attr(data-number);position:absolute;left:10px;top:13px;color:#7a8c80;font-size:11px}.change-link small{display:block;margin-top:5px;color:#738477}.change-link[aria-current=true]{background:white;border-color:#c5d7ca;box-shadow:0 2px 5px #19392b06}
.help{font-size:12px;color:#78867e;line-height:1.7;margin:20px 10px}kbd{font:11px system-ui;border:1px solid var(--line);padding:1px 4px;border-radius:3px;background:#fff}
main{min-width:0}article{background:#fff;border:1px solid var(--line);border-radius:10px;margin:0 0 24px;scroll-margin-top:calc(var(--header) + 18px);overflow:hidden}
article.active{border-color:#89a992;box-shadow:0 0 0 1px #89a992}.bar{padding:13px 20px;background:#edf2ec;border-bottom:1px solid var(--line);font-size:12px}.bar strong{display:block;font-size:13px;font-weight:600;margin-bottom:4px}.bar .kind{color:#65766b}
.unchanged .columns{grid-template-columns:1fr}.unchanged .pane{max-width:85ch;margin:auto;width:100%}
.columns{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.pane{padding:18px 24px 22px;overflow:auto;min-width:0;font:17px/1.75 Georgia,'Times New Roman',serif}.pane+.pane{border-left:1px solid var(--line)}.version{font:600 11px/1.5 system-ui;text-transform:uppercase;letter-spacing:.09em;color:#7a857c;margin-bottom:14px}
.pane p{margin:0 0 1em}.pane p:last-child{margin-bottom:0}.pane h1,.pane h2,.pane h3,.pane h4{font-family:system-ui;line-height:1.4;letter-spacing:normal}.pane h1{font-size:21px}.pane h2{font-size:19px}.pane h3,.pane h4{font-size:17px}
.pane img{display:block;max-width:100%;max-height:600px;object-fit:contain}.pane table{border-collapse:collapse;width:100%;font:13px/1.5 system-ui}.pane td,.pane th{padding:7px;border:1px solid var(--line)}.pane th{background:#f4f6f2}
mark.added{background:#d7eee2;color:#16442b;box-shadow:0 1px 0 #528567}mark.removed{background:#f8e1df;color:#8b3431;text-decoration:line-through}mark{border-radius:2px;padding:1px 0;box-decoration-break:clone}
.absent{color:#7b887e;font-style:italic}.only-changes .unchanged,.content-only [data-display=true]{display:none}[hidden]{display:none!important}.empty{padding:55px 28px;background:#fff;border:1px solid var(--line);border-radius:10px;text-align:center}.empty h2{font-size:21px;margin:0 0 10px}.empty p{color:#617366;margin:0;line-height:1.6}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{font-size:.88em}math{max-width:100%;overflow:auto}footer{padding:8px 0 25px;font-size:12px;color:#77847c;line-height:1.6}.no-script{padding:12px 28px;background:#fff4d8}
@media(min-width:1400px){.pane{font-size:18px;padding:22px 30px}}
@media(max-width:1050px){.layout{grid-template-columns:195px minmax(0,1fr);gap:18px;padding:18px}.pane{padding:16px;font-size:16px}.legend{margin-left:0}}
@media(max-width:800px){header{padding:14px 16px}.topline{align-items:flex-start}.summary{max-width:160px;font-size:12px}.layout{display:block;padding:16px}aside{position:static;max-height:180px;margin-bottom:18px}.help{display:none}.columns{grid-template-columns:1fr}.pane+.pane{border-left:0;border-top:1px solid var(--line)}.bar{padding:12px;gap:10px}.legend{display:none}.toolbar{gap:10px}.comparison{max-width:230px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
@media print{header,aside,footer{display:none}.layout{display:block;padding:0}.unchanged{display:none}article{break-inside:avoid}.pane{font-size:11pt}article[hidden]{display:block!important}}
"""

SCRIPT = r"""
const cards=[...document.querySelectorAll('article.changed')];
const links=[...document.querySelectorAll('.change-link')];
const filter=document.getElementById('filter');
const previous=document.getElementById('previous'),next=document.getElementById('next');
let current=null;
function visible(){return cards.filter(c=>!c.hidden);}
function setCurrent(card){
  current=card;
  cards.forEach(c=>c.classList.toggle('active',c===card));
  links.forEach(a=>a.setAttribute('aria-current',String(card?.id===a.hash.slice(1))));
  const list=visible(),index=list.indexOf(card);
  document.getElementById('position').textContent=index<0?'No edits':`Edit ${index+1} of ${list.length}`;
  previous.disabled=index<=0;next.disabled=index<0||index===list.length-1;
}
function go(card){if(!card)return;setCurrent(card);card.scrollIntoView({block:'start'});}
function refresh(){
  document.body.classList.toggle('only-changes',filter.value!=='all');
  document.body.classList.toggle('content-only',filter.value==='content');
  cards.forEach(c=>{c.hidden=filter.value==='content'&&c.dataset.display==='true';});
  links.forEach(a=>{a.hidden=filter.value==='content'&&a.dataset.display==='true';});
  document.getElementById('display-only').hidden=!(cards.length&&visible().length===0);
  setCurrent(current&&!current.hidden?current:visible()[0]||null);
}
function move(step){const list=visible(),index=list.indexOf(current);go(list[index+step]);}
previous.onclick=()=>move(-1);next.onclick=()=>move(1);
filter.onchange=()=>{refresh();const target=current;requestAnimationFrame(()=>go(target));};
links.forEach(a=>a.onclick=e=>{e.preventDefault();go(document.getElementById(a.hash.slice(1)));});
document.addEventListener('keydown',e=>{
  if(e.altKey||e.ctrlKey||e.metaKey||e.target.closest('input,select,textarea,button,a,[contenteditable=true]'))return;
  if(e.key==='j'||e.key==='k'){e.preventDefault();move(e.key==='j'?1:-1);}
});
const header=document.querySelector('header');
new ResizeObserver(()=>document.documentElement.style.setProperty('--header',header.offsetHeight+'px')).observe(header);
cards.forEach(c=>c.addEventListener('pointerdown',()=>setCurrent(c)));
refresh();
"""


def section_labels(blocks: list, rendered: list[str]) -> list[str]:
    """Locate each passage in the manuscript, including removed passages."""
    headings, labels = [], []
    for block, html in zip(blocks, rendered):
        if block.get("t") == "Header":
            level = block["c"][0]
            # Use the actual heading's text, without interpreting its numbering.
            title = re.sub(r"\s+", " ", "".join(_text_nodes(html))).strip()
            headings = [(depth, name) for depth, name in headings if depth < level]
            headings.append((level, title))
        labels.append(" › ".join(title for _, title in headings) or "Front matter")
    return labels


def _text_nodes(html: str) -> list[str]:
    class Text(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []

        def handle_data(self, text):
            self.parts.append(text)
    reader = Text()
    reader.feed(html)
    return reader.parts


def report(old: Path, new: Path, old_name: str, new_name: str) -> tuple[str, int]:
    validate(old)
    validate(new)
    docs = [json.loads((p / "document.json").read_text()) for p in (old, new)]
    blocks = [doc["blocks"] for doc in docs]
    keys = [[json.dumps(canonical(b, folder), sort_keys=True, ensure_ascii=False)
             for b in bs] for bs, folder in zip(blocks, (old, new))]
    rendered = [render(bs, doc, folder) for bs, doc, folder in zip(blocks, docs, (old, new))]
    sections = [section_labels(bs, html) for bs, html in zip(blocks, rendered)]
    rows, navigation, changes, display_changes = [], [], 0, 0
    for op, a, b, c, d in SequenceMatcher(None, *keys, autojunk=False).get_opcodes():
        # Unmatched groups stay together; position alone does not establish a match.
        pairs = [(a + i, a + i + 1, c + i, c + i + 1) for i in range(b - a)] if op == "equal" else [(a, b, c, d)]
        for x, y, z, w in pairs:
            left, right = "\n".join(rendered[0][x:y]), "\n".join(rendered[1][z:w])
            changed = op != "equal" or left != right
            section = sections[1][z] if z < w else sections[0][x]
            display_only = changed and op == "equal"
            if display_only:
                display_changes += 1
            if changed:
                changes += 1
                left, right = highlight(left, right)
            label = ("Display / numbering changed" if op == "equal" else
                     {"replace": "Edited", "delete": "Removed", "insert": "Added"}.get(op, "Unchanged")) if changed else "Unchanged"
            anchor = f' id="change-{changes}"' if changed else ""
            cls = "changed" if changed else "unchanged"
            if changed:
                navigation.append(f'<a class="change-link" data-number="{changes}" data-display="{str(display_only).lower()}" href="#change-{changes}">'
                                  f'{escape(section)}<small>{label}</small></a>')
            if not changed:
                rows.append(f'<article class="unchanged"><div class="columns"><div class="pane">{right}</div></div></article>')
                continue
            rows.append(f'<article class="{cls}" data-display="{str(display_only).lower()}"{anchor}><div class="bar"><div><strong>{escape(section)}</strong>'
                        f'<span class="kind">{label}{f" · Change {changes}" if changed else ""}</span></div></div><div class="columns">'
                        f'<div class="pane"><div class="version">Before · {escape(old_name)}</div>{left or "<p class=absent>No content here.</p>"}</div>'
                        f'<div class="pane"><div class="version">After · {escape(new_name)}</div>{right or "<p class=absent>No content here.</p>"}</div></div></article>')
    content_changes = changes - display_changes
    summary = f"{content_changes} content edit{'s' if content_changes != 1 else ''}"
    if display_changes:
        summary += f" · {display_changes} display / numbering change{'s' if display_changes != 1 else ''}"
    nav = (f'<aside aria-label="Changed passages"><h2>Where to look</h2>'
           + ''.join(navigation) + '<div class="help"><kbd>J</kbd> next · <kbd>K</kbd> previous</div></aside>') if changes else ''
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'nonce-review'; base-uri 'none'">
<title>Manuscript changes: {escape(old_name)} to {escape(new_name)}</title><style>{STYLE}</style></head>
<body class="only-changes content-only"><header><div class="topline"><div><div class="eyebrow">Manuscript review</div><h1>Review what changed</h1>
<div class="comparison">{escape(old_name)} → {escape(new_name)}</div></div>
<div class="summary">{summary}</div></div>
<div class="toolbar"><div class="nav-controls"><button id="previous" disabled aria-label="Previous change">← Previous</button><span id="position" role="status">{content_changes} edits</span><button id="next" disabled aria-label="Next change">Next →</button></div>
<label>Show <select id="filter"><option value="content">Content edits</option><option value="changes">All changes</option><option value="all">Full paper</option></select></label>
<div class="legend"><span class="removed">Removed</span><span class="added">Added</span></div></div></header>
<noscript><style>.content-only [data-display=true]{{display:block}}</style><div class="no-script">Use the section links to read each change. Enable JavaScript for navigation and filters.</div></noscript>
<div class="layout{' no-changes' if not changes else ''}">{nav}<main>
{'<div class="empty"><h2>No content changes</h2><p>These versions match. Choose Full paper to read the manuscript.</p></div>' if not changes else ''}
<div id="display-only" class="empty" hidden><h2>No content edits</h2><p>Only display or numbering changed. Choose All changes to inspect those differences.</p></div>
{''.join(rows)}<footer>Numbers, tables, figures, equations, and references are included. Layout and source-code changes are outside this report.</footer></main></div>
<script nonce="review">{SCRIPT}</script></body></html>'''
    return html, changes


def version_path(root: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name) or name == "current":
        raise ValueError("version names use letters, digits, dots, hyphens or underscores; 'current' is reserved")
    return root / ".review" / "versions" / name


def current_snapshot(root: Path) -> Path:
    from build_state import build
    build("resolve", root)
    pointer = json.loads((root / ".build-state/manuscript.json").read_text())
    return root / pointer["path"]


def save(root: Path, name: str) -> Path:
    from build_state import build_lock
    destination = version_path(root, name)
    if destination.exists():
        raise ValueError(f"version {name!r} already exists; choose a new name")
    source = current_snapshot(root)
    with build_lock(root):
        validate(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
            staged = Path(tmp) / "version"
            shutil.copytree(source, staged)
            if destination.exists():
                raise ValueError(f"version {name!r} already exists")
            os.rename(staged, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("baseline", "compare", "versions"))
    parser.add_argument("baseline", nargs="?")
    parser.add_argument("new", nargs="?", default="current")
    args = parser.parse_args()
    if args.command != "versions" and not args.baseline:
        parser.error("a version name is required; list saved names with: just review-versions")
    try:
        if args.command == "versions":
            names = sorted(p.name for p in (ROOT / ".review/versions").glob("*")
                           if p.is_dir() and (p / "manifest.json").is_file())
            print("Saved review versions:\n" + "\n".join(f"  {name}" for name in names)
                  if names else "No saved versions. Start with: just review-baseline reviewed")
        elif args.command == "baseline":
            path = save(ROOT, args.baseline)
            print(f"Saved {args.baseline}: {path}")
        else:
            old = version_path(ROOT, args.baseline)
            if not old.is_dir():
                raise ValueError(f"no saved version {args.baseline!r}; use just review-versions to list names")
            validate(old)  # Fail before rebuilding if the requested baseline is absent/broken.
            new = current_snapshot(ROOT) if args.new == "current" else version_path(ROOT, args.new)
            html, count = report(old, new, args.baseline, args.new)
            output = ROOT / ".review/review.html"
            write_text(output, html)
            print(f"{count} changed passage(s): {output}")
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"review failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
