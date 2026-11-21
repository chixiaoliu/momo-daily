"""用已有的 body.json 重新渲染页面，不调用模型、不花钱。

改完排版、字号、交互之后跑一次：

    python rerender.py            # 全部日期
    python rerender.py 2026-11-15 # 只重渲染某一天
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pipeline import write_day  # noqa: E402

OUTPUT = HERE / "output"


def rerender(folder: Path) -> bool:
    body = folder / "body.json"
    if not body.exists():
        return False
    articles = json.loads(body.read_text(encoding="utf-8"))
    words = json.loads((folder / "words.json").read_text(encoding="utf-8"))
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    is_demo = folder.name == "demo"
    day = date.today() if is_demo else date.fromisoformat(folder.name)
    write_day(OUTPUT, day, words.get("words") or [],
              words.get("recycled") or words.get("review") or [],
              articles, model=meta.get("model") or "?", source=meta.get("source") or "api",
              folder="demo" if is_demo else None)
    print(f"√ {folder.name}  {len(articles)} 篇")
    return True


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    count = 0
    for d in sorted((x for x in OUTPUT.iterdir() if x.is_dir())):
        if target and d.name != target:
            continue
        if rerender(d):
            count += 1
    print(f"完成：{count} 天")
    return 0 if count else 1


if __name__ == "__main__":
    raise SystemExit(main())
