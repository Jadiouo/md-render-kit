# md-render-kit

把一份 Markdown（含 LaTeX 數學、Mermaid 圖、程式碼、表格、任務清單）變成**單一檔案、可離線開啟的 HTML**，需要的話再印成 PDF。一個指令：

```bash
python mdrender.py notes.md --pdf
```

GitHub 上 Markdown 的預覽對數學和 Mermaid 支援不一，Marp / Typora 各有各的方言；這個小工具只做一件事：用 Pandoc 當解析器，把渲染需要的東西（樣式、MathJax、Mermaid.js、圖片）全部塞進同一個 HTML，讓它在任何瀏覽器都長一樣，也能可靠地印成 PDF。

## 流程

```
Markdown ─pandoc→ HTML ─post-process→ 自包含 HTML ─Playwright/Chromium→ PDF
                          │
                          ├ 注入 GitHub 風格 CSS（可用 --css 換掉）
                          ├ 注入 MathJax 3（SVG 輸出，PDF 不依賴網頁字型）
                          ├ 注入 Mermaid.js，並把 pandoc 產生的
                          │   <pre class="mermaid"> 修成 <div class="mermaid">
                          └ 本地圖片轉成 base64 內嵌
```

PDF 輸出會等 MathJax 排版完成、且每個 Mermaid 區塊都已被 `<svg>` 取代之後才列印，不是固定 sleep。

## 安裝

```bash
# 1. pandoc（https://pandoc.org/installing.html）
winget install JohnMacFarlane.Pandoc      # Windows
sudo apt install pandoc                    # Ubuntu
brew install pandoc                        # macOS

# 2. 只需要 HTML：不用裝任何 Python 套件
# 3. 需要 PDF：
pip install playwright && playwright install chromium
```

## 使用

```bash
python mdrender.py notes.md                              # 產生 notes.html
python mdrender.py notes.md -o out/notes.html --pdf      # HTML + PDF
python mdrender.py notes.md --title "標題" --css my.css   # 自訂標題與樣式
python mdrender.py notes.md --no-embed                   # 圖片保留連結不內嵌
cat notes.md | python mdrender.py - -o notes.html        # 讀 stdin
python mdrender.py notes.md --pandoc-arg=--toc           # 額外參數直接丟給 pandoc
```

支援的 Markdown：GFM（表格、刪除線、任務清單）+ `$...$` / `$$...$$` 數學 + ```` ```mermaid ```` 區塊 + 程式碼高亮（pygments 樣式）。

## 範例

`examples/constrained-optimization.md` 是一份「約束優化理論與機器學習」的學習筆記（拉格朗日乘子、KKT、對偶、SVM，含 4 張 Mermaid 流程圖與 CVXPY / scikit-learn 程式碼），用來測試所有語法。渲染結果在 `examples/output/`：

- [constrained-optimization.html](examples/output/constrained-optimization.html)
- [constrained-optimization.pdf](examples/output/constrained-optimization.pdf)

重新產生：

```bash
python mdrender.py examples/constrained-optimization.md -o examples/output/constrained-optimization.html --pdf
```

## 測試

```bash
pip install pytest
python -m pytest
```

測試會用一份小型 Markdown 跑完整流程，檢查 MathJax / Mermaid 注入、Mermaid 區塊轉換、圖片內嵌、任務清單與表格；沒有 pandoc 時自動略過。

## 授權

MIT
