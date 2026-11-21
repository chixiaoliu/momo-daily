"""提示词模板：把当天的 20 个目标词写进一篇可读的短篇故事。

设计原则见 ../方案.md 第 4 节：
1. 目标词必须 100% 出现（允许变位/变形，词根不变）；
2. 密度受控——每句最多 2 个目标词，每段最多 5 个；
3. 句子短、场景具体，避免"为了塞词而造句"；
4. 输出严格 JSON，方便程序做覆盖校验。
"""

SYSTEM = """You are a senior graded-reader author. You write short, concrete, emotionally \
engaging stories for adult Chinese learners of English. The level given in the task \
(for example "B1 (CET-4)") is a hard ceiling for every word that is not a target word — \
if a target word is far above that level, still use it, but keep everything else simple.

Hard rules you must never break:
1. EVERY target word must appear at least once. Inflected forms are allowed and encouraged
   (abandon -> abandoned, abandon -> abandoning), but the word family must stay the same.
2. Density control: at most 2 target words in one sentence, never 3. Spread the target
   words evenly: each paragraph should carry roughly the number given in the request.
3. Sentences are short: 8-22 words. Prefer active voice and concrete nouns/verbs.
4. Never explain a word inside the story. No glosses, no parentheses, no "which means",
   and no meta-language such as "the word X" or "she thought about the word X".
   The target words must feel like they belong to the scene, not like vocabulary items.
5. The story must be ONE coherent narrative with a named protagonist, a place, and a
   turn of events. Not a list of unrelated example sentences.
6. Difficulty: use only common vocabulary for everything that is not a target word.
   Non-target sentences should be comfortable for a reader at the requested level.
7. Output JSON only. No markdown fence, no commentary.

Output schema:
{
  "title": "English title, <= 8 words",
  "title_cn": "中文标题",
  "logline": "一句中文概括，<= 30 字",
  "paragraphs": ["paragraph 1", "paragraph 2", ...],
  "glosses": [{"word": "abandon", "ipa": "/əˈbændən/", "pos": "v.", "cn": "放弃；抛弃"}]
}

`glosses` must contain one entry per target word, in the sense actually used in the story.
Do not output any other field — no per-word sentence lists, no commentary."""


def build_user_prompt(words, review_words=None, topic=None, level="B1 (CET-4)",
                      paragraphs=5, total_words=(360, 430), series_note=None,
                      per_para=None):
    """拼装单篇生成请求。"""
    review_words = review_words or []
    lines = []
    lines.append(f"Target words ({len(words)}) — every one must appear:")
    lines.append(", ".join(words))
    lines.append("")
    if review_words:
        lines.append(
            f"Recycled words from previous days ({len(review_words)}) — reuse them only if they "
            f"fit naturally, do NOT force them:"
        )
        lines.append(", ".join(review_words))
        lines.append("")
    lines.append(f"CEFR level: {level}")
    lines.append(f"Length: exactly {paragraphs} paragraphs, {total_words[0]}-{total_words[1]} words in total.")
    if per_para:
        lines.append(f"Distribution: about {per_para} target words per paragraph, spread evenly.")
    if series_note:
        lines.append(f"Continuity: this is chapter {series_note}. Keep the same protagonist and setting.")
    if topic:
        lines.append(f"Suggested theme (adapt freely if the words do not fit): {topic}")
    else:
        lines.append("Theme: your choice — prefer a small, concrete, slightly surprising everyday scene.")
    lines.append("")
    lines.append("Return the JSON object now.")
    return "\n".join(lines)


PATCH_SYSTEM = """You patch an existing short story so that a few missing target words get included.

Rules:
- Keep the existing story, characters and tone. You may rewrite at most one paragraph.
- Add 1 short paragraph at the end (2-4 sentences) if needed.
- At most 2 target words per sentence.
- Return JSON only, with the SAME schema as before: title, title_cn, logline, paragraphs, used, glosses.
- `paragraphs` must be the FULL, final list of paragraphs (not only the new one)."""


def build_patch_prompt(missing, article, level="B1 (CET-4)"):
    body = "\n\n".join(article.get("paragraphs", []))
    return (
        f"Missing target words that must be inserted: {', '.join(missing)}\n\n"
        f"CEFR level: {level}\n\n"
        f"Current story (title: {article.get('title','')}):\n{body}\n\n"
        "Rewrite/patch it so every missing word appears, then return the full JSON object. "
        "Reuse the `used` entries that are still valid and add one entry per newly inserted word."
    )
