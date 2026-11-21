"""生成引擎：分组 → 调用大模型 → 覆盖校验 → 局部补词。

支持任何 OpenAI 兼容接口（DeepSeek / 通义 / Kimi / 本地 Ollama 均可）。
无 API Key 时用 MockGenerator，用于离线演示阅读器效果。
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request

from prompts import PATCH_SYSTEM, SYSTEM, build_patch_prompt, build_user_prompt

# ---------------------------------------------------------------- 文本工具

_SUFFIX = {
    "": "", "s": "", "es": "", "ed": "", "d": "", "ing": "", "ly": "",
    "er": "", "est": "", "ers": "", "ings": "", "ied": "y", "ies": "y",
    "ying": "y", "ying": "", "ied": "",
}


def norm(word: str) -> str:
    return re.sub(r"[^a-z'\-]", "", (word or "").lower())


def word_forms(word: str) -> set[str]:
    """粗略词形集合——只用于「是否出现过」的宽松匹配，不追求语言学完美。"""
    w = norm(word)
    if not w:
        return set()
    forms = {w, w + "s", w + "es", w + "ed", w + "d", w + "ing", w + "ly",
             w + "er", w + "est"}
    if w.endswith("e"):
        forms |= {w[:-1] + "ing", w[:-1] + "ed"}
    if w.endswith("y"):
        forms |= {w[:-1] + "ies", w[:-1] + "ied", w[:-1] + "ier", w[:-1] + "iest"}
    if len(w) > 3 and w[-1] not in "aeiou" and w[-2] in "aeiou" and w[-3] not in "aeiou":
        forms |= {w + w[-1] + "ing", w + w[-1] + "ed", w + w[-1] + "er"}
    forms.add(w + "ness")
    forms.add(w + "ment")
    return {f for f in forms if len(f) >= 2}


def article_text(article: dict) -> str:
    parts = [article.get("title", "")] + list(article.get("paragraphs") or [])
    return "\n".join(parts)


def missing_words(article: dict, targets: list[str]) -> list[str]:
    """双重校验：模型自报的 used 列表 ∪ 正文正则扫描。"""
    reported = {norm(u.get("target", "")) for u in article.get("used") or []}
    text = article_text(article).lower()
    missing = []
    for t in targets:
        n = norm(t)
        if not n:
            continue
        if n in reported:
            continue
        if any(re.search(rf"\b{re.escape(f)}\b", text) for f in word_forms(n)):
            continue
        missing.append(t)
    return missing


def coverage(article: dict, targets: list[str]) -> float:
    if not targets:
        return 1.0
    return 1 - len(missing_words(article, targets)) / len(targets)


def chunk(seq: list, size: int) -> list[list]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def shape_for(n: int, paragraphs: int | None = None) -> tuple[int, int, tuple[int, int]]:
    """按词数决定篇幅：多少段、每段摊几个词、总词数区间。

    词越多文章越长，而不是把词硬挤进去——否则生词率会失控。
    """
    paras = paragraphs or max(5, min(14, math.ceil(n / 5)))
    paras = max(3, min(16, paras))
    per_para = max(1, math.ceil(n / paras))
    lo = max(340, int(n * 15))
    hi = min(1700, max(400, int(n * 18)))
    return paras, per_para, (lo, hi)


def _strip_fence(raw: str) -> str:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    if not raw.startswith("{"):
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            raw = raw[start:end + 1]
    return raw


# ---------------------------------------------------------------- LLM 客户端

class LLMError(RuntimeError):
    pass


class LLM:
    """OpenAI 兼容 /chat/completions 的最小封装，纯标准库。"""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, json_mode: bool | None = None,
                 verbose: bool = True):
        self.api_key = (api_key or os.environ.get("LLM_API_KEY") or "").strip()
        self.base_url = (base_url or os.environ.get("LLM_BASE_URL")
                         or "https://api.deepseek.com/v1").rstrip("/")
        self.model = model or os.environ.get("LLM_MODEL") or "deepseek-chat"
        if json_mode is None:
            json_mode = os.environ.get("LLM_JSON_MODE", "1") != "0"
        self.json_mode = json_mode
        self.verbose = verbose
        if not self.api_key:
            raise LLMError("缺少 LLM_API_KEY（DeepSeek 控制台 → API keys 获取）")

    def chat(self, system: str, user: str, temperature: float = 0.8,
             max_tokens: int = 2200) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.json_mode:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=body, method="POST",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"})
        last = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "ignore")
                if exc.code in (429, 500, 502, 503):
                    last = LLMError(f"HTTP {exc.code}: {detail}")
                    time.sleep(2 + attempt * 3)
                    continue
                raise LLMError(f"模型接口报错 HTTP {exc.code}: {detail}") from exc
            except (urllib.error.URLError, KeyError, json.JSONDecodeError) as exc:
                last = LLMError(f"模型接口异常: {exc}")
                time.sleep(1 + attempt)
        raise last or LLMError("模型调用失败")

    def json(self, system: str, user: str, temperature: float = 0.8,
             max_tokens: int = 3000, attempts: int = 2) -> dict:
        """要 JSON，并且容忍一次偶发的解析失败（长段落里冒出裸换行很常见）。"""
        last: LLMError | None = None
        for i in range(attempts):
            raw = self.chat(system, user,
                            temperature=temperature if i == 0 else min(0.4, temperature),
                            max_tokens=max_tokens)
            cleaned = _strip_fence(raw)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:
                last = LLMError(
                    f"模型没有返回合法 JSON（第 {i + 1} 次尝试）：{exc}\n"
                    f"原文片段: {cleaned[:300]}")
                time.sleep(0.6)
        raise last or LLMError("模型没有返回合法 JSON")


class MockLLM:
    """离线演示用：不发网络请求，用固定句式把目标词串成一篇可渲染的文章。"""

    model = "mock"

    def __init__(self, *_, **__):
        self.verbose = True

    def json(self, system: str, user: str, temperature: float = 0.8) -> dict:
        words = re.search(r"Target words \(\d+\) — every one must appear:\n(.+?)\n", user)
        targets = [w.strip() for w in (words.group(1) if words else "").split(",") if w.strip()]
        return mock_article(targets, chapter=self._chapter(user))

    @staticmethod
    def _chapter(user: str) -> int:
        m = re.search(r"chapter (\d+)", user)
        return int(m.group(1)) if m else 1

    def chat(self, *a, **k):
        raise NotImplementedError


# ---------------------------------------------------------------- 生成流程

def _dedupe(words: list[str]) -> list[str]:
    seen, out = set(), []
    for w in words:
        n = norm(w)
        if n and n not in seen:
            seen.add(n)
            out.append(w.strip())
    return out


def generate_for_day(gen, words: list[str], per_article: int = 20, level: str = "B1 (CET-4)",
                     topic: str | None = None, review_words: list[str] | None = None,
                     paragraphs: int | None = None,
                     log=lambda *a, **k: None) -> list[dict]:
    """把一天的词切成若干篇，逐篇生成并校验。返回 article dict 列表。

    per_article >= 词数时就是「一篇」，篇幅会按词数自动放大。
    """
    words = _dedupe(words)
    review_words = _dedupe(review_words or [])
    groups = chunk(words, max(8, per_article))
    articles = []
    for idx, group in enumerate(groups, 1):
        note = f"{idx}/{len(groups)}"
        paras, per_para, total = shape_for(len(group), paragraphs)
        log(f"  · 第 {idx}/{len(groups)} 篇：{len(group)} 个目标词 · "
            f"{paras} 段 / {total[0]}-{total[1]} 词")
        t0 = time.time()
        # 输出预算：正文 + 每个词的释义，词多时 JSON 会很长，给小了会被截断
        budget = min(7500, max(3000, 800 + len(group) * 42 + int(total[1] * 1.4)))
        try:
            art = gen.json(
                SYSTEM,
                build_user_prompt(group, review_words=review_words, topic=topic, level=level,
                                  paragraphs=paras, total_words=total, per_para=per_para,
                                  series_note=note if len(groups) > 1 else None),
                temperature=0.85,
                max_tokens=budget,
            )
        except Exception as exc:  # 单篇失败不该毁掉整天
            log(f"    ✗ 这篇生成失败，跳过：{exc}")
            continue
        missing = missing_words(art, group)
        attempts = 0
        while missing and attempts < 2:
            attempts += 1
            log(f"    漏词 {len(missing)} 个 → 第 {attempts} 次补词：{', '.join(missing[:8])}")
            try:
                art = gen.json(PATCH_SYSTEM, build_patch_prompt(missing, art, level),
                               temperature=0.45)
            except Exception as exc:  # 补词失败不致命，保留原稿
                log(f"    补词失败（保留原稿）：{exc}")
                break
            missing = missing_words(art, group)

        art = _finalize(art, group, review_words)
        art["stats"] = {
            "targets": len(group),
            "missing": missing,
            "coverage": round(coverage(art, group), 3),
            "words": len(article_text(art).split()),
            "seconds": round(time.time() - t0, 1),
        }
        log(f"    覆盖 {art['stats']['coverage']:.0%} · {art['stats']['words']} 词 · "
            f"{art['stats']['seconds']}s")
        articles.append(art)
    if not articles:
        raise RuntimeError("这一批一篇都没生成成功，看看上面的报错")
    return articles


def infer_used(paragraphs: list[str], target: str) -> dict | None:
    """在正文里找出 target 的首次出现，返回 {target, form, sentence}。"""
    text = " ".join(paragraphs)
    sentences = re.split(r"(?<=[.!?])\s+", text)
    forms = sorted(word_forms(target), key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(f) for f in forms) + r")\b", re.IGNORECASE)
    for sent in sentences:
        m = pattern.search(sent)
        if m:
            return {"target": target, "form": m.group(0), "sentence": sent.strip()}
    return None


def _finalize(art: dict, targets: list[str], review_words: list[str]) -> dict:
    """补齐缺省字段，规范大小写，保证渲染层永远有东西可画。"""
    art.setdefault("title", "Untitled")
    art.setdefault("title_cn", "")
    art.setdefault("logline", "")
    paras = art.get("paragraphs") or []
    if isinstance(paras, str):
        paras = [p.strip() for p in paras.split("\n") if p.strip()]
    art["paragraphs"] = [str(p).strip() for p in paras if str(p).strip()]

    target_set = {norm(t) for t in targets}
    review_set = {norm(t) for t in review_words} - target_set

    used = []
    for u in art.get("used") or []:
        if isinstance(u, dict) and u.get("target"):
            u["target"] = u["target"].strip()
            used.append(u)
    # 模型漏报 used 时，从正文里反查例句，保证阅读器一定有可点的例句和挖空题
    have = {norm(u["target"]) for u in used}
    for t in list(targets) + list(review_words):
        if norm(t) in have:
            continue
        guess = infer_used(art["paragraphs"], t)
        if guess:
            used.append(guess)
            have.add(norm(t))
    art["used"] = used

    gloss_map = {}
    for g in art.get("glosses") or []:
        if isinstance(g, dict) and g.get("word"):
            key = norm(g["word"])
            gloss_map[key] = {
                "word": g["word"],
                "ipa": g.get("ipa", ""),
                "pos": g.get("pos", ""),
                "cn": g.get("cn", ""),
            }
    # 没给释义的目标词补占位，避免点击时空白
    for t in list(targets) + list(review_words):
        k = norm(t)
        if k and k not in gloss_map:
            gloss_map[k] = {"word": t, "ipa": "", "pos": "", "cn": "（未返回释义）"}
    art["glosses"] = gloss_map
    art["targets"] = list(targets)
    art["review_words"] = [w for w in review_words if norm(w) in review_set]
    return art


def mock_article(targets: list[str], chapter: int = 1) -> dict:
    """确定性假数据，只用于 `--mock` 演示 HTML 效果。"""
    templates = [
        "Mira kept a small notebook in which she would {w} every name she heard.",
        "The old keeper did not {w} the rule, though everyone else did.",
        "By the third night, the sound of the tide began to {w} into her dreams.",
        "She would {w} the lamp at dusk and wait for the ferry to answer.",
        "Nobody could {w} why the bell rang at exactly four in the morning.",
        "He had learned to {w} the silence between two questions.",
    ]
    used, paragraphs, glosses = [], [], []
    paras: list[list[str]] = [[]]
    for i, w in enumerate(targets):
        base = templates[i % len(templates)]
        sent = base.format(w=w)
        used.append({"target": w, "form": w, "sentence": sent})
        glosses.append({"word": w, "ipa": "", "pos": "", "cn": "（示例释义，接入模型后为真实释义）"})
        if len(paras[-1]) >= 5:
            paras.append([])
        paras[-1].append(sent)
    for p in paras:
        paragraphs.append(" ".join(p))
    return {
        "title": f"The Keeper's Notebook ({chapter})",
        "title_cn": "守灯人的笔记本",
        "logline": "海雾里的第七个夜晚，她决定不再等待。",
        "paragraphs": paragraphs,
        "used": used,
        "glosses": glosses,
    }
