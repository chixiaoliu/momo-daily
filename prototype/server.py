"""momo-daily 本地网页版：选日期、一键生成、手机上读。

    python server.py                # 默认 http://127.0.0.1:7788
    python server.py --port 9000
    python server.py --no-browser

两种运行模式：

* 私人模式（默认）：读根目录 .env，就是你自己的实例。
* 公网模式（MOMO_PUBLIC=1）：不读 .env 里的个人配置；每个访客用自己的 Cookie 会话，
  各自填自己的墨墨 Token / 模型 Key，数据也各存各的。适合放到 Cloudflare Tunnel / Render 上给别人用。
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

if hasattr(sys.stdout, "reconfigure"):
    # Windows 控制台默认 GBK，遇到 ✗ 这类字符会直接抛 UnicodeEncodeError
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
import exporting
import ui
from generator import LLM
from momo_client import MomoClient
from momo_export import fetch_all_records, group_by_first_study, group_by_last_study
from pipeline import DemoLLM, generate_day, recent_words

HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "output"
DATA = HERE / "data"
DEMO_JSON = HERE / "examples" / "demo_article.json"
CACHE_DIR = HERE / "cache"
GLOSSARY = CACHE_DIR / "glossary.json"

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 公网模式：每个访客一份配置和数据
PUBLIC = (os.environ.get("MOMO_PUBLIC") or config._read_file().get("MOMO_PUBLIC") or "") == "1"

# 允许跨域的前端地址（静态站放 Cloudflare Pages 时需要）。
# 留空 = 不开 CORS；填 * 或具体域名（如 https://momo.pages.dev）。
CORS = (os.environ.get("MOMO_CORS") or config._read_file().get("MOMO_CORS") or "").strip()

JOBS: dict[str, dict] = {}
_LOCK = threading.Lock()

# 翻全量学习记录很慢（几十秒），按会话缓存 10 分钟
_RECORDS: dict[str, dict] = {}


def jlog(sid: str, msg) -> None:
    text = str(msg)
    with _LOCK:
        job = JOBS.setdefault(sid, {})
        job.setdefault("log", []).append(text)
        if len(job["log"]) > 500:
            del job["log"][:200]
    try:
        print(text, flush=True)
    except Exception:  # 控制台编码问题绝不能影响任务状态
        pass


def parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def cookie_token(password: str) -> str:
    return hashlib.sha256(("momo-daily:" + password).encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------- 会话

def session_paths(sid: str) -> tuple[Path, Path]:
    base = DATA / "sessions" / sid
    return base / "config.json", base / "output"


# ---------------------------------------------------------------- 状态

def _load_meta(folder: Path) -> dict | None:
    path = folder / "meta.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_words(folder: Path) -> dict | None:
    path = folder / "words.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_state(cfg: dict, out: Path, date_str: str | None = None) -> dict:
    today = date.today()
    sel = parse_day(date_str) or today
    if sel > today:
        sel = today
    key = sel.isoformat()
    meta = _load_meta(out / key)
    wj = _load_words(out / key)
    dm = _load_meta(out / "demo")

    history = []
    if out.exists():
        for d in sorted((x for x in out.iterdir() if x.is_dir()), reverse=True):
            if d.name == "demo":
                continue
            m = _load_meta(d)
            arts = (m or {}).get("articles") or []
            if arts:
                history.append({"date": d.name, "count": len(arts),
                                "file": arts[0]["file"],
                                "title": arts[0].get("title") or "Untitled"})
    return {
        "today": today.isoformat(),
        "selected": key,
        "selected_label": f"{key} · {WEEKDAYS[sel.weekday()]}",
        "is_today": sel == today,
        "yesterday": (today - timedelta(days=1)).isoformat(),
        "before": (today - timedelta(days=2)).isoformat(),
        "cfg": config.status(cfg),
        "public": PUBLIC,
        "articles": (meta or {}).get("articles") or [],
        "word_count": len((wj or {}).get("words") or []),
        "demo_articles": (dm or {}).get("articles") or [],
        "history": history[:30],
    }


# ---------------------------------------------------------------- 取词

def cached_record_days(sid: str, client, log=print, ttl: int = 600) -> dict:
    cache = _RECORDS.get(sid) or {"at": 0.0, "first": {}, "last": {}}
    now = time.time()
    if cache["first"] and now - cache["at"] < ttl:
        return cache
    log("拉取学习记录（第一次会慢一点，之后 10 分钟内复用）…")
    records = fetch_all_records(client, log=log)
    first = group_by_first_study(records)
    last = group_by_last_study(records)
    if first:
        cache = {"at": now, "first": first, "last": last}
        _RECORDS[sid] = cache
    return cache


MIN_WORDS = 6
MAX_DAY_WORDS = 100   # 一天最多写多少词（100 词 = 5 篇，再多读不完了）


def words_for_day(sid: str, client, day: date, log=print) -> list[str]:
    """当天的全部词：新学的 + 复习的。新词排前面，超量时优先保住新词。"""
    if day == date.today():
        items = client.today_items(limit=1000)
        if not items:
            raise RuntimeError("今天墨墨里还没有单词。先在 App 里学一会儿，"
                               "或确认「自动同步」已打开。")
        new = [i for i in items if i.get("is_new")]
        review = [i for i in items if not i.get("is_new")]
        log(f"今天一共 {len(items)} 个词：新学 {len(new)} + 复习 {len(review)}")
        pool = [i.get("voc_spelling") for i in new + review]
    else:
        cache = cached_record_days(sid, client, log=log)
        new_rows = cache["first"].get(day, [])
        seen = {r.get("voc_id") for r in new_rows}
        rev_rows = [r for r in cache["last"].get(day, []) if r.get("voc_id") not in seen]
        log(f"{day.isoformat()}：新学 {len(new_rows)} + 复习 {len(rev_rows)}"
            f"（复习数按「最后学习日期」近似，越早的日子越不准）")
        pool = [r.get("voc_spelling") for r in new_rows + rev_rows]

    words = [w for w in pool if w]
    if len(words) > MAX_DAY_WORDS:
        log(f"      超过 {MAX_DAY_WORDS} 个，只取前 {MAX_DAY_WORDS} 个（新词优先）")
        words = words[:MAX_DAY_WORDS]
    if len(words) < MIN_WORDS:
        hint = ""
        if day != date.today():
            top = sorted(cache["first"].items(), key=lambda kv: len(kv[1]), reverse=True)[:3]
            hint = "记录里词比较多的日子：" + "、".join(
                f"{d.isoformat()}（{len(v)} 个）" for d, v in top if v)
        raise RuntimeError(f"{day.isoformat()} 只有 {len(words)} 个词，写不成故事。{hint}")
    return words


# ---------------------------------------------------------------- 任务

def start_job(sid: str, cfg: dict, out: Path, mode: str, day: date | None = None) -> tuple[bool, str]:
    with _LOCK:
        job = JOBS.setdefault(sid, {})
        if job.get("state") == "running":
            return False, "已有任务正在跑，等它结束"
        JOBS[sid] = {"state": "running", "log": [], "error": None, "meta": None, "mode": mode}
    threading.Thread(target=_run_job, args=(sid, cfg, out, mode, day), daemon=True).start()
    return True, "started"


def _run_job(sid: str, cfg: dict, out: Path, mode: str, day: date | None = None) -> None:
    state, error = "done", None
    target = day or date.today()
    log = lambda m: jlog(sid, m)  # noqa: E731
    try:
        if mode == "demo":
            log("[1/3] 使用内置样例文章（不调用墨墨和模型）")
            gen = DemoLLM()
            words = json.loads(DEMO_JSON.read_text(encoding="utf-8")).get("targets") or []
            review, folder = [], "demo"
            target = date.today()
        else:
            token = cfg.get("MAIMEMO_TOKEN", "")
            if not token:
                raise RuntimeError("还没填墨墨 Token，先去「设置」填一下")
            client = MomoClient(token)
            log(f"[1/3] 取 {target.isoformat()} 背过的词")
            words = words_for_day(sid, client, target, log=log)
            gen = LLM(api_key=cfg.get("LLM_API_KEY"),
                      base_url=cfg.get("LLM_BASE_URL"),
                      model=cfg.get("LLM_MODEL"))
            review = recent_words(out, today=target)
            folder = None
            if review:
                log(f"      注入 {len(review)} 个历史复习词")

        mode_cfg = (cfg.get("MOMO_MODE") or "single").lower()
        if mode_cfg == "split":
            per = max(10, min(60, int(cfg.get("MOMO_PER") or 20)))
            plan = f"按每篇 {per} 词拆分"
        else:
            per = max(len(words), 1)
            plan = "一篇"
        level = cfg.get("MOMO_LEVEL") or "B1 (CET-4)"
        log(f"[2/3] 生成中：{len(words)} 词 · {plan} · {level} · "
            f"模型 {getattr(gen, 'model', '?')}")

        articles, meta = generate_day(gen, words, out, per=per, level=level,
                                      review=review, log=log, folder=folder, day=target)
        log(f"[3/3] 完成，共 {len(articles)} 篇")
        with _LOCK:
            JOBS.setdefault(sid, {})["meta"] = meta
    except Exception as exc:  # 任何失败都要回到界面上，而不是让线程静默死掉
        state, error = "error", str(exc)
        log(f"✗ {exc}")
    finally:
        with _LOCK:
            JOBS.setdefault(sid, {}).update(state=state, error=error)


# ---------------------------------------------------------------- 全文翻译

ZH_SYS = """You translate English graded-reader stories into natural Simplified Chinese \
for Chinese learners. Translate faithfully but idiomatically; do not add or drop information.

