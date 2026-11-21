"""阅读器渲染：把 article dict 变成一份可离线打开的手机端 HTML。

零依赖、零 CDN、可断网阅读、可发到微信里直接点开。
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime

from generator import norm, word_forms

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

_CSS = """
:root{
  --paper:#fbf8f3; --ink:#211f1b; --muted:#8a8175; --line:#e7dfd2;
  --accent:#2f6f73; --accent-soft:rgba(47,111,115,.10);
  --hl:#0f6b52; --hl-bg:rgba(47,160,120,.16);
  --rv:#9a8f7c; --card:#ffffff; --shadow:0 10px 30px rgba(40,32,20,.10);
  --fs:18px;
}
@media (prefers-color-scheme: dark){
  :root{ --paper:#161513; --ink:#eae6dd; --muted:#9a9184; --line:#302d27;
    --accent:#7fc4c0; --accent-soft:rgba(127,196,192,.12);
    --hl:#8fd6b4; --hl-bg:rgba(90,190,150,.18); --rv:#8d8477;
    --card:#22201c; --shadow:0 10px 30px rgba(0,0,0,.45); }
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--paper); color:var(--ink);
  font-family:"Georgia","Iowan Old Style","Times New Roman",serif;
  font-size:var(--fs); line-height:1.95;
  padding:0 0 120px;
}
.wrap{max-width:660px;margin:0 auto;padding:26px 20px 0}
.top{display:flex;justify-content:space-between;align-items:center;gap:12px;
  font-family:ui-sans-serif,system-ui,"PingFang SC","Microsoft YaHei",sans-serif;
  font-size:12.5px;color:var(--muted);letter-spacing:.04em}
.kicker{text-transform:uppercase}
h1{font-size:1.72em;line-height:1.32;margin:14px 0 6px;letter-spacing:-.01em}
h1 .cn{display:block;font-family:ui-sans-serif,system-ui,"PingFang SC",sans-serif;
  font-size:.44em;font-weight:400;color:var(--muted);margin-top:10px;letter-spacing:.06em}
.logline{font-family:ui-sans-serif,system-ui,"PingFang SC",sans-serif;
  font-size:.82em;color:var(--muted);margin:0 0 18px;line-height:1.75}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 22px;
  font-family:ui-sans-serif,system-ui,"PingFang SC",sans-serif;font-size:11.5px}
.chip{border:1px solid var(--line);border-radius:99px;padding:3px 10px;color:var(--muted);
  background:var(--card)}
.chip b{color:var(--accent);font-weight:600}
hr.rule{border:0;border-top:1px solid var(--line);margin:0 0 26px}
p.para{margin:0 0 1.35em;text-align:justify;hyphens:auto}
p.zh{display:none;margin:-.8em 0 1.5em;padding-left:12px;border-left:2px solid var(--line);
  color:var(--muted);font-size:.86em;line-height:1.75;
  font-family:ui-sans-serif,system-ui,"PingFang SC","Microsoft YaHei",sans-serif}
body.show-zh p.zh{display:block}
.w{cursor:pointer;border-bottom:2px solid var(--hl-bg);border-radius:3px;
  padding:0 1px;background:var(--hl-bg);color:var(--hl);font-weight:600}
.w:active{background:var(--accent);color:var(--paper)}
.w.rv{background:transparent;border-bottom:1.5px dashed var(--rv);color:inherit;
  font-weight:500;font-style:italic}
.w.rv:active{background:var(--rv);color:var(--paper)}
.wp{cursor:pointer;border-radius:3px}
.wp:hover{background:var(--accent-soft)}
.wp:active{background:var(--accent);color:var(--paper)}
.tools{position:sticky;top:0;z-index:5;display:flex;gap:8px;align-items:center;flex-wrap:wrap;
  padding:8px 20px;background:color-mix(in srgb,var(--paper) 88%,transparent);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--line);
  font-family:ui-sans-serif,system-ui,"PingFang SC",sans-serif;font-size:12px;color:var(--muted)}
