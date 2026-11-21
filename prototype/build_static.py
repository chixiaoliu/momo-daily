r"""把 output/ 里的文章打包成一个纯静态站点，可以直接丢到 Cloudflare Pages / GitHub Pages。

    python build_static.py          # 生成到 ../site/
    python build_static.py --out D:\site

静态站是只读的：能读文章、点目标词查释义、朗读、做挖空题；
「生成新文章」和「查非目标词」需要本地服务，所以在静态页里自动隐藏/降级。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from render import render_article  # noqa: E402

OUTPUT = HERE / "output"

INDEX = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#fbf8f3">
<title>momo·daily · 每日一文</title>
<style>
:root{--paper:#fbf8f3;--ink:#211f1b;--muted:#8a8175;--line:#e7dfd2;--accent:#2f6f73;--card:#fff}
@media (prefers-color-scheme:dark){:root{--paper:#161513;--ink:#eae6dd;--muted:#9a9184;
  --line:#302d27;--accent:#7fc4c0;--card:#22201c}}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);line-height:1.65;
  font-family:ui-sans-serif,system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
main{max-width:680px;margin:0 auto;padding:34px 20px 80px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px;margin:0 0 28px}
.month{font-size:12px;letter-spacing:.12em;color:var(--muted);margin:28px 0 10px;font-weight:600}
.day{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);
  margin:20px 0 8px;padding-bottom:6px;border-bottom:1px solid var(--line)}
a.card{display:block;text-decoration:none;color:inherit;border:1px solid var(--line);
  border-radius:13px;padding:14px 16px;margin:0 0 9px;background:var(--card)}
a.card:hover{border-color:var(--accent)}
a.card .t{font-family:Georgia,"Times New Roman",serif;font-size:16.5px;font-weight:600}
a.card .c{font-size:12px;color:var(--muted);margin-top:2px}
a.card .m{font-size:12px;color:var(--muted);margin-top:6px;display:flex;gap:12px}
footer{margin-top:46px;padding-top:16px;border-top:1px solid var(--line);
  font-size:11.5px;color:var(--muted);line-height:1.8}
</style></head><body><main>
<h1>每日一文</h1>
<p class="sub">每天背的单词，变成当天要读的故事</p>
__BODY__
<footer>静态导出 · 只读<br>
点高亮词看释义、可朗读、可做挖空题；生成新文章需要回到本地服务。</footer>
</main></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="把已生成的文章打包成静态站")
    ap.add_argument("--out", default=str(HERE.parent / "site"), help="输出目录")
    ap.add_argument("--zip", action="store_true", help="同时打一个 zip，方便整包上传")
    ap.add_argument("--demo-only", action="store_true",
                    help="只打包样例文章，不含你的个人词表（分享给别人时更安全）")
    args = ap.parse_args()

    site = Path(args.out)
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)

    if args.demo_only:
        demo = OUTPUT / "demo"
        days = [demo] if (demo / "body.json").exists() else []
    else:
        days = sorted((d for d in OUTPUT.iterdir()
                       if d.is_dir() and d.name != "demo" and (d / "body.json").exists()),
                      key=lambda p: p.name, reverse=True) if OUTPUT.exists() else []

    blocks: list[str] = []
    month = None
    total = 0
    for folder in days:
        try:
            articles = json.loads((folder / "body.json").read_text(encoding="utf-8"))
            meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"跳过 {folder.name}: {exc}")
            continue
        out_dir = site / folder.name
        out_dir.mkdir()

        if folder.name[:7] != month:
            month = folder.name[:7]
            if len(month) == 7 and "-" in month:
                y, m = month.split("-")
                blocks.append(f'<div class="month">{y} 年 {int(m)} 月</div>')
            else:
                blocks.append('<div class="month">样例</div>')

        n = len(articles)
        rows = []
        for i, art in enumerate(articles, 1):
            html = render_article(art, day_label=folder.name, index=i, total=n,
                                  model=meta.get("model") or "?",
                                  day_key=folder.name, standalone=True)
            (out_dir / f"{i:02d}.html").write_text(html, encoding="utf-8")
            stats = art.get("stats") or {}
            rows.append(
                f'<a class="card" href="{folder.name}/{i:02d}.html">'
                f'<div class="t">{art.get("title") or "Untitled"}</div>'
                f'<div class="c">{art.get("title_cn") or ""}</div>'
                f'<div class="m"><span>{len(art.get("targets") or [])} 个词</span>'
                f'<span>{stats.get("words", 0)} 词</span>'
                f'<span>覆盖 {(stats.get("coverage") or 0):.0%}</span></div></a>')
            total += 1
        blocks.append(f'<div class="day"><span>{folder.name}</span><span>{n} 篇</span></div>')
        blocks.extend(rows)
        print(f"√ {folder.name}  {n} 篇")

    (site / "index.html").write_text(INDEX.replace("__BODY__", "\n".join(blocks)),
                                     encoding="utf-8")
    print(f"\n完成：{site.resolve()}  共 {total} 篇 / {len(days)} 天")

    if args.zip:
        import zipfile
        zp = site.parent / f"{site.name}.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(site.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(site).as_posix())
        print(f"打包：{zp.resolve()}  {zp.stat().st_size // 1024} KB")

    print("把整个 site 目录拖到 Cloudflare Pages 或 GitHub Pages 即可。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
