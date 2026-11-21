r"""导出：单篇 PDF、整天 ZIP、全部 ZIP（压缩包里也是 PDF）。纯标准库。

PDF 靠系统自带的 Edge / Chrome 无头打印生成——排版和你在阅读器里看到的一致，
不需要装 reportlab / weasyprint 这类依赖。
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from generator import norm, word_forms
from render import render_article

_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")

# 打印样式改了就 +1，旧缓存自动失效
PRINT_VERSION = "1"


class ExportError(RuntimeError):
    pass


# ---------------------------------------------------------------- 浏览器

def find_browser() -> str | None:
    """找一个能无头打印 PDF 的 Chromium 内核浏览器。"""
    env = (os.environ.get("MOMO_BROWSER") or "").strip()
    cands: list[str] = [env] if env else []
    cands += [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for c in cands:
        if c and Path(c).exists():
            return c
    for name in ("msedge", "chrome", "chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def html_to_pdf(html: str, out: Path) -> None:
    browser = find_browser()
    if not browser:
        raise ExportError("没找到 Edge / Chrome，无法生成 PDF。"
                          "装一个浏览器，或设置 MOMO_BROWSER 指向它。")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "article.html"
        src.write_text(html, encoding="utf-8")
        cmd = [
            browser,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-pdf-header-footer",
            f"--user-data-dir={Path(td) / 'profile'}",
            "--virtual-time-budget=3000",
            f"--print-to-pdf={out}",
            src.as_uri(),
        ]
        try:
            subprocess.run(cmd, check=True, timeout=90,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            raise ExportError("生成 PDF 超时（浏览器没响应）") from exc
        except subprocess.CalledProcessError as exc:
            raise ExportError(f"生成 PDF 失败：浏览器返回 {exc.returncode}") from exc
    if not out.exists() or out.stat().st_size < 800:
        raise ExportError("生成的 PDF 是空的，检查一下浏览器是否可用")


def slug(title: str, fallback: str = "article") -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "").lower()).strip("-")
    return s[:60] or fallback


def _form_map(article: dict) -> dict[str, str]:
    fm: dict[str, str] = {}
    for u in article.get("used") or []:
        t = norm(u.get("target") or "")
        if not t:
            continue
        for f in {norm(u.get("form") or ""), t}:
            if f:
                fm[f] = t
    for t in article.get("targets") or []:
        for f in word_forms(t):
            fm.setdefault(f, norm(t))
    return fm


def _md_body(paragraphs: list[str], form_map: dict[str, str], targets: set[str]) -> str:
    def repl(m: re.Match) -> str:
        w = m.group(0)
        key = form_map.get(w.lower())
        return f"**{w}**" if key and key in targets else w

    return "\n\n".join(_WORD.sub(repl, p) for p in paragraphs or [])


def _yaml(value) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def article_markdown(article: dict, day: str, meta: dict | None = None) -> str:
    meta = meta or {}
    targets = article.get("targets") or []
    target_set = {norm(t) for t in targets}
    gloss = article.get("glosses") or {}
    stats = article.get("stats") or {}
    missing = stats.get("missing") or []
    coverage = stats.get("coverage")

    out: list[str] = [
        "---",
        "generator: momo-daily",
        f"date: {day}",
        f"title: {_yaml(article.get('title'))}",
        f"title_cn: {_yaml(article.get('title_cn'))}",
        f"logline: {_yaml(article.get('logline'))}",
        f"model: {_yaml(meta.get('model'))}",
        f"targets: {len(targets)}",
        f"words: {stats.get('words') or 0}",
        f"coverage: {round(coverage, 3) if isinstance(coverage, (int, float)) else 0}",
        "tags:",
        "  - momo-daily",
        f"  - {day}",
    ]
    if missing:
        out.append("missing: [" + ", ".join(_yaml(m) for m in missing) + "]")
    out.append("---")
    out.append("")

    out.append(f"# {article.get('title') or 'Untitled'}")
    if article.get("title_cn"):
        out.append(f"> {article['title_cn']}")
    bits = [day, f"{len(targets)} 个目标词"]
    if stats.get("words"):
        bits.append(f"{stats['words']} 词")
    if isinstance(coverage, (int, float)):
        bits.append(f"覆盖 {coverage:.0%}")
    out.append("> " + " · ".join(bits))
    if article.get("logline"):
        out.append("")
        out.append(article["logline"])
    out.append("")
    out.append("---")
    out.append("")
    out.append(_md_body(article.get("paragraphs") or [], _form_map(article), target_set))

    if targets:
        out.append("")
        out.append("---")
        out.append("")
        out.append("## 生词表")
        out.append("")
        out.append("| 单词 | 音标 | 词性 | 释义 |")
        out.append("| --- | --- | --- | --- |")
        for t in targets:
            g = gloss.get(norm(t)) or {}
            cells = [g.get("word") or t, g.get("ipa") or "", g.get("pos") or "", g.get("cn") or ""]
            out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in cells) + " |")

    used = [u for u in (article.get("used") or []) if (u.get("sentence") or "").strip()]
    if used:
        out.append("")
        out.append("## 例句")
        out.append("")
        seen = set()
        for u in used:
            s = u["sentence"].strip()
            if s in seen:          # 一个句子常承载多个目标词，去重后才好读
                continue
            seen.add(s)
            out.append(f"- {s}")

    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- 读盘

def _load(folder: Path) -> tuple[list[dict], dict]:
    body = folder / "body.json"
    if not body.exists():
        raise ExportError("这一天没有可导出的原稿（body.json）")
    articles = json.loads(body.read_text(encoding="utf-8"))
    meta = {}
    mp = folder / "meta.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    return articles, meta


def article_file(outdir: Path, day: str, index: int) -> tuple[str, str]:
    """返回 (下载文件名, markdown 内容)。index 从 1 开始。"""
    folder = outdir / day
    if not folder.is_dir():
        raise ExportError(f"没有 {day} 的数据")
    articles, meta = _load(folder)
    if not 1 <= index <= len(articles):
        raise ExportError(f"{day} 只有 {len(articles)} 篇")
    art = articles[index - 1]
    name = f"{day}-{index:02d}-{slug(art.get('title'))}.md"
    return name, article_markdown(art, day, meta)


def _pdf_cache(folder: Path) -> Path:
    return folder / f"pdf_v{PRINT_VERSION}"


def article_pdf(outdir: Path, day: str, index: int) -> tuple[str, bytes]:
    """返回 (下载文件名, PDF 字节)。生成过一次就落盘复用。"""
    folder = outdir / day
    if not folder.is_dir():
        raise ExportError(f"没有 {day} 的数据")
    articles, meta = _load(folder)
    if not 1 <= index <= len(articles):
        raise ExportError(f"{day} 只有 {len(articles)} 篇")
    art = articles[index - 1]
    cache = _pdf_cache(folder) / f"{index:02d}.pdf"
    body_mtime = (folder / "body.json").stat().st_mtime
    if not (cache.exists() and cache.stat().st_mtime >= body_mtime):
        html = render_article(art, day_label=day, index=index, total=len(articles),
                              model=meta.get("model") or "?", day_key=day, standalone=True)
        html_to_pdf(html, cache)
    name = f"{day}-{index:02d}-{slug(art.get('title'))}.pdf"
    return name, cache.read_bytes()


def _days(outdir: Path) -> list[Path]:
    if not outdir.exists():
        return []
    return sorted((d for d in outdir.iterdir()
                   if d.is_dir() and d.name != "demo" and (d / "body.json").exists()),
                  key=lambda p: p.name, reverse=True)


def zip_days(outdir: Path, only: str | None = None) -> tuple[str, bytes]:
    """打包成 zip（里面是 PDF）。only 给定日期时只导那一天。"""
    folders = _days(outdir)
    if only:
        folders = [d for d in folders if d.name == only]
    if not folders:
        raise ExportError("没有可导出的文章")

    index_lines = ["momo-daily 导出", "=" * 20, ""]
    total = 0
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder in folders:
            articles, meta = _load(folder)
            body_mtime = (folder / "body.json").stat().st_mtime
            index_lines.append(f"## {folder.name}")
            for i, art in enumerate(articles, 1):
                cache = _pdf_cache(folder) / f"{i:02d}.pdf"
                if not (cache.exists() and cache.stat().st_mtime >= body_mtime):
                    html = render_article(art, day_label=folder.name, index=i,
                                          total=len(articles),
                                          model=meta.get("model") or "?",
                                          day_key=folder.name, standalone=True)
                    html_to_pdf(html, cache)
                inner = f"{folder.name}/{i:02d}-{slug(art.get('title'))}.pdf"
                zf.write(cache, inner)
                index_lines.append(f"  - {art.get('title')}  →  {inner}")
                total += 1
            index_lines.append("")
        zf.writestr("索引.txt", "\n".join(index_lines))

    name = f"momo-daily-{only}.zip" if only else "momo-daily-all.zip"
    return name, buf.getvalue()
