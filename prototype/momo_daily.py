"""momo-daily —— 把「今天背的单词」变成「今天读的故事」。

用法（在 prototype 目录下）：
    python momo_daily.py --demo            # 不需要任何 Key，先看效果
    python momo_daily.py --sample          # 用内置词 + 真模型跑
    python momo_daily.py                   # 正式：墨墨取词 + 调模型 + 生成 HTML
    python momo_daily.py --words my.txt --topic "一个雨夜的出租车"
    python momo_daily.py --push            # 额外把例句回写进墨墨

环境变量：
    MAIMEMO_TOKEN   墨墨开放 API Token（App → 我的 → 开放 API）
    LLM_API_KEY     DeepSeek / 任意 OpenAI 兼容服务的 Key
    LLM_BASE_URL    默认 https://api.deepseek.com/v1
    LLM_MODEL       默认 deepseek-chat
"""
from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from generator import LLM, LLMError, MockLLM  # noqa: E402
from momo_client import MomoClient, MomoError  # noqa: E402
from pipeline import DemoLLM, generate_day, recent_words  # noqa: E402

SAMPLE_WORDS = [
    "abandon", "absorb", "abstract", "accommodate", "accumulate", "accurate",
    "acknowledge", "acquire", "adapt", "adequate", "advocate", "aesthetic",
    "ambiguous", "ambitious", "anticipate", "apparent", "appropriate", "arbitrary",
    "articulate", "assess", "assume", "attitude", "authentic", "autonomy",
    "bias", "boost", "boundary", "capable", "capacity", "casual",
    "circumstance", "cite", "coherent", "collapse", "commit", "compensate",
    "competent", "complex", "comprehensive", "conceal", "concede", "concrete",
]


def log(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def load_words_file(path: str) -> list[str]:
    text = Path(path).read_text(encoding="utf-8")
    words = []
    for line in text.replace(",", "\n").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            words.append(line)
    return words


def main() -> int:
    ap = argparse.ArgumentParser(description="把墨墨今日单词生成一篇可读短文")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--words", help="从 txt 读取单词（每行一个，逗号也支持）")
    src.add_argument("--sample", action="store_true", help="使用内置示例词，不访问网络")
    src.add_argument("--demo", action="store_true", help="渲染 examples/demo_article.json 的真实样例")
    ap.add_argument("--mock", action="store_true", help="不调用大模型，用占位文章（测链路）")
    ap.add_argument("--per", type=int, default=0,
                    help="每篇多少个新词；0（默认）= 不管多少词都写成一篇")
    ap.add_argument("--paragraphs", type=int, default=0,
                    help="每篇段落数；0（默认）= 按词数自动决定")
    ap.add_argument("--level", default="B1 (CET-4)", help="难度描述，如 B1 / B2 / IELTS 6.5")
    ap.add_argument("--topic", default=None, help="指定主题，如「深夜便利店」")
    ap.add_argument("--out", default=str(HERE / "output"), help="输出目录")
    ap.add_argument("--no-review", action="store_true", help="不注入 D-1/D-3/D-7 的复习词")
    ap.add_argument("--push", action="store_true", help="把文章例句回写进墨墨（写入 /phrases）")
    ap.add_argument("--notepad", action="store_true", help="同时在墨墨创建当天的云词本")
    ap.add_argument("--open", action="store_true", help="生成后自动打开阅读器")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    folder = "demo" if args.demo else None

    # ---------- 1. 取词 ----------
    source = "sample"
    words: list[str] = []
    review: list[str] = []
    if args.demo:
        demo = json.loads((HERE / "examples" / "demo_article.json").read_text(encoding="utf-8"))
        words, source = demo.get("targets") or [], "demo"
        log(f"[1/4] 样例文章：{len(words)} 个目标词（{demo.get('title')}）")
    elif args.sample:
        words, source = SAMPLE_WORDS[: args.per], "sample"
        log(f"[1/4] 使用内置示例词：{len(words)} 个")
    elif args.words:
        words, source = load_words_file(args.words), f"file:{args.words}"
        log(f"[1/4] 从文件读取：{len(words)} 个词")
    else:
        try:
            client = MomoClient()
            words, source = client.today_new_words(), "maimemo-api"
            prog = client.progress()
            log(f"[1/4] 墨墨今日新学：{len(words)} 个词"
                f"（进度 {prog.get('finished', '?')}/{prog.get('total', '?')}）")
            if not words:
                log("      今天还没有新学词，改用示例词演示。")
                words, source = SAMPLE_WORDS[: args.per], "sample"
        except (MomoError, OSError) as exc:
            log(f"[1/4] 读取墨墨失败：{exc}")
            log("      退回示例词。可先用 --words 手动给词表。")
            words, source = SAMPLE_WORDS[: args.per], "sample"

    if not words:
        log("没有可用的单词，退出。")
        return 1

    if not args.no_review and not args.demo:
        review = recent_words(outdir)
        if review:
            log(f"      注入 {len(review)} 个历史复习词（D-1/D-3/D-7）")

    # ---------- 2. 生成 ----------
    if args.demo:
        gen = DemoLLM()
    elif args.mock:
        gen = MockLLM()
    else:
        try:
            gen = LLM()
        except LLMError as exc:
            log(f"[2/4] {exc}")
            log("      改用 mock 模式演示，或先配置 LLM_API_KEY。")
            gen = MockLLM()
    model_name = getattr(gen, "model", "mock")
    per = args.per if args.per > 0 else max(len(words), 1)
    log(f"[2/4] 生成中：{len(words)} 词 → {'一篇' if args.per <= 0 else f'每篇 {per} 词'} · "
        f"模型 {model_name}")
    articles, meta = generate_day(gen, words, outdir, per=per, level=args.level,
                                  topic=args.topic, review=review,
                                  paragraphs=args.paragraphs or None,
                                  log=log, folder=folder)

    day_dir = outdir / (folder or date.today().isoformat())
    for a in meta["articles"]:
        log(f"[3/4] 写入 {day_dir / a['file']}")

    # ---------- 4. 回写墨墨 ----------
    if args.push or args.notepad:
        try:
            client = MomoClient()
            if args.push:
                ids = client.resolve_ids(sorted({w for a in articles for w in (a.get("targets") or [])}))
                pushed, failed = 0, 0
                for art in articles:
                    for u in art.get("used") or []:
                        vid = ids.get((u.get("target") or "").lower())
                        if not vid:
                            failed += 1
                            continue
                        try:
                            client.add_phrase(vid, u.get("sentence", ""))
                            pushed += 1
                        except MomoError:
                            failed += 1
                log(f"[4/4] 回写例句：成功 {pushed}，失败 {failed}")
            if args.notepad:
                blob = client.create_notepad(f"AI每日 {date.today().isoformat()}", words,
                                             brief=articles[0].get("title", "") if articles else "")
                log(f"[4/4] 云词本已创建：{(blob.get('notepad') or {}).get('id', '?')}")
        except MomoError as exc:
            log(f"[4/4] 回写墨墨失败：{exc}")

    if args.open:
        webbrowser.open((day_dir / "01.html").resolve().as_uri())

    log("")
    log(f"完成：{(day_dir / '01.html').resolve()}")
    for a in meta["articles"]:
        flag = f"  ⚠ 漏词 {len(a['missing'])}" if a["missing"] else ""
        log(f"  · {a['file']}  {a['title']}  覆盖 {a['coverage']:.0%}{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