Return JSON only, exactly: {"paragraphs": ["第一段中文", "第二段中文", ...]}

Rules:
- Exactly one Chinese paragraph per English paragraph, same order, same count.
- Never merge or split paragraphs.
- Keep proper nouns in a natural Chinese form."""


def translate_article(cfg: dict, out: Path, day: str, index: int) -> dict:
    folder = out / day
    body = folder / "body.json"
    if not body.exists():
        raise RuntimeError("这天没有可翻译的原稿")
    articles = json.loads(body.read_text(encoding="utf-8"))
    if not 1 <= index <= len(articles):
        raise RuntimeError("没有这一篇")
    paras = articles[index - 1].get("paragraphs") or []
    if not paras:
        raise RuntimeError("这篇没有正文")

    cache = folder / "zh" / f"{index:02d}.json"
    if cache.exists() and cache.stat().st_mtime >= body.stat().st_mtime:
        try:
            return {"paragraphs": json.loads(cache.read_text(encoding="utf-8"))["paragraphs"],
                    "cached": True}
        except Exception:
            pass

    if not cfg.get("LLM_API_KEY"):
        raise RuntimeError("需要先配置模型 Key 才能翻译")
    gen = LLM(api_key=cfg.get("LLM_API_KEY"), base_url=cfg.get("LLM_BASE_URL"),
              model=cfg.get("LLM_MODEL"), verbose=False, json_mode=True)
    prompt = json.dumps({"paragraphs": paras}, ensure_ascii=False)
    data = gen.json(ZH_SYS, prompt, temperature=0.3, max_tokens=3000)
    zh = [str(x).strip() for x in (data.get("paragraphs") or [])]
    if len(zh) != len(paras):
        raise RuntimeError(f"翻译段落数不对（{len(zh)} vs {len(paras)}），再点一次试试")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"paragraphs": zh}, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    return {"paragraphs": zh, "cached": False}


# ---------------------------------------------------------------- 词语查询

LOOKUP_SYS = """You are a bilingual dictionary for Chinese learners of English.
Return JSON only, exactly this shape:
{"ipa": "/.../", "pos": "n.", "cn": "中文释义"}