.tools button,.tools a.tbtn{border:1px solid var(--line);background:var(--card);color:var(--ink);
  border-radius:8px;padding:5px 10px;font-size:12px;cursor:pointer;line-height:1.2;
  text-decoration:none;display:inline-block}
.tools button:hover,.tools a.tbtn:hover{border-color:var(--accent);color:var(--accent)}
.tools .grow{flex:1}
section.block{margin:44px 0 0;font-family:ui-sans-serif,system-ui,"PingFang SC",sans-serif}
section.block h2{font-size:13px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin:0 0 14px;
  display:flex;align-items:center;gap:10px}
section.block h2::after{content:"";flex:1;height:1px;background:var(--line)}
table.gloss{width:100%;border-collapse:collapse;font-size:13.5px;line-height:1.6}
table.gloss td{padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top}
table.gloss td.wd{font-family:"Georgia",serif;font-size:15px;font-weight:600;white-space:nowrap;
  color:var(--hl)}
table.gloss td.ph{font-size:11.5px;color:var(--muted);white-space:nowrap}
table.gloss td.cn{color:var(--ink);opacity:.9}
.qitem{margin:0 0 14px;font-size:14.5px;line-height:2.1}
.qitem .idx{color:var(--muted);font-size:11px;margin-right:6px}
input.blank{font-family:inherit;font-size:14px;width:7.2em;border:0;border-bottom:1.5px solid var(--accent);
  background:transparent;color:var(--accent);text-align:center;padding:1px 4px;outline:none}
