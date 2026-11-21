"""pipeline —— CLI 和网页共用的「取词 → 生成 → 落盘」流程。"""
from __future__ import annotations

import copy
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from generator import generate_for_day
from render import render_article

HERE = Path(__file__).resolve().parent
DEMO_JSON = HERE / "examples" / "demo_article.json"

# 墨墨的词条里混着短语和专有表达（如 "a variety of ..."），塞进故事会毁掉匹配
_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z'\-]{1,19}$")


def split_entries(entries) -> tuple[list[str], list[str]]:
    """拆成「能写进故事的单词」和「跳过的短语/异常条目」。"""
    words, skipped, seen = [], [], set()
    for raw in entries or []:
        s = str(raw or "").strip()
        if not s:
            continue
        if _WORD_RE.match(s):
            if s.lower() not in seen:
                seen.add(s.lower())
                words.append(s)
        else:
            skipped.append(s)
    return words, skipped

INDEX_TMPL = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>momo-daily · 每日一文</title>
<style>
body{margin:0 auto;background:#fbf8f3;color:#211f1b;font-family:ui-sans-serif,system-ui,"PingFang SC",sans-serif;
padding:28px 20px 60px;max-width:660px;line-height:1.7}
h1{font-size:20px;margin:0 0 4px}p.sub{color:#8a8175;font-size:12.5px;margin:0 0 26px}
a.card{display:block;text-decoration:none;color:inherit;border:1px solid #e7dfd2;border-radius:14px;
padding:16px 18px;margin:0 0 12px;background:#fff}
a.card:hover{border-color:#2f6f73}a.card .n{font-family:Georgia,serif;font-size:17px;font-weight:600}
a.card .m{font-size:12px;color:#8a8175;margin-top:6px}
</style></head><body>
<h1>momo-daily</h1><p class="sub">每天背的单词，变成当天要读的故事</p>
__ITEMS__
</body></html>"""


class DemoLLM:
    """返回手写的样例文章，用于零配置预览。"""

    model = "demo"

    def __init__(self):
        self._art = json.loads(DEMO_JSON.read_text(encoding="utf-8"))

    def json(self, *args, **kwargs):
        return copy.deepcopy(self._art)

    def chat(self, *args, **kwargs):
        raise NotImplementedError


def recent_words(outdir: Path, offsets=(1, 3, 7), cap: int = 12,
                 today: date | None = None) -> list[str]:
    """取 D-1 / D-3 / D-7 用过的词，作为复习词注入当天的文章。"""
    picked: list[str] = []
    today = today or date.today()
    for off in offsets:
        meta = outdir / (today - timedelta(days=off)).isoformat() / "words.json"
        if not meta.exists():
            continue
        try:
            picked.extend((json.loads(meta.read_text(encoding="utf-8")).get("words") or [])[:cap])
        except Exception:
            continue
    seen, out = set(), []
    for w in picked:
        if w.lower() not in seen:
            seen.add(w.lower())
            out.append(w)
    return out


def build_index(outdir: Path) -> None:
    if not outdir.exists():
        return
    blocks = []
    days = sorted([d for d in outdir.iterdir() if d.is_dir()], reverse=True)
    for d in days[:60]:
        meta_path = d / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        cards = "".join(
            f'<a class="card" href="{d.name}/{a["file"]}">'
            f'<div class="n">{a["title"]}</div>'
            f'<div class="m">{d.name} · {a["targets"]} 个新词 · 覆盖 {a["coverage"]:.0%}</div></a>'
            for a in meta.get("articles", [])
        )
        blocks.append(cards)
    (outdir / "index.html").write_text(
        INDEX_TMPL.replace("__ITEMS__", "\n".join(blocks)), encoding="utf-8")


def write_day(outdir: Path, day: date, words: list[str], review: list[str],
              articles: list[dict], model: str, source: str = "api",
              folder: str | None = None) -> dict:
    """落盘：每个章节一个 html + words.json + meta.json + 总索引。"""
    day_dir = outdir / (folder or day.isoformat())
    day_dir.mkdir(parents=True, exist_ok=True)
    label = day.strftime("%Y-%m-%d")
    meta_articles = []
    total = len(articles)
    for i, art in enumerate(articles, 1):
        fname = f"{i:02d}.html"
        page = render_article(art, day_label=label, index=i, total=total, model=model,
                              generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                              day_key=folder or label)
        (day_dir / fname).write_text(page, encoding="utf-8")
        stats = art.get("stats") or {}
        meta_articles.append({
            "file": fname,
            "title": art.get("title") or "Untitled",
            "title_cn": art.get("title_cn") or "",
            "targets": len(art.get("targets") or []),
            "coverage": stats.get("coverage", 0),
            "missing": stats.get("missing", []),
            "words": stats.get("words", 0),
        })
    # 重新生成时篇数可能变少（5 篇 → 1 篇），把多余的旧章节删掉，免得留下孤儿页面
    keep = {a["file"] for a in meta_articles}
    for old in day_dir.glob("*.html"):
        if old.name not in keep:
            old.unlink(missing_ok=True)

    (day_dir / "words.json").write_text(
        json.dumps({"date": label, "source": source, "words": words,
                    "recycled": review},   # recycled = 跨天注入的旧词，不是「复习词」
                   ensure_ascii=False, indent=2), encoding="utf-8")
    # 存一份原始稿件：以后改排版/改样式可以直接重渲染，不用再花一次模型钱
    (day_dir / "body.json").write_text(
        json.dumps(articles, ensure_ascii=False, indent=1), encoding="utf-8")
    meta = {"date": label, "model": model, "source": source,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "articles": meta_articles}
    (day_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    build_index(outdir)
    return meta


def generate_day(gen, words: list[str], outdir: Path, per: int = 20,
                 level: str = "B1 (CET-4)", topic: str | None = None,
                 review: list[str] | None = None, paragraphs: int | None = None,
                 log=print, folder: str | None = None,
                 day: date | None = None) -> tuple[list[dict], dict]:
    """生成并落盘，返回 (articles, meta)。day 默认今天，可指定历史日期。"""
    words, skipped = split_entries(words)
    if skipped:
        preview = "、".join(skipped[:6]) + ("…" if len(skipped) > 6 else "")
        log(f"      跳过 {len(skipped)} 个短语/非单词条目：{preview}")
    if not words:
        raise ValueError("这一天没有可用的单词（全是短语或空）")
    articles = generate_for_day(gen, words, per_article=per, level=level, topic=topic,
                                review_words=review or [], paragraphs=paragraphs, log=log)
    meta = write_day(outdir, day or date.today(), words, review or [], articles,
                     model=getattr(gen, "model", "?"),
                     source="demo" if isinstance(gen, DemoLLM) else "api", folder=folder)
    return articles, meta