Rules:
- ipa: British IPA wrapped in slashes; empty string if unsure.
- pos: one of n. / v. / adj. / adv. / prep. / conj. / pron. / phr.
- cn: the meaning **as used in the given sentence**, at most 12 Chinese characters,
  no English, no examples, no explanation, no quotes.
- If the word is a proper noun or an inflected form, still give its base meaning."""

_GLOSS_LOCK = threading.Lock()


def _load_glossary() -> dict:
    if not GLOSSARY.exists():
        return {}
    try:
        return json.loads(GLOSSARY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def lookup_word(cfg: dict, word: str, sentence: str) -> dict:
    """单词/短语释义。先查本地缓存，没有才调模型，查过的永久缓存。"""
    key = (word or "").strip().lower()[:64]
    if not key:
        return {"ipa": "", "pos": "", "cn": ""}
    with _GLOSS_LOCK:
        cache = _load_glossary()
    if key in cache:
        return cache[key]

    if not cfg.get("LLM_API_KEY"):
        return {"ipa": "", "pos": "", "cn": "未配置模型 Key，查不了释义"}
    try:
        gen = LLM(api_key=cfg.get("LLM_API_KEY"), base_url=cfg.get("LLM_BASE_URL"),
                  model=cfg.get("LLM_MODEL"), verbose=False, json_mode=True)
        data = gen.json(LOOKUP_SYS, f"word: {key}\nsentence: {sentence[:300]}",
                        temperature=0.2)
        entry = {"ipa": str(data.get("ipa") or "")[:40],
                 "pos": str(data.get("pos") or "")[:16],
                 "cn": str(data.get("cn") or "")[:40]}
    except Exception as exc:
        return {"ipa": "", "pos": "", "cn": f"查询失败：{exc}"}

    if entry["cn"]:
        with _GLOSS_LOCK:
            cache = _load_glossary()
            cache[key] = entry
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            GLOSSARY.write_text(json.dumps(cache, ensure_ascii=False, indent=0),
                                encoding="utf-8")
    return entry


# ---------------------------------------------------------------- 归档

def build_archive(out: Path) -> list[dict]:
    days = []
    if not out.exists():
        return days
    for d in sorted((x for x in out.iterdir() if x.is_dir()), reverse=True):
        if d.name == "demo":
            continue
        meta = _load_meta(d)
        arts = (meta or {}).get("articles") or []
        if not arts:
            continue
        try:
            wd = WEEKDAYS[date.fromisoformat(d.name).weekday()]
        except ValueError:
            wd = ""
        days.append({"date": d.name, "weekday": wd, "articles": arts,
                     "count": len(arts),
                     "words": sum(a.get("words", 0) for a in arts)})
    return days


# ---------------------------------------------------------------- 连通性自检

def test_connections(cfg: dict) -> dict:
    out: dict = {"momo": {"ok": False, "msg": ""}, "llm": {"ok": False, "msg": ""}}
    try:
        client = MomoClient(cfg.get("MAIMEMO_TOKEN", ""))
        prog = client.progress()
        words = client.today_new_words()
        out["momo"] = {"ok": True,
                       "msg": f"连接正常 · 今日新学 {len(words)} 个词 "
                              f"（进度 {prog.get('finished', '?')}/{prog.get('total', '?')}）"}
    except Exception as exc:
        out["momo"] = {"ok": False, "msg": str(exc)}
    try:
        gen = LLM(api_key=cfg.get("LLM_API_KEY"), base_url=cfg.get("LLM_BASE_URL"),
                  model=cfg.get("LLM_MODEL"), verbose=False, json_mode=False)
        reply = gen.chat("You are a health check.", "Reply with exactly: pong",
                         temperature=0, max_tokens=8)
        out["llm"] = {"ok": True, "msg": f"{gen.model} 正常（返回 {reply.strip()[:16]}）"}
    except Exception as exc:
        out["llm"] = {"ok": False, "msg": str(exc)}
    return out


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "momodaily/0.4"
    timeout = 20

    sid: str = ""
    _new_sid: bool = False

    def log_message(self, fmt, *args):
        return

    # -- 会话
    def _ensure_sid(self) -> None:
        # 跨域前端没法用 Cookie，允许它自带一个会话 id（随机 16 位十六进制）
        sid = (self.headers.get("X-Momo-Sid") or "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{8,32}", sid):
            self.sid = sid
            return
        sid = ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "momo_sid" and re.fullmatch(r"[0-9a-f]{8,32}", v or ""):
                sid = v
                break
        if not sid:
            sid = secrets.token_hex(8)
            self._new_sid = True
        self.sid = sid

    def _ctx(self) -> tuple[dict, Path, Path]:
        if PUBLIC:
            cfg_path, out = session_paths(self.sid)
            return config.load_file(cfg_path), out, cfg_path
        return config.load(), OUTPUT, config.ENV_PATH

    # -- 输出 helper
    def _cors_headers(self) -> None:
        if not CORS:
            return
        self.send_header("Access-Control-Allow-Origin", CORS)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Momo-Sid")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self):
        self._ensure_sid()
        try:
            self.send_response(204)
            self._cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _send(self, code: int, payload: bytes, ctype: str, extra: dict | None = None) -> None:
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self._cors_headers()
            if self._new_sid:
                self.send_header("Set-Cookie",
                                 f"momo_sid={self.sid}; Path=/; HttpOnly; "
                                 f"Max-Age=31536000; SameSite=Lax")
                self._new_sid = False
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _html(self, text: str, code: int = 200) -> None:
        self._send(code, text.encode("utf-8"), "text/html; charset=utf-8")

    def _file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._html("<h1>404</h1><p>文件不存在</p>", 404)
            return
        ctype = ("text/html; charset=utf-8" if path.suffix == ".html"
                 else "application/json; charset=utf-8")
        self._send(200, path.read_bytes(), ctype)

    def _download(self, filename: str, payload: bytes, ctype: str) -> None:
        self._send(200, payload, ctype,
                   {"Content-Disposition": f'attachment; filename="{filename}"'})

    def _redirect(self, to: str) -> None:
        try:
            self.send_response(302)
            self.send_header("Location", to)
            self.send_header("Content-Length", "0")
            if self._new_sid:
                self.send_header("Set-Cookie",
                                 f"momo_sid={self.sid}; Path=/; HttpOnly; "
                                 f"Max-Age=31536000; SameSite=Lax")
                self._new_sid = False
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # -- 认证（只在私人模式下有意义）
    def _authed(self) -> bool:
        if PUBLIC:
            return True
        pw = (config.load().get("MOMO_PASS") or "").strip()
        if not pw:
            return True
        want = cookie_token(pw)
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "momo_auth" and v == want:
                return True
        return False

    def _do_login(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        pw = ""
        if raw.startswith("{"):
            try:
                pw = str((json.loads(raw) or {}).get("password") or "")
            except Exception:
                pw = ""
        else:
            pw = (parse_qs(raw).get("password") or [""])[0]
        want = (config.load().get("MOMO_PASS") or "").strip()
        if want and pw == want:
            try:
                self.send_response(302)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie",
                                 f"momo_auth={cookie_token(want)}; Path=/; HttpOnly; "
                                 f"Max-Age=2592000; SameSite=Lax")
                self.send_header("Content-Length", "0")
                self.end_headers()
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self._html(ui.login_page(error=True), 401)

    # -- 路由
    def do_GET(self):
        self._ensure_sid()
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        day_arg = (query.get("date") or [None])[0]

        if path == "/login":
            self._html(ui.login_page())
            return
        if not self._authed():
            self._redirect("/login")
            return

        cfg, out, _ = self._ctx()

        if path in ("/", "/index.html"):
            try:
                self._html(ui.dashboard(build_state(cfg, out, day_arg)))
            except Exception as exc:
                self._html(f"<h1>500</h1><pre>{html.escape(str(exc))}</pre>", 500)
        elif path == "/setup":
            self._html(ui.setup_page(build_state(cfg, out, day_arg)))
        elif path == "/archive":
            try:
                self._html(ui.archive(build_archive(out)))
            except Exception as exc:
                self._html(f"<h1>500</h1><pre>{html.escape(str(exc))}</pre>", 500)
        elif path == "/api/state":
            self._json(build_state(cfg, out, day_arg))
        elif path == "/api/job":
            with _LOCK:
                job = dict(JOBS.get(self.sid) or {})
                snap = {"state": job.get("state", "idle"),
                        "log": list(job.get("log") or [])[-200:],
                        "error": job.get("error"), "meta": job.get("meta")}
            self._json(snap)
        elif path.startswith("/read/"):
            self._serve_output(out, path[len("/read/"):])
        elif path.startswith("/export/"):
            self._serve_export(cfg, out, path[len("/export/"):])
        elif path.startswith("/output/"):
            self._serve_output(out, path[len("/output/"):])
        else:
            self._html("<h1>404</h1><p><a href='/'>回到首页</a></p>", 404)

    def _serve_output(self, out: Path, rel: str) -> None:
        target = (out / rel).resolve()
        try:
            target.relative_to(out.resolve())
        except ValueError:
            self._html("<h1>403</h1>", 403)
            return
        self._file(target)

    def _serve_export(self, cfg: dict, out: Path, rel: str) -> None:
        rel = rel.strip("/")
        try:
            if rel == "all.zip":
                name, data = exporting.zip_days(out)
                self._download(name, data, "application/zip")
            elif rel.endswith(".zip"):
                name, data = exporting.zip_days(out, only=rel[:-4])
                self._download(name, data, "application/zip")
            elif rel.endswith(".pdf"):
                day, _, fname = rel.partition("/")
                digits = re.sub(r"\D", "", fname)
                if not day or not digits:
                    self._html("<h1>404</h1>", 404)
                    return
                name, data = exporting.article_pdf(out, day, int(digits))
                self._download(name, data, "application/pdf")
            elif rel.endswith(".md"):
                day, _, fname = rel.partition("/")
                digits = re.sub(r"\D", "", fname)
                if not day or not digits:
                    self._html("<h1>404</h1>", 404)
                    return
                name, text = exporting.article_file(out, day, int(digits))
                self._download(name, text.encode("utf-8"), "text/markdown; charset=utf-8")
            else:
                self._html("<h1>404</h1>", 404)
        except exporting.ExportError as exc:
            self._html(f"<h1>404</h1><p>{html.escape(str(exc))}</p>"
                       f"<p><a href='/archive'>返回归档</a></p>", 404)

    def do_POST(self):
        self._ensure_sid()
        path = urlparse(self.path).path
        if path == "/login":
            self._do_login()
            return
        if not self._authed():
            self._json({"ok": False, "error": "未登录（这个实例设置了访问口令）"}, 401)
            return

        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        except Exception:
            self._json({"ok": False, "error": "请求体不是合法 JSON"}, 400)
            return

        cfg, out, cfg_path = self._ctx()

        if path == "/api/config":
            updates = body if isinstance(body, dict) else {}
            if PUBLIC:
                config.save_file(cfg_path, updates)
            else:
                config.save(updates)
            cfg = config.load_file(cfg_path) if PUBLIC else config.load()
            self._json({"ok": True, "cfg": config.status(cfg)})
        elif path == "/api/test":
            self._json(test_connections(cfg))
        elif path == "/api/lookup":
            word = str((body or {}).get("word") or "")
            sentence = str((body or {}).get("sentence") or "")
            self._json(lookup_word(cfg, word, sentence))
        elif path == "/api/translate":
            day = str((body or {}).get("day") or "")
            try:
                idx = int((body or {}).get("index") or 0)
                self._json(translate_article(cfg, out, day, idx))
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
        elif path == "/api/generate":
            mode = "demo" if (body or {}).get("mode") == "demo" else "api"
            day = parse_day((body or {}).get("date"))
            if day and day > date.today():
                self._json({"started": False, "message": "不能生成未来日期"})
                return
            ok, msg = start_job(self.sid, cfg, out, mode, day)
            self._json({"started": ok, "message": msg,
                        "date": (day or date.today()).isoformat()})
        else:
            self._json({"ok": False, "error": "unknown endpoint"}, 404)


# ---------------------------------------------------------------- 启动

def _port_in_use(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.4):
            return True
    except OSError:
        return False


def lan_ips() -> list[str]:
    """默认路由的网卡排最前——那才是手机连得上的那个。"""
    primary = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary = s.getsockname()[0]
        s.close()
    except Exception:
        pass
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    if primary:
        ips.add(primary)
    rest = sorted(i for i in ips if not i.startswith("127.") and i != primary)
    return ([primary] if primary else []) + rest


def main() -> None:
    ap = argparse.ArgumentParser(description="momo-daily 本地网页版")
    ap.add_argument("--port", type=int, default=7788)
    ap.add_argument("--host", default="0.0.0.0", help="默认 0.0.0.0，方便手机访问")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    if PUBLIC:
        DATA.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{args.port}/"

    if _port_in_use(args.port):
        print(f"端口 {args.port} 上已经有一个 momo-daily 在跑，直接打开：{url}")
        if not args.no_browser:
            webbrowser.open(url)
        return
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as exc:
        print(f"启动失败：{exc}")
        return

    print("momo·daily 已启动")
    print(f"  本机：{url}")
    for ip in lan_ips():
        print(f"  手机：http://{ip}:{args.port}/   （同一 WiFi）")
    print(f"  模式：{'公网（每个访客自带 Token）' if PUBLIC else '私人'}")
    print("  按 Ctrl+C 停止")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
