"""配置读写：项目根目录的 .env + 进程环境变量。

网页设置页写的就是这个文件，所以不需要用户去碰环境变量。
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"

KEYS = ["MAIMEMO_TOKEN", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
        "LLM_JSON_MODE", "MOMO_MODE", "MOMO_PER", "MOMO_LEVEL", "MOMO_TOPIC",
        "MOMO_PASS", "MOMO_PUBLIC"]

DEFAULTS = {
    "LLM_BASE_URL": "https://api.deepseek.com/v1",
    "LLM_MODEL": "deepseek-chat",
    "LLM_JSON_MODE": "1",
    "MOMO_MODE": "single",   # single = 不管多少词都写成一篇
    "MOMO_PER": "20",        # split 模式下每篇多少个词
    "MOMO_LEVEL": "B1 (CET-4)",
}


def _read(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip().strip('"').strip("'")
    return data


def _read_file() -> dict[str, str]:
    return _read(ENV_PATH)


def load() -> dict[str, str]:
    """环境变量优先，其次 .env，最后默认值。"""
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in _read_file().items() if v})
    for k in KEYS:
        v = os.environ.get(k)
        if v:
            cfg[k] = v
    return cfg


def save(updates: dict[str, str]) -> dict[str, str]:
    """只改动给出的键，保留 .env 里的注释和顺序。"""
    return save_file(ENV_PATH, updates)


def _clean(updates: dict[str, str]) -> dict[str, str]:
    return {k: (v or "") for k, v in updates.items() if k in KEYS}


def save_file(path: Path, updates: dict[str, str]) -> dict[str, str]:
    """把配置写进任意配置文件（公网模式下每个访客一份）。"""
    lines: list[str] = []
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    pending = _clean(updates)
    seen = set()
    out: list[str] = []
    for raw in lines:
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in pending:
                out.append(f"{k}={pending[k]}")
                seen.add(k)
                continue
        out.append(raw)
    for key, val in pending.items():
        if key not in seen:
            if out and out[-1].strip():
                out.append("")
            out.append(f"{key}={val}")

    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    if path == ENV_PATH:
        for key, val in pending.items():
            if val:
                os.environ[key] = val
            else:
                os.environ.pop(key, None)
    return load_file(path)


def load_file(path: Path) -> dict[str, str]:
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in _read(path).items() if v})
    if path == ENV_PATH:
        for k in KEYS:
            v = os.environ.get(k)
            if v:
                cfg[k] = v
    return cfg


def masked(value: str | None, keep: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "•" * len(value)
    return f"{value[:keep]}…{value[-keep:]}"


def status(cfg: dict[str, str] | None = None) -> dict:
    cfg = cfg or load()
    token = cfg.get("MAIMEMO_TOKEN", "")
    key = cfg.get("LLM_API_KEY", "")
    return {
        "token_set": bool(token),
        "token_hint": masked(token),
        "llm_key_set": bool(key),
        "llm_key_hint": masked(key),
        "base_url": cfg.get("LLM_BASE_URL", ""),
        "model": cfg.get("LLM_MODEL", ""),
        "mode": cfg.get("MOMO_MODE") or "single",
        "per": cfg.get("MOMO_PER", "20"),
        "level": cfg.get("MOMO_LEVEL", ""),
        "pass_set": bool(cfg.get("MOMO_PASS")),
        "ready": bool(token and key),
    }
