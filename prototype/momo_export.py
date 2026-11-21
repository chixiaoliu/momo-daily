"""momo_export —— 用墨墨官方开放 API 导出「每天背过的单词」，不用手动粘贴。

用法（在 prototype 目录下，先设好 MAIMEMO_TOKEN）：

    python momo_export.py                     # 导出今天新学的词 → words/2026-11-21.txt
    python momo_export.py --forgotten         # 导出今天点了「忘记」的词
    python momo_export.py --date 2026-11-15   # 导出历史上某一天新学的词
    python momo_export.py --days 7            # 最近 7 天，一天一个文件
    python momo_export.py --csv               # 带学习次数/反馈的表格

导出的 txt 可以直接喂给 momo_daily.py：
    python momo_daily.py --words words/2026-11-15.txt
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from momo_client import MomoClient, MomoError  # noqa: E402

BEIJING = timezone(timedelta(hours=8))


def log(*args, **kwargs):
    print(*args, **kwargs, flush=True)


def bj_date(value: str | None) -> date | None:
    """把接口返回的 ISO 时间转成北京时间的「哪一天」。"""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=BEIJING)
    return dt.astimezone(BEIJING).date()


# ---------------------------------------------------------------- 取数

def _day_bounds(d: date) -> tuple[str, str]:
    """北京时间某一天的起止 ISO 字符串。"""
    return (f"{d.isoformat()}T00:00:00+08:00", f"{d.isoformat()}T23:59:59+08:00")


def fetch_all_records(client, limit: int = 1000, max_pages: int = 60,
                      log=print) -> list[dict]:
    """拉全量学习记录。

    单页上限 1000，按 next_study_date 顺序翻页。坑在于：墨墨会把一整天的词
    排到同一个时刻，翻到页尾正好卡在同一天时，下一页会整批跳过——所以要
    对「最后一页所在的那一天」补一次按日窗口查询。
    """
    records: list[dict] = []
    seen: set[str] = set()
    cursor: str | None = None  # 下一页起点（含）

    def add(batch: list[dict]) -> int:
        added = 0
        for r in batch:
            key = r.get("voc_id") or f"{r.get('voc_spelling')}|{r.get('first_study_date')}"
            if key in seen:
                continue
            seen.add(key)
            records.append(r)
            added += 1
        return added

    for page in range(1, max_pages + 1):
        body: dict = {"limit": limit}
        if cursor:
            body["next_study_date"] = {"start": cursor}
        batch = client.post("/study/query_study_records", body).get("records") or []
        if not batch:
            break
        added = add(batch)
        log(f"  · 第 {page} 页 {len(batch)} 条 → 新增 {added}，累计 {len(records)}")

        last = batch[-1].get("next_study_date")
        if not last:
            break
        day = bj_date(last)
        if day:  # 补齐这一天的全部记录
            start, end = _day_bounds(day)
            extra = client.post("/study/query_study_records",
                                {"limit": limit,
                                 "next_study_date": {"start": start, "end": end}}).get("records") or []
            filled = add(extra)
            if filled:
                log(f"    ↳ 补齐 {day} 当天：+{filled}")
        if len(batch) < limit:
            break
        cursor = (day + timedelta(days=1)).isoformat() + "T00:00:00+08:00" if day else None
        if not cursor:
            break
    return records


def group_by_first_study(records: list[dict]) -> dict[date, list[dict]]:
    days: dict[date, list[dict]] = {}
    for r in records:
        d = bj_date(r.get("first_study_date"))
        if d:
            days.setdefault(d, []).append(r)
    return days


def group_by_last_study(records: list[dict]) -> dict[date, list[dict]]:
    """按「最后一次学习日期」归日。

    注意：这个字段会被后续复习覆盖，所以只能近似还原历史某天复习过哪些词，
    越靠近今天的日子越准。
    """
    days: dict[date, list[dict]] = {}
    for r in records:
        d = bj_date(r.get("last_study_date"))
        if d:
            days.setdefault(d, []).append(r)
    return days


def today_new_words(client) -> list[dict]:
    """今天的精确数据：直接问 /get_today_items，比翻记录准。"""
    items = client.today_items(is_new=True, limit=1000)
    items.sort(key=lambda x: x.get("order", 0))
    return [{"voc_spelling": i.get("voc_spelling"), "is_new": True,
             "first_response": i.get("first_response")} for i in items
            if i.get("voc_spelling")]


def today_forgotten_words(client) -> list[dict]:
    items = client.today_items(is_finished=True, limit=1000)
    return [{"voc_spelling": i.get("voc_spelling"), "first_response": "FORGET"}
            for i in items if i.get("first_response") == "FORGET"]


# ---------------------------------------------------------------- 落盘

def write_day(outdir: Path, day: date, rows: list[dict], fmt: str, note: str = "") -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    words = [r["voc_spelling"] for r in rows if r.get("voc_spelling")]
    if fmt == "csv":
        path = outdir / f"{day.isoformat()}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["word", "first_response", "first_study_date", "study_count", "tags"])
            for r in rows:
                w.writerow([r.get("voc_spelling", ""), r.get("first_response") or "",
                            r.get("first_study_date") or "", r.get("study_count", ""),
                            r.get("tags") or ""])
        return path
    if fmt == "json":
        path = outdir / f"{day.isoformat()}.json"
        path.write_text(json.dumps({"date": day.isoformat(), "words": words,
                                    "records": rows}, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        return path
    path = outdir / f"{day.isoformat()}.txt"
    head = f"# {day.isoformat()} · {len(words)} 词"
    if note:
        head += f" · {note}"
    path.write_text(head + "\n" + "\n".join(words) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------- 入口

def main() -> int:
    ap = argparse.ArgumentParser(description="导出墨墨每天背过的单词（官方开放 API）")
    ap.add_argument("--date", help="指定日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--days", type=int, default=0, help="导出最近 N 天，一天一个文件")
    ap.add_argument("--forgotten", action="store_true", help="只要今天点了「忘记」的词")
    ap.add_argument("--format", choices=["txt", "csv", "json"], default="txt")
    ap.add_argument("--out", default=str(HERE / "words"), help="输出目录（默认 prototype/words）")
    ap.add_argument("--print", action="store_true", help="同时打印到终端")
    args = ap.parse_args()

    outdir = Path(args.out)
    try:
        client = MomoClient()
    except MomoError as exc:
        log(str(exc))
        return 1

    today = date.today()

    # 情况一：今天（精确接口）
    if not args.date and not args.days:
        rows: list[dict] = []
        note = ""
        if args.forgotten:
            rows = today_forgotten_words(client)
            note = "今日忘记"
        else:
            rows = today_new_words(client)
            if not rows:  # 今天还没学 / 接口没数据，退回记录
                log("  今天接口没返回新词，改从学习记录里翻…")
                days = group_by_first_study(fetch_all_records(client))
                rows = days.get(today, [])
            note = "今日新学"
        if not rows:
            log("没有拿到单词：先在 App 里学几个词，或确认开了「自动同步」。")
            return 1
        path = write_day(outdir, today, rows, args.format, note)
        log(f"√ {path}  （{len(rows)} 个词）")
        if args.print:
            for r in rows:
                log("  " + str(r.get("voc_spelling")))
        return 0

    # 情况二：历史 / 区间（翻学习记录，按 first_study_date 归日）
    log("拉取学习记录（一次性，可能几十秒）…")
    days_map = group_by_first_study(fetch_all_records(client))
    if args.date:
        target = date.fromisoformat(args.date)
        rows = days_map.get(target, [])
        if not rows:
            log(f"{target} 没有记录（那天可能没学，或数据不在返回范围内）。")
            return 1
        path = write_day(outdir, target, rows, args.format, "历史新学")
        log(f"√ {path}  （{len(rows)} 个词）")
        return 0

    written = 0
    for i in range(args.days):
        d = today - timedelta(days=i)
        rows = days_map.get(d, [])
        if not rows:
            continue
        path = write_day(outdir, d, rows, args.format, "历史新学")
        log(f"√ {path}  （{len(rows)} 个词）")
        written += 1
    log(f"完成：{written} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())
