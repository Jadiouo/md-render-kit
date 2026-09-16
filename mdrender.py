#!/usr/bin/env python3
"""mdrender - render Markdown (math + Mermaid + code) to a self-contained HTML page, optionally PDF.

Pipeline
    pandoc  ->  post-process (CSS, MathJax, Mermaid, base64 images)  ->  [Playwright/Chromium -> PDF]

Examples
    python mdrender.py notes.md                      # notes.html next to the source
    python mdrender.py notes.md -o out/notes.html --pdf
    python mdrender.py notes.md --title "My notes" --css my.css
    cat notes.md | python mdrender.py - -o notes.html

Requires pandoc on PATH; PDF export additionally needs `pip install playwright`
and `playwright install chromium`.
"""
from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_CSS = """\
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial,
                 "Noto Sans CJK TC", "Microsoft JhengHei", sans-serif;
    max-width: 900px; margin: 2em auto; padding: 0 2em;
    line-height: 1.8; color: #24292e; background: #fff;
}
h1 { font-size: 2em; border-bottom: 2px solid #0366d6; padding-bottom: 0.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: 0.3em; margin-top: 2em; }
h3 { font-size: 1.25em; margin-top: 1.5em; }
blockquote { border-left: 4px solid #0366d6; padding: 0.5em 1em; margin: 1em 0; background: #f1f8ff; }
table { border-collapse: collapse; width: 100%; margin: 1em 0; }
th, td { border: 1px solid #dfe2e5; padding: 8px 12px; text-align: left; }
th { background: #f6f8fa; font-weight: 600; }
tr:nth-child(even) { background: #f9f9f9; }
code { background: #f6f8fa; padding: 0.2em 0.4em; border-radius: 3px; font-size: 0.9em;
       font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace; }
pre { background: #282c34; color: #abb2bf; padding: 1em 1.5em; border-radius: 6px; overflow-x: auto; line-height: 1.5; }
pre code { background: none; padding: 0; color: inherit; }
hr { border: none; border-top: 2px solid #eaecef; margin: 2em 0; }
a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }
img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
ul, ol { padding-left: 2em; }
input[type="checkbox"] { margin-right: 0.5em; }
.mermaid { background: #fff; text-align: center; margin: 1.5em 0; }
del { color: #999; }
@media print { body { max-width: none; margin: 0; padding: 0; } pre { white-space: pre-wrap; } }
"""

MATHJAX = """\
<script>
MathJax = { tex: { inlineMath: [['$', '$'], ['\\\\(', '\\\\)']] },
            startup: { typeset: true } };
</script>
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
"""

MERMAID = """\
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>mermaid.initialize({ startOnLoad: true });</script>
"""


# --------------------------------------------------------------------------
def run_pandoc(source: str, title: str | None, extra_args: list[str]) -> str:
    """Convert Markdown text to a standalone HTML document with pandoc."""
    if shutil.which("pandoc") is None:
        sys.exit("error: pandoc not found on PATH (https://pandoc.org/installing.html)")
    cmd = ["pandoc", "--from", "gfm+tex_math_dollars+task_lists+strikeout", "--to", "html5",
           "--standalone", "--highlight-style=pygments"]
    if title:
        cmd += ["--metadata", f"title={title}"]
    cmd += extra_args
    proc = subprocess.run(cmd, input=source.encode("utf-8"), capture_output=True)
    if proc.returncode != 0:
        sys.exit(f"pandoc failed:\n{proc.stderr.decode('utf-8', 'replace')}")
    return proc.stdout.decode("utf-8")


def fix_mermaid_blocks(doc: str) -> str:
    """pandoc emits <pre class="mermaid"><code>...</code></pre>; mermaid.js wants <div class="mermaid">."""
    def repl(m: re.Match) -> str:
        return '<div class="mermaid">\n' + html.unescape(m.group(1)) + "\n</div>"
    # pandoc wraps fenced blocks with a language as <pre class="mermaid"><code class="...">
    return re.sub(r'<pre class="mermaid"><code[^>]*>(.*?)</code></pre>', repl, doc, flags=re.DOTALL)


def embed_images(doc: str, base_dir: Path) -> str:
    """Inline local <img src> files as base64 data URIs so the HTML is self-contained."""
    def repl(m: re.Match) -> str:
        tag, src = m.group(0), m.group(1)
        if re.match(r"^(https?:|data:)", src):
            return tag
        path = (base_dir / src).resolve()
        if not path.is_file():
            print(f"warning: image not found, left as-is: {src}", file=sys.stderr)
            return tag
        mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        return tag.replace(f'src="{src}"', f'src="data:{mime};base64,{b64}"')
    return re.sub(r'<img\b[^>]*\bsrc="([^"]+)"[^>]*>', repl, doc)


def postprocess(doc: str, base_dir: Path, css: str, embed: bool) -> str:
    head_inject = f"<style>\n{css}</style>\n" + MATHJAX
    doc = doc.replace("</head>", head_inject + "</head>", 1)
    doc = doc.replace("</body>", MERMAID + "</body>", 1)
    doc = fix_mermaid_blocks(doc)
    if embed:
        doc = embed_images(doc, base_dir)
    return doc


def html_to_pdf(html_path: Path, pdf_path: Path, timeout_ms: int = 30000) -> None:
    """Print the rendered page with headless Chromium once MathJax and Mermaid have finished."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("error: PDF export needs Playwright: pip install playwright && playwright install chromium")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
        # MathJax: wait for the initial typeset; Mermaid: every diagram has been replaced by an <svg>
        page.evaluate("() => (window.MathJax && MathJax.startup) ? MathJax.startup.promise.then(() => true) : true")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('.mermaid')).every(e => e.querySelector('svg'))",
            timeout=timeout_ms)
        page.pdf(path=str(pdf_path), format="A4",
                 margin={"top": "2cm", "bottom": "2cm", "left": "2cm", "right": "2cm"},
                 print_background=True)
        browser.close()


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="mdrender", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="Markdown file, or - for stdin")
    ap.add_argument("-o", "--output", help="output HTML path (default: <source>.html)")
    ap.add_argument("--pdf", action="store_true", help="also export a PDF next to the HTML")
    ap.add_argument("--title", help="document title (default: from the first H1 / front matter)")
    ap.add_argument("--css", help="use this CSS file instead of the built-in GitHub-like theme")
    ap.add_argument("--no-embed", action="store_true", help="keep image links instead of inlining base64")
    ap.add_argument("--pandoc-arg", action="append", default=[], metavar="ARG",
                    help="extra argument passed straight to pandoc (repeatable)")
    args = ap.parse_args(argv)

    if args.source == "-":
        text, base_dir = sys.stdin.read(), Path.cwd()
        out = Path(args.output) if args.output else Path("output.html")
    else:
        src = Path(args.source)
        if not src.is_file():
            sys.exit(f"error: {src} not found")
        text, base_dir = src.read_text(encoding="utf-8"), src.parent
        out = Path(args.output) if args.output else src.with_suffix(".html")

    title = args.title
    if not title:
        m = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
        title = m.group(1) if m else out.stem

    css = Path(args.css).read_text(encoding="utf-8") if args.css else DEFAULT_CSS
    doc = postprocess(run_pandoc(text, title, args.pandoc_arg), base_dir, css, embed=not args.no_embed)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}")
    if args.pdf:
        pdf = out.with_suffix(".pdf")
        html_to_pdf(out, pdf)
        print(f"wrote {pdf}")


if __name__ == "__main__":
    main()