input.blank.ok{border-color:#2f9e6e;color:#2f9e6e}
input.blank.bad{border-color:#c0503a;color:#c0503a;text-decoration:line-through}
.bank{display:flex;flex-wrap:wrap;gap:6px;margin:4px 0 18px}
.bank span{border:1px solid var(--line);border-radius:6px;padding:3px 9px;font-size:12.5px;
  color:var(--muted);background:var(--card)}
.bank span.used{opacity:.35;text-decoration:line-through}
.score{font-size:13px;color:var(--muted);margin-left:10px}
footer{margin:56px 0 0;padding:22px 0 0;border-top:1px solid var(--line);
  font-family:ui-sans-serif,system-ui,"PingFang SC",sans-serif;font-size:11.5px;
  color:var(--muted);line-height:1.9}
.sheet{position:fixed;left:0;right:0;bottom:0;z-index:20;background:var(--card);
  border-top:1px solid var(--line);border-radius:18px 18px 0 0;box-shadow:var(--shadow);
  padding:18px 22px calc(20px + env(safe-area-inset-bottom));
  font-family:ui-sans-serif,system-ui,"PingFang SC",sans-serif;
  transform:translateY(105%);transition:transform .22s cubic-bezier(.2,.7,.3,1);max-width:660px;
  margin:0 auto}
.sheet.open{transform:translateY(0)}
.sheet .row{display:flex;align-items:baseline;gap:10px}
.sheet .w-en{font-family:"Georgia",serif;font-size:22px;font-weight:600;color:var(--hl)}
.sheet .w-ipa{font-size:13px;color:var(--muted)}
.sheet .w-pos{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:4px;
  padding:0 5px}
.sheet .w-cn{font-size:14.5px;margin:10px 0 0;line-height:1.7}
.sheet .w-sent{font-family:"Georgia",serif;font-size:13.5px;color:var(--muted);
  margin:10px 0 0;line-height:1.7;border-left:2px solid var(--line);padding-left:12px}
.sheet .bar{display:flex;gap:8px;margin-top:16px}
.sheet .bar button{flex:1;border:1px solid var(--line);background:var(--paper);color:var(--ink);
  border-radius:10px;padding:10px;font-size:13px;cursor:pointer}
.sheet .bar button.primary{border-color:var(--accent);color:var(--accent);font-weight:600}
.hidden{display:none !important}
@media print{
  @page{ size:A4; margin:16mm 15mm 18mm; }
  html,body{background:#fff !important;color:#000 !important}
  body{font-size:10.8pt;line-height:1.75;padding:0}
  .tools,.sheet,.bank,section.block.test,#progress,nav{display:none !important}
  .wrap{max-width:none;padding:0}
  h1{font-size:20pt;margin:0 0 4pt}
  h1 .cn{font-size:9pt;margin-top:4pt}
  .logline{font-size:9pt;margin-bottom:10pt}
  .chips{display:none}
  hr.rule{display:none}
  p.para{margin:0 0 9pt;text-align:left;page-break-inside:auto;orphans:3;widows:3}
  .w{background:transparent !important;border:0 !important;color:#000 !important;
    font-weight:700;text-decoration:underline;text-underline-offset:2px}
  .wp{background:transparent !important;color:inherit}
  section.block{margin-top:14pt;page-break-inside:auto}
  section.block h2{font-size:8pt;color:#666}
  table.gloss td{padding:3pt 4pt;font-size:9pt}
  table.gloss td.wd{color:#000;font-size:10pt}
  footer{margin-top:16pt;font-size:8pt;color:#666}
  a{color:#000;text-decoration:none}
}
@media print{ .hidden{display:none !important} }
"""

_JS = r"""
const DATA = __DATA__;
const STANDALONE = __STANDALONE__;
const sheet = document.getElementById('sheet');
const SYN = window.speechSynthesis || null;

async function api(path, body){
  const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'},
                               body: JSON.stringify(body || {})});
  if(!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}
function showSheet(d){
  document.getElementById('s-word').textContent = d.word || '';
  document.getElementById('s-ipa').textContent = d.ipa || '';
  document.getElementById('s-pos').textContent = d.pos || '';
  document.getElementById('s-cn').textContent = d.cn || '';
  document.getElementById('s-sent').textContent = d.sentence ? '“' + d.sentence + '”' : '';
  document.getElementById('s-sent').classList.toggle('hidden', !d.sentence);
  sheet.dataset.word = d.word || '';
  sheet.dataset.sentence = d.sentence || '';
  sheet.classList.add('open');
}
function openWord(key){
  const d = DATA.words[key];
  if(d) showSheet(d);
}
async function openPlain(word, sentence){
  const known = DATA.words[word];
  if(known){ showSheet(known); return; }
  if(STANDALONE){
    showSheet({word: word, cn: '静态页面：只带目标词释义，其他词需要本地服务才能查', sentence: sentence});
    return;
  }
  showSheet({word: word, cn: '查询中…', sentence: sentence});
  try{
    const r = await api('/api/lookup', {word: word, sentence: sentence});
    if(sheet.dataset.word === word){
      showSheet({word: word, ipa: r.ipa, pos: r.pos,
                 cn: r.cn, sentence: sheet.dataset.sentence});
    }
  }catch(e){
    if(sheet.dataset.word === word){
      showSheet({word: word, cn: '查询失败：' + e.message, sentence: sheet.dataset.sentence});
    }
  }
}
function sentenceAround(text, word){
  const i = text.indexOf(word);
  if(i < 0) return text.slice(0, 220).trim();
  let s = i; while(s > 0 && '.!?'.indexOf(text[s-1]) < 0) s--;
  let e = i + word.length; while(e < text.length && '.!?'.indexOf(text[e]) < 0) e++;
  if(e < text.length) e++;
  return text.slice(s, e).trim();
}
sheet.addEventListener('click', e => { if(e.target === sheet) closeSheet(); });
document.addEventListener('click', e => {
  const t = e.target.closest('.w, .wp');
  if(!t) return;
  e.stopPropagation();
  if(t.classList.contains('w')){
    openWord(t.dataset.t);
  }else{
    const para = t.closest('p');
    const sent = para ? sentenceAround(para.textContent, t.textContent) : '';
    openPlain(t.dataset.w, sent);
  }
});
function closeSheet(){ sheet.classList.remove('open'); }
document.getElementById('speak-word').addEventListener('click', () => speak(sheet.dataset.word));
document.getElementById('speak-sent').addEventListener('click', () => {
  if(sheet.dataset.sentence) speak(sheet.dataset.sentence, .92);
});
function speak(text, rate){
  if(!SYN || !text) return;
  SYN.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = 'en-US'; u.rate = rate || .9;
  const v = SYN.getVoices().find(v => /en[-_]US/i.test(v.lang)) || SYN.getVoices().find(v => /^en/i.test(v.lang));
  if(v) u.voice = v;
  SYN.speak(u);
}
document.getElementById('speak-all').addEventListener('click', () => {
  speak(DATA.paragraphs.join(' '), .88);
  document.getElementById('speak-all').textContent = '■ 停止';
  setTimeout(() => document.getElementById('speak-all').textContent = '🔊 朗读全文', 1200);
});
let fs = 18;
document.getElementById('fs-up').addEventListener('click', () => {
  fs = Math.min(26, fs + 1); document.documentElement.style.setProperty('--fs', fs + 'px');
});
document.getElementById('fs-down').addEventListener('click', () => {
  fs = Math.max(15, fs - 1); document.documentElement.style.setProperty('--fs', fs + 'px');
});

/* 全文翻译 */
let zhLoaded = false, zhShown = false;
const zhBtn = document.getElementById('zh-btn');
function injectZh(list){
  document.querySelectorAll('p.para').forEach((p, i) => {
    const t = list[i];
    if(!t) return;
    const d = document.createElement('p');
    d.className = 'zh';
    d.textContent = t;
    p.insertAdjacentElement('afterend', d);
  });
}
if(zhBtn){
  zhBtn.addEventListener('click', async () => {
    if(!zhLoaded){
      zhBtn.textContent = '翻译中…';
      try{
        const r = await api('/api/translate', {day: DATA.day, index: DATA.index});
        injectZh(r.paragraphs || []);
        zhLoaded = true;
      }catch(e){
        zhBtn.textContent = '译全文';
        alert('翻译失败：' + e.message);
        return;
      }
    }
    zhShown = !zhShown;
    document.body.classList.toggle('show-zh', zhShown);
    zhBtn.textContent = zhShown ? '隐藏译文' : '译全文';
  });
}

/* 挖空自测 */
document.querySelectorAll('.qitem').forEach(item => {
  const input = item.querySelector('input.blank');
  const ans = (item.dataset.answer || '').toLowerCase();
  const alt = (item.dataset.alt || '').toLowerCase();
  input.addEventListener('input', () => {
    const v = input.value.trim().toLowerCase();
    input.classList.remove('ok','bad');
    if(v.length >= 2){
      if(v === ans || v === alt) input.classList.add('ok');
      else if(v.length >= ans.length - 1) input.classList.add('bad');
    }
  });
});
document.getElementById('check').addEventListener('click', () => {
  let ok = 0, total = 0;
  document.querySelectorAll('.qitem').forEach(item => {
    const input = item.querySelector('input.blank');
    const v = input.value.trim().toLowerCase();
    if(!v) return;
    total++;
    const good = v === (item.dataset.answer||'').toLowerCase() || v === (item.dataset.alt||'').toLowerCase();
    input.classList.remove('ok','bad');
    input.classList.add(good ? 'ok' : 'bad');
    if(good) ok++;
  });
  document.getElementById('score').textContent = total ? `答对 ${ok} / ${total}` : '先填几个空试试';
});

/* 阅读进度 */
const bar = document.getElementById('progress');
window.addEventListener('scroll', () => {
  const h = document.documentElement.scrollHeight - window.innerHeight;
  bar.style.width = (h > 0 ? Math.min(100, window.scrollY / h * 100) : 0) + '%';
}, {passive:true});
"""


def _highlight(paragraph: str, form_map: dict[str, str], target_set: set[str],
               review_set: set[str]) -> str:
    """目标词高亮，其余单词也包一层 span——点任意词都能查。"""
    out, last = [], 0
    for m in _WORD_RE.finditer(paragraph):
        out.append(html.escape(paragraph[last:m.start()]))
        word = m.group(0)
        key = form_map.get(word.lower())
        if key in target_set:
            out.append(f'<span class="w" data-t="{html.escape(key)}">{html.escape(word)}</span>')
        elif key in review_set:
            out.append(f'<span class="w rv" data-t="{html.escape(key)}">{html.escape(word)}</span>')
        elif len(word) >= 2:
            out.append(f'<span class="wp" data-w="{html.escape(word.lower())}">{html.escape(word)}</span>')
        else:
            out.append(html.escape(word))
        last = m.end()
    out.append(html.escape(paragraph[last:]))
    return "".join(out)


def _quiz_block(used: list[dict]) -> str:
    rows = []
    seen: set[str] = set()
    for u in used:
        if len(rows) >= 10:
            break
        sentence = (u.get("sentence") or "").strip()
        form = (u.get("form") or u.get("target") or "").strip()
        target = (u.get("target") or "").strip()
        if not sentence or not form or sentence in seen:
            continue
        seen.add(sentence)
        m = re.search(rf"\b{re.escape(form)}\b", sentence, re.IGNORECASE)
        if not m:
            continue
        before = html.escape(sentence[:m.start()])
        after = html.escape(sentence[m.end():])
        answer = html.escape(m.group(0))
        rows.append(
            f'<div class="qitem" data-answer="{answer}" data-alt="{html.escape(target)}">'
            f'<span class="idx">{len(rows) + 1:02d}</span>{before}'
            f'<input class="blank" type="text" autocomplete="off" autocapitalize="off" '
            f'spellcheck="false" size="10">{after}</div>'
        )
    if not rows:
        return ""
    bank = "".join(f"<span>{html.escape((u.get('target') or ''))}</span>" for u in used[:10])
    return (
        '<section class="block test"><h2>Read again, then fill the blanks</h2>'
        f'<div class="bank">{bank}</div>{"".join(rows)}'
        '<div style="margin-top:14px"><button id="check" class="btn">检查</button>'
        '<span class="score" id="score"></span></div></section>'
    )


def _gloss_table(glosses: dict, targets: list[str]) -> str:
    rows = []
    for t in targets:
        g = glosses.get(norm(t)) or {}
        rows.append(
            "<tr>"
            f'<td class="wd">{html.escape(g.get("word") or t)}</td>'
            f'<td class="ph">{html.escape(g.get("ipa") or "")}</td>'
            f'<td class="ph">{html.escape(g.get("pos") or "")}</td>'
            f'<td class="cn">{html.escape(g.get("cn") or "")}</td>'
            "</tr>"
        )
    return ('<section class="block"><h2>Words in this chapter</h2>'
            f'<table class="gloss">{"".join(rows)}</table></section>')


def render_article(article: dict, day_label: str, index: int, total: int,
                   model: str = "", generated_at: str | None = None,
                   day_key: str | None = None, standalone: bool = False) -> str:
    targets = article.get("targets") or []
    review = article.get("review_words") or []
    glosses = article.get("glosses") or {}
    used = article.get("used") or []

    target_set = {norm(t) for t in targets}
    review_set = {norm(t) for t in review} - target_set

    form_map: dict[str, str] = {}
    sentence_map: dict[str, str] = {}
    for u in used:
        t = norm(u.get("target", ""))
        if not t:
            continue
        sentence_map[t] = u.get("sentence", "")
        for f in {norm(u.get("form", ""))} | {t}:
            if f:
                form_map[f] = t
    for t in list(target_set) + list(review_set):
        for f in word_forms(t):
            form_map.setdefault(f, t)

    paras_html = "".join(
        f'<p class="para">{_highlight(p, form_map, target_set, review_set)}</p>'
        for p in article.get("paragraphs") or []
    )

    words_js = {}
    for t in list(targets) + list(review):
        k = norm(t)
        g = glosses.get(k) or {}
        words_js[k] = {
            "word": g.get("word") or t,
            "ipa": g.get("ipa") or "",
            "pos": g.get("pos") or "",
            "cn": g.get("cn") or "",
            "sentence": sentence_map.get(k, ""),
        }
    data = {
        "title": article.get("title", ""),
        "paragraphs": article.get("paragraphs") or [],
        "words": words_js,
        "day": day_key or day_label,
        "index": index,
    }
    data_json = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    stats = article.get("stats") or {}
    cov = stats.get("coverage")
    cov_txt = f"{cov:.0%}" if isinstance(cov, (int, float)) else "—"

    page = _TEMPLATE
    repl = {
        "__CSS__": _CSS,
        "__JS__": _JS.replace("__DATA__", data_json),
        "__TITLE__": html.escape(article.get("title") or "Untitled"),
        "__TITLE_CN__": html.escape(article.get("title_cn") or ""),
        "__LOGLINE__": html.escape(article.get("logline") or ""),
        "__KICKER__": html.escape(f"{day_label} · Chapter {index}/{total}"),
        "__CHIPS__": "".join([
            f'<span class="chip"><b>{len(targets)}</b> 目标词</span>',
            f'<span class="chip"><b>{len(review)}</b> 复习词</span>',
            f'<span class="chip"><b>{stats.get("words", "—")}</b> 词篇幅</span>',
            f'<span class="chip">覆盖 <b>{cov_txt}</b></span>',
        ]),
        "__BODY__": paras_html,
        "__GLOSS__": _gloss_table(glosses, targets),
        "__QUIZ__": _quiz_block(used),
        "__FOOT__": html.escape(
            f"{model or 'unknown model'} · 生成于 "
            f"{generated_at or datetime.now().strftime('%Y-%m-%d %H:%M')} · 仅供个人学习"
        ),
        "__NEXT__": _next_link(index, total),
        "__EXPORT_LINK__": ("" if standalone else
                            f'<a class="tbtn" href="/export/{day_key or day_label}/{index:02d}.pdf"'
                            f' download>PDF</a>'),
        "__MD_LINK__": ("" if standalone else
                        f'<a class="tbtn" href="/export/{day_key or day_label}/{index:02d}.md"'
                        f' download>MD</a>'),
        "__ZH_BUTTON__": "" if standalone else '<button id="zh-btn">译全文</button>',
        "__STANDALONE__": "true" if standalone else "false",
    }
    for k, v in repl.items():
        page = page.replace(k, v)
    return page


def _next_link(index: int, total: int) -> str:
    parts = []
    if index > 1:
        parts.append(f'<a href="{index - 1:02d}.html">← 上一章</a>')
    if index < total:
        parts.append(f'<a href="{index + 1:02d}.html">下一章 →</a>')
    if not parts:
        return ""
    return ('<nav style="display:flex;justify-content:space-between;margin:26px 0 0;'
            'font-family:ui-sans-serif,system-ui;font-size:13px">'
            + "".join(parts) + "</nav>")


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#fbf8f3">
<title>__TITLE__</title>
<style>__CSS__</style>
</head>
<body>
<div id="progress" style="position:fixed;top:0;left:0;height:2px;width:0;background:var(--accent);z-index:30;transition:width .1s"></div>
<div class="tools">
  <button id="fs-down">A−</button><button id="fs-up">A+</button>
  <button id="speak-all">🔊 朗读全文</button>
  <span class="grow"></span>
  __ZH_BUTTON__
  __EXPORT_LINK__
  __MD_LINK__
</div>
<div class="wrap">
  <div class="top"><span class="kicker">__KICKER__</span><span>墨墨 · 每日一文</span></div>
  <h1>__TITLE__<span class="cn">__TITLE_CN__</span></h1>
  <p class="logline">__LOGLINE__</p>
  <div class="chips">__CHIPS__</div>
  <hr class="rule">
  __BODY__
  __NEXT__
  __QUIZ__
  __GLOSS__
  <footer>__FOOT__<br>点击高亮单词查看释义 · 生词来自墨墨开放 API</footer>
</div>

<div class="sheet" id="sheet">
  <div class="row">
    <span class="w-en" id="s-word"></span>
    <span class="w-ipa" id="s-ipa"></span>
    <span class="w-pos" id="s-pos"></span>
  </div>
  <p class="w-cn" id="s-cn"></p>
  <p class="w-sent" id="s-sent"></p>
  <div class="bar">
    <button id="speak-word">🔊 读单词</button>
    <button id="speak-sent">🔊 读例句</button>
    <button onclick="document.getElementById('sheet').classList.remove('open')">关闭</button>
  </div>
</div>
<script>__JS__</script>
</body>
</html>
"""
