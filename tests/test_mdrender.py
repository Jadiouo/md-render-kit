import base64
import shutil
from pathlib import Path

import pytest

import mdrender

pytestmark = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")

SAMPLE = """# Title

Inline $E = mc^2$ and display:

$$\\int_0^1 x\\,dx = \\tfrac12$$

```mermaid
graph LR
  A --> B
```

- [x] done
- [ ] todo

| a | b |
|---|---|
| 1 | 2 |

![pic](pic.png)
"""

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture
def rendered(tmp_path: Path) -> str:
    (tmp_path / "doc.md").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "pic.png").write_bytes(PNG_1PX)
    mdrender.main([str(tmp_path / "doc.md"), "-o", str(tmp_path / "out.html")])
    return (tmp_path / "out.html").read_text(encoding="utf-8")


def test_html_is_standalone_with_theme_and_libraries(rendered: str):
    assert rendered.lstrip().startswith("<!DOCTYPE html>")
    assert "<title>Title</title>" in rendered
    assert "<style>" in rendered and "max-width: 900px" in rendered
    assert "mathjax@3/es5/tex-svg.js" in rendered
    assert "mermaid.initialize" in rendered


def test_mermaid_block_becomes_div(rendered: str):
    assert '<div class="mermaid">' in rendered
    assert "graph LR" in rendered
    assert '<pre class="mermaid">' not in rendered


def test_math_kept_for_mathjax(rendered: str):
    assert 'class="math inline"' in rendered
    assert 'class="math display"' in rendered


def test_local_image_is_embedded(rendered: str):
    assert 'src="data:image/png;base64,' in rendered
    assert 'src="pic.png"' not in rendered


def test_task_list_and_table(rendered: str):
    assert 'type="checkbox"' in rendered
    assert "<table>" in rendered


def test_no_embed_flag_keeps_links(tmp_path: Path):
    (tmp_path / "doc.md").write_text(SAMPLE, encoding="utf-8")
    (tmp_path / "pic.png").write_bytes(PNG_1PX)
    mdrender.main([str(tmp_path / "doc.md"), "-o", str(tmp_path / "out.html"), "--no-embed"])
    assert 'src="pic.png"' in (tmp_path / "out.html").read_text(encoding="utf-8")
