"""墨墨背单词开放 API 最小客户端 —— 只用 Python 标准库。

官方文档：https://open.maimemo.com/document
Agent 技能参考：https://github.com/maimemo/memo-skills

Token 获取（二选一，推荐第一种）：
  1. App 内：墨墨背单词 → 我的 → 开放 API → 复制 Token
  2. 网页：打开 https://open.maimemo.com/open/api/v1/tokens/openapi
     登录后复制；网页来源的 Token 有效期 7 天

注意：
  * 学习数据类接口（/study/*）目前是 Beta，需要 App 内开启「自动同步」；
  * 限流 20 次/10s、40 次/60s、2000 次/5h，脚本已做 429 退避。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

BASE_URL = "https://open.maimemo.com/open/api/v1"


class MomoError(RuntimeError):
    pass


class MomoClient:
    def __init__(self, token: str | None = None, base_url: str = BASE_URL):
        self.token = (token or os.environ.get("MAIMEMO_TOKEN", "")).strip()
        if not self.token:
            raise MomoError(
                "缺少 MAIMEMO_TOKEN。请在墨墨 App 的「开放 API」里复制 Token，"
                "然后 set MAIMEMO_TOKEN=xxxx（PowerShell）或写进 .env。"
            )
        self.base_url = base_url.rstrip("/")

    # ---------- 底层 ----------
    def _request(self, method: str, path: str, payload=None, retries: int = 3):
        url = f"{self.base_url}{path}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "momo-daily/0.1",
        }
        last = None
        for attempt in range(retries):
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read().decode("utf-8") or "{}"
                    return self._unwrap(raw, path)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "ignore")
                if exc.code == 429:
                    time.sleep(2 + attempt * 3)
                    last = MomoError(f"429 限流: {detail}")
                    continue
                if exc.code in (401, 403):
                    raise MomoError(
                        "Token 无效或已过期（网页版 Token 只有 7 天）。请重新获取并更新 MAIMEMO_TOKEN。"
                        f" 服务器返回: {detail}"
                    ) from exc
                raise MomoError(f"HTTP {exc.code} on {path}: {detail}") from exc
            except urllib.error.URLError as exc:
                last = MomoError(f"网络错误 on {path}: {exc}")
                time.sleep(1 + attempt)
        raise last or MomoError(f"{path} 调用失败")

    @staticmethod
    def _unwrap(raw: str, path: str) -> dict:
        """真实响应是 {errors, data, success} 信封，业务数据在 data 里。

        官方文档的示例省略了这层包装，直接照着写会永远拿到空列表。
        """
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MomoError(f"{path} 返回的不是 JSON: {raw[:200]}") from exc
        if not isinstance(payload, dict):
            return {"value": payload}
        if payload.get("success") is False:
            errors = payload.get("errors") or []
            msg = "; ".join(str(e.get("msg") or e) for e in errors) or "请求失败"
            raise MomoError(f"{path} 失败：{msg}")
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload

    def post(self, path: str, payload=None):
        return self._request("POST", path, payload if payload is not None else {})

    def get(self, path: str):
        return self._request("GET", path)

    # ---------- 学习数据 ----------
    def today_items(self, is_new: bool | None = None, is_finished: bool | None = None,
                    limit: int = 1000) -> list[dict]:
        payload: dict = {"limit": min(limit, 1000)}
        if is_new is not None:
            payload["is_new"] = is_new
        if is_finished is not None:
            payload["is_finished"] = is_finished
        data = self.post("/study/get_today_items", payload)
        return data.get("today_items") or []

    def progress(self) -> dict:
        return self.post("/study/get_study_progress", {}).get("progress") or {}

    def today_new_words(self, limit: int = 1000) -> list[str]:
        """今日新学单词拼写（按学习顺序）。"""
        items = sorted(self.today_items(is_new=True, limit=limit), key=lambda x: x.get("order", 0))
        return [i.get("voc_spelling") for i in items if i.get("voc_spelling")]

    def today_words(self, limit: int = 1000) -> list[str]:
        """今日要过的全部词：新学 + 复习，新词排前面。

        墨墨每天的「新学」经常是 0（当天全是复习），只取新词会导致空手而归。
        """
        items = sorted(self.today_items(limit=limit), key=lambda x: x.get("order", 0))
        new = [i for i in items if i.get("is_new")]
        rest = [i for i in items if not i.get("is_new")]
        return [i.get("voc_spelling") for i in new + rest if i.get("voc_spelling")]

    def today_forgotten_words(self, limit: int = 1000) -> list[str]:
        """今日点了「忘记」的单词——最适合优先编进文章。"""
        items = self.today_items(is_finished=True, limit=limit)
        return [i.get("voc_spelling") for i in items
                if i.get("voc_spelling") and i.get("first_response") == "FORGET"]

    # ---------- 词库 ----------
    def resolve_ids(self, spellings: list[str]) -> dict[str, str]:
        """spelling -> voc_id，批量解析（单次上限 1000）。"""
        mapping: dict[str, str] = {}
        for i in range(0, len(spellings), 500):
            batch = spellings[i:i + 500]
            data = self.post("/vocabulary/query", {"spellings": batch})
            for voc in data.get("voc") or []:
                if voc.get("spelling"):
                    mapping[voc["spelling"].lower()] = voc["id"]
        return mapping

    # ---------- 回写 ----------
    def add_phrase(self, voc_id: str, sentence: str, translation: str = "",
                   origin: str = "自编-AI") -> dict:
        payload = {
            "phrase": {
                "voc_id": voc_id,
                "phrase": sentence,
                "interpretation": translation,
                "tags": ["词典"],
                "origin": origin,
            }
        }
        return self.post("/phrases", payload)

    def create_notepad(self, title: str, words: list[str], brief: str = "",
                       chapter: str = "Day") -> dict:
        content = f"# {chapter}\n" + "\n".join(words)
        payload = {
            "notepad": {
                "title": title[:40],
                "brief": (brief or "由 momo-daily 自动生成的每日词汇本")[:80],
                "content": content,
                "tags": ["AI每日"],
                "status": "UNPUBLISHED",
            }
        }
        return self.post("/notepads", payload)
