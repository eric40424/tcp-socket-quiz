#!/usr/bin/env python3
"""把專案裡的 Markdown 文件打包成一個可以離線瀏覽的 docs.html。

用法: python3 scripts/build_docs.py
產生的 docs.html 已內嵌所有文件與 JS 函式庫 (marked、highlight.js)，直接用瀏覽器開啟即可。
修改任何 .md 之後重跑一次就會更新。
"""
import datetime
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
OUT = ROOT / "docs.html"

# (分組名稱, 檔案清單, 是否為解答 — 解答需要點擊確認才會顯示)
SECTIONS = [
    ("總覽", ["README.md", "EXAM.md"], False),
    ("教材", ["materials/README.md"] + sorted(
        p.relative_to(ROOT).as_posix() for p in (ROOT / "materials").glob("0*.md")
    ), False),
    ("考後", ["solutions/README.md"], True),
]


def title_of(md, fallback):
    m = re.search(r"^#\s+(.+)$", md, re.MULTILINE)
    return m.group(1).strip() if m else fallback


def script_safe(js):
    """讓內容可以安全地放進 <script> 裡 (避免提早結束 script 標籤)。"""
    return re.sub(r"</(script)", r"<\\/\1", js, flags=re.IGNORECASE).replace("<!--", "<\\!--")


def main():
    docs = []
    for group, files, spoiler in SECTIONS:
        for rel in files:
            md = (ROOT / rel).read_text(encoding="utf-8")
            docs.append({
                "path": rel,
                "title": title_of(md, rel),
                "group": group,
                "spoiler": spoiler,
                "md": md,
            })

    html = (DOCS_DIR / "template.html").read_text(encoding="utf-8")
    replacements = {
        "/*__MARKED__*/": script_safe((DOCS_DIR / "vendor" / "marked.min.js").read_text(encoding="utf-8")),
        "/*__HLJS__*/": script_safe((DOCS_DIR / "vendor" / "highlight.min.js").read_text(encoding="utf-8")),
        "/*__DOCS__*/": script_safe(json.dumps(docs, ensure_ascii=False)),
        "__BUILD_TIME__": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)

    OUT.write_text(html, encoding="utf-8", newline="\n")
    print(f"已產生 {OUT.relative_to(ROOT)} ({len(docs)} 份文件, {len(html) // 1024} KB)")
    for d in docs:
        print(f"  [{d['group']}] {d['title']}")


if __name__ == "__main__":
    main()
