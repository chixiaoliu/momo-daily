"""网页界面：一个总览页 + 一个设置页。纯手写 HTML/CSS，不依赖任何前端框架。"""
from __future__ import annotations

import html

# 难度档位：左边是写给模型的（CEFR + 考试名），右边是给人看的
LEVELS = [
    ("A2 (初中)", "A2 · 初中 / 会考"),
    ("B1 (CET-4)", "B1 · 大学四级 CET-4"),
    ("B2 (CET-6)", "B2 · 大学六级 CET-6"),
    ("B2 (考研)", "B2 · 考研英语"),
    ("B2 (IELTS 6.0)", "B2 · 雅思 6.0"),
    ("C1 (IELTS 7.0)", "C1 · 雅思 7.0 / 托福 100"),
    ("C1 (GRE)", "C1 · GRE"),
]


def _level_select(current: str) -> str:
    known = {v for v, _ in LEVELS}
    items = []
    if current and current not in known:      # 手填过的老值，原样保留
        items.append((current, f"{current}（自定义）"))
    items.extend(LEVELS)
    return "".join(
        f'<option value="{html.escape(v)}"{" selected" if v == current else ""}>'
        f'{html.escape(label)}</option>'
        for v, label in items
    )

_CSS = """
:root{
  --paper:#fbf8f3; --ink:#211f1b; --muted:#8a8175; --line:#e7dfd2;
  --accent:#2f6f73; --accent-ink:#1f4f52; --warn:#b46b2a; --ok:#2f7d5d;
  --card:#fff; --shadow:0 1px 2px rgba(40,32,20,.04),0 8px 24px rgba(40,32,20,.06);
}
@media (prefers-color-scheme:dark){
  :root{ --paper:#161513; --ink:#eae6dd; --muted:#9a9184; --line:#302d27;
    --accent:#7fc4c0; --accent-ink:#a8dad6; --warn:#e0a86a; --ok:#7fcaa8;
    --card:#22201c; --shadow:0 1px 2px rgba(0,0,0,.3),0 8px 24px rgba(0,0,0,.35); }
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:ui-sans-serif,system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
.topbar{display:flex;align-items:center;justify-content:space-between;
  padding:16px 22px;border-bottom:1px solid var(--line);position:sticky;top:0;
  background:color-mix(in srgb,var(--paper) 92%,transparent);backdrop-filter:blur(8px);z-index:9}
.brand{font-size:15px;font-weight:650;letter-spacing:.02em}
.brand span{color:var(--accent);margin:0 1px}
.nav{display:flex;gap:16px;font-size:13px;color:var(--muted)}
.nav a{color:var(--muted)} .nav a:hover{color:var(--accent)}
main{max-width:680px;margin:0 auto;padding:26px 20px 80px}
.hero{padding:6px 0 22px;border-bottom:1px solid var(--line)}
.date{font-size:12px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
h1{font-size:23px;margin:8px 0 6px;letter-spacing:-.01em;font-weight:640}
.sub{color:var(--muted);font-size:13.5px;margin:0}
.actions{display:flex;gap:10px;margin-top:18px;flex-wrap:wrap}
button{font:inherit;cursor:pointer;border-radius:10px;padding:10px 18px;font-size:13.5px;
  border:1px solid transparent;transition:.15s}
button.primary{background:var(--accent);color:#fff;font-weight:600}
button.primary:hover{background:var(--accent-ink)}
button.ghost{background:transparent;border-color:var(--line);color:var(--ink)}
button.ghost:hover{border-color:var(--accent);color:var(--accent)}
button:disabled{opacity:.45;cursor:not-allowed}
.banner{margin:18px 0 0;padding:13px 16px;border-radius:12px;font-size:13px;line-height:1.7;
  border:1px solid var(--line);background:var(--card)}
.banner.warn{border-color:color-mix(in srgb,var(--warn) 40%,var(--line));
  background:color-mix(in srgb,var(--warn) 7%,var(--card))}
.banner.ok{border-color:color-mix(in srgb,var(--ok) 35%,var(--line))}
.banner b{font-weight:650}
.chapters{margin-top:26px;display:grid;gap:10px}
.chead{display:flex;align-items:baseline;justify-content:space-between;margin:0 0 2px}
.chead h2,.history h2{font-size:12px;letter-spacing:.12em;text-transform:uppercase;
  color:var(--muted);font-weight:600;margin:26px 0 12px}
.card{display:block;padding:15px 17px;border:1px solid var(--line);border-radius:13px;
  background:var(--card);box-shadow:var(--shadow);color:inherit}
.card:hover{border-color:var(--accent);transform:translateY(-1px)}
.card:active{transform:none}
.card .t{font-family:Georgia,"Times New Roman",serif;font-size:16.5px;font-weight:600;
  display:flex;gap:8px;align-items:baseline}
.card .t .n{font-family:ui-sans-serif,system-ui;font-size:11px;color:var(--muted);font-weight:500}
.card .m{font-size:12.5px;color:var(--muted);margin-top:5px;display:flex;gap:12px;flex-wrap:wrap}
.card .cn{font-size:12px;color:var(--muted);margin-top:2px}
.tag{display:inline-block;font-size:11px;padding:1px 7px;border-radius:99px;
  border:1px solid var(--line);color:var(--muted)}
.tag.demo{border-color:var(--warn);color:var(--warn)}
.history .day{display:flex;justify-content:space-between;padding:9px 2px;
  border-bottom:1px solid var(--line);font-size:13.5px}
.history .day a{display:flex;gap:10px;align-items:baseline}
.history .day .cnt{color:var(--muted);font-size:12px}
.progress{margin:20px 0 0;padding:16px 18px;border:1px solid var(--line);border-radius:14px;
  background:var(--card);box-shadow:var(--shadow)}
.progress .hd{display:flex;align-items:center;gap:10px;font-size:13px;font-weight:600}
.spinner{width:14px;height:14px;border-radius:50%;border:2px solid var(--line);
  border-top-color:var(--accent);animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.log{margin:12px 0 0;max-height:220px;overflow:auto;font-family:ui-monospace,Consolas,monospace;
  font-size:11.5px;line-height:1.75;color:var(--muted);white-space:pre-wrap}
label{display:block;font-size:12.5px;color:var(--muted);margin:18px 0 6px}
input,select{width:100%;font:inherit;font-size:14px;padding:10px 12px;border-radius:10px;
  border:1px solid var(--line);background:var(--card);color:var(--ink);outline:none}
input:focus{border-color:var(--accent)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.note{font-size:12px;color:var(--muted);margin:6px 0 0;line-height:1.75}
.steps{counter-reset:s;padding:0;margin:10px 0 0;list-style:none;font-size:12.5px;
  color:var(--muted);line-height:1.9}
.steps li{counter-increment:s;padding-left:22px;position:relative}
.steps li::before{content:counter(s);position:absolute;left:0;top:2px;width:16px;height:16px;
  border:1px solid var(--line);border-radius:50%;font-size:10px;display:flex;
  align-items:center;justify-content:center;color:var(--muted)}
pre.out{margin:14px 0 0;padding:12px 14px;border-radius:10px;border:1px solid var(--line);
  background:var(--paper);font-size:12px;line-height:1.7;white-space:pre-wrap;color:var(--muted)}
footer{margin-top:46px;padding-top:16px;border-top:1px solid var(--line);
  font-size:11.5px;color:var(--muted)}
.datebar{display:flex;gap:8px;align-items:center;margin:14px 0 18px;flex-wrap:wrap}
.datebar input[type=date]{width:auto;padding:7px 10px;font-size:13px;border-radius:9px;
  font-family:inherit;color:var(--ink)}
.qchip{font-size:12px;padding:6px 11px;border:1px solid var(--line);border-radius:99px;
  color:var(--muted);text-decoration:none}
.qchip:hover{border-color:var(--accent);color:var(--accent)}
.qchip.on{border-color:var(--accent);color:var(--accent);
  background:color-mix(in srgb,var(--accent) 9%,transparent)}
.tag.hist{border-color:var(--warn);color:var(--warn)}
.month{font-size:12px;letter-spacing:.12em;color:var(--muted);margin:30px 0 12px;font-weight:600}
.dayblock{margin:0 0 20px}
.dayhead{display:flex;justify-content:space-between;align-items:baseline;margin:0 0 9px;
  font-size:13px}
.dayhead a{color:var(--ink);font-weight:600}
.dayhead a:hover{color:var(--accent)}
.dayhead span{color:var(--muted);font-size:11.5px}
.dayblock .card{margin-bottom:9px}
.more{display:inline-block;margin-top:12px;font-size:12.5px}
.opt{display:flex;gap:10px;align-items:flex-start;padding:12px 14px;border:1px solid var(--line);
  border-radius:12px;background:var(--card);cursor:pointer;font-size:13.5px;color:var(--ink)}
.opt:has(input:checked){border-color:var(--accent);
  background:color-mix(in srgb,var(--accent) 6%,var(--card))}
.opt input[type=radio]{width:auto;margin:3px 0 0;accent-color:var(--accent);flex:none}
.opt b{display:block;font-weight:620;font-size:13.5px}
.opt em{display:block;font-style:normal;color:var(--muted);font-size:12px;margin-top:3px}
.opt input[type=number]{width:62px;display:inline-block;padding:1px 6px;font-size:12.5px;
  margin:0 4px;border-radius:6px}
.seg{display:grid;gap:9px;margin-top:6px}
a.btn{display:inline-block;text-decoration:none;background:var(--accent);color:#fff;
  font-weight:600;border-radius:10px;padding:9px 16px;font-size:13px}
a.btn:hover{background:var(--accent-ink)}
.mini{color:var(--accent);border-bottom:1px dotted var(--accent);font-size:11.5px}
.hidden{display:none !important}
@media (max-width:420px){ h1{font-size:20px} .row2{grid-template-columns:1fr} }
"""

_JS_COMMON = """
async function api(path, body){
  const opt = body ? {method:'POST',headers:{'Content-Type':'application/json'},
                      body:JSON.stringify(body)} : {};
  const r = await fetch(path, opt);
  if(!r.ok){ throw new Error('HTTP ' + r.status + ' ' + (await r.text()).slice(0,200)); }
  return r.json();
}
function el(id){ return document.getElementById(id); }
"""

_JS_DASH = """
const SEL_DATE = '__SEL__';
const HAS_ART = __HAS__;
let polling = null;
function setBusy(on){
  el('gen').disabled = on; el('demo').disabled = on;
  el('progress').classList.toggle('hidden', !on && !polling);
}
function renderLog(lines){
  const box = el('log');
  box.textContent = lines.join('\\n');
  box.scrollTop = box.scrollHeight;
}
async function poll(){
  try{
    const j = await api('/api/job');
    renderLog(j.log || []);
    if(j.state === 'running'){ return; }
    clearInterval(polling); polling = null;
    if(j.state === 'done'){
      if(j.meta && j.meta.source === 'demo'){ location.href = '/read/demo/01.html'; }
      else { setTimeout(()=>location.reload(), 500); }
    }
    else if(j.state === 'error'){ showError(j); }
    else { setBusy(false); }
  }catch(e){ /* 网络抖动忽略 */ }
}
function showError(j){
  setBusy(false);
  el('progress').classList.remove('hidden');
  el('phd').textContent = '上次生成失败';
  const sp = el('progress').querySelector('.spinner');
  if(sp) sp.classList.add('hidden');
  renderLog([].concat(j.log || [], '', '✗ ' + (j.error || '未知错误')));
}
async function start(mode){
  if(mode === 'api' && el('gen').dataset.ready === '0'){
    location.href = '/setup';
    return;
  }
  if(mode === 'api' && HAS_ART && !confirm(SEL_DATE + ' 已经有文章了，重新生成会覆盖，继续？')){
    return;
  }
  try{
    setBusy(true);
    el('progress').classList.remove('hidden');
    el('phd').textContent = '生成中，别关页面…';
    el('log').textContent = '正在启动…';
    const r = await api('/api/generate', {mode, date: SEL_DATE});
    if(!r.started){ renderLog([r.message || '已有任务在跑']); return; }
    if(!polling){ polling = setInterval(poll, 1200); }
  }catch(e){
    setBusy(false);
    renderLog(['✗ ' + e.message]);
  }
}
if(el('gen')) el('gen').onclick = () => start('api');
if(el('demo')) el('demo').onclick = () => start('demo');
if(el('day')) el('day').onchange = (e) => {
  if(e.target.value) location.href = '/?date=' + e.target.value;
};
(async () => {
  try{
    const j = await api('/api/job');
    if(j.state === 'running'){
      el('progress').classList.remove('hidden');
      polling = setInterval(poll, 1200);
      renderLog(j.log || []);
    } else if(j.state === 'error'){
      showError(j);
    }
  }catch(e){}
})();
"""

_JS_SETUP = """
function curMode(){
  const r = document.querySelector('input[name=mode]:checked');
  return r ? r.value : 'single';
}
function syncMode(){
  const split = curMode() === 'split';
  const per = el('per');
  if(per) per.disabled = !split;
}
document.querySelectorAll('input[name=mode]').forEach(r => r.addEventListener('change', syncMode));
syncMode();

el('save').onclick = async () => {
  const mode = curMode();
  const body = {
    MAIMEMO_TOKEN: el('token').value.trim(),
    LLM_API_KEY: el('key').value.trim(),
    LLM_BASE_URL: el('base').value.trim(),
    LLM_MODEL: el('model').value.trim(),
    MOMO_MODE: mode,
    MOMO_LEVEL: el('level').value.trim(),
  };
  const passEl = el('pass');
  if(passEl){
    const pass = passEl.value.trim();
    if(pass) body.MOMO_PASS = pass;
  }
  if(mode === 'split'){
    let n = parseInt(el('per').value || '20', 10);
    if(isNaN(n) || n < 10) n = 10;
    if(n > 60) n = 60;
    el('per').value = n;
    body.MOMO_PER = String(n);
  }
  Object.keys(body).forEach(k => { if(!body[k]) delete body[k]; });
  el('msg').textContent = '保存中…';
  try{
    await api('/api/config', body);
    el('msg').textContent = '✓ 已保存（Token/Key 留空则保持不变）';
    el('token').value = ''; el('key').value = '';
    if(el('pass')) el('pass').value = '';
  }catch(e){ el('msg').textContent = '✗ ' + e.message; }
};
el('test').onclick = async () => {
  el('out').classList.remove('hidden');
  el('out').textContent = '测试中…（墨墨 + 模型，各一次调用）';
  try{
    const r = await api('/api/test', {});
    el('out').textContent = [
      (r.momo.ok ? '✓ 墨墨：' : '✗ 墨墨：') + r.momo.msg,
      (r.llm.ok ? '✓ 模型：' : '✗ 模型：') + r.llm.msg,
    ].join('\\n');
  }catch(e){ el('out').textContent = '✗ ' + e.message; }
};
"""


def _shell(title: str, body: str, js: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#fbf8f3">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
{body}
<script>{_JS_COMMON}{js}</script>
</body>
</html>"""


def _topbar() -> str:
    return """<div class="topbar">
  <div class="brand">momo<span>·</span>daily</div>
  <div class="nav"><a href="/archive">归档</a><a href="/setup">设置</a></div>
</div>"""


def _chapter_card(a: dict, day: str, demo: bool) -> str:
    tag = '<span class="tag demo">样例</span>' if demo else ""
    cn = f'<div class="cn">{html.escape(a.get("title_cn") or "")}</div>' if a.get("title_cn") else ""
    return (
        f'<a class="card" href="/read/{day}/{a["file"]}">'
        f'<div class="t">{html.escape(a.get("title") or "Untitled")}{tag}</div>{cn}'
        f'<div class="m"><span>{a.get("targets", 0)} 个词</span>'
        f'<span>{a.get("words", 0)} 词</span>'
        f'<span>覆盖 {a.get("coverage", 0):.0%}</span></div></a>'
    )


def _qchip(label: str, href: str, active: bool = False) -> str:
    return f'<a class="{"qchip on" if active else "qchip"}" href="{href}">{label}</a>'


def dashboard(state: dict) -> str:
    st = state["cfg"]
    sel = state["selected"]
    is_today = state["is_today"]
    articles = state.get("articles") or []
    demo = state.get("demo_articles") or []

    if articles:
        worst = min((a.get("coverage") or 0) for a in articles)
        total = sum(a.get("words", 0) for a in articles)
        headline = f"{'今天' if is_today else '这天'}有 {len(articles)} 篇"
        subtext = f"{total} 词 · 最低覆盖 {worst:.0%} · 点开开始读"
        btn = "重新生成（覆盖）"
    elif is_today:
        headline = "今天还没有文章"
        subtext = "把今天背的词变成 5 篇连续短篇。"
        btn = "生成今天的文章"
    else:
        headline = "这天还没有生成文章"
        subtext = "点下面按钮，会从墨墨的学习记录里翻出这天新学的词。"
        btn = f"生成 {sel[5:]} 的文章"

    if not st["token_set"]:
        head = "还没配置墨墨 Token"
        tail = ('没有它就拿不到那天背了哪些词。'
                if not state.get("public")
                else '这是公共实例：填你自己的 Token 才能用。')
        banner = (f'<div class="banner warn"><b>{head}</b><br>{tail}'
                  '<a href="/setup">去设置 →</a></div>')
    elif not st["llm_key_set"]:
        banner = ('<div class="banner warn"><b>还没配置模型 Key</b><br>'
                  '生成文章需要一个大模型接口（DeepSeek 充 10 元够用很久）。'
                  '<a href="/setup">去设置 →</a></div>')
    else:
        plan = "一次一篇" if st.get("mode") != "split" else f"每篇 {st['per']} 词"
        banner = (f'<div class="banner ok">已就绪 · 模型 {html.escape(st["model"])} · '
                  f'{plan}</div>')

    hist_tag = "" if is_today else '<span class="tag hist">历史</span>'
    chips = (_qchip("今天", "/", is_today)
             + _qchip("昨天", f"/?date={state['yesterday']}", sel == state["yesterday"])
             + _qchip("前天", f"/?date={state['before']}", sel == state["before"]))

    chapters = "".join(_chapter_card(a, sel, False) for a in articles)
    if demo:
        chapters += ('<div class="chead" style="margin-top:22px"><h2>样例</h2></div>'
                     + "".join(_chapter_card(a, "demo", True) for a in demo))

    history = ""
    for d in state.get("history") or []:
        active = " style=\"color:var(--accent)\"" if d["date"] == sel else ""
        history += (f'<div class="day">'
                    f'<a href="/?date={d["date"]}"{active}><span>{d["date"]}</span>'
                    f'<span>{html.escape(d["title"])}</span></a>'
                    f'<span class="cnt">{d["count"]} 篇</span></div>')

    js = _JS_DASH.replace("__SEL__", sel).replace("__HAS__", "1" if articles else "0")

    body = f"""{_topbar()}
<main>
  <section class="hero">
    <div class="date">{state["selected_label"]} {hist_tag}</div>
    <div class="datebar">
      <input type="date" id="day" value="{sel}" max="{state["today"]}">
      {chips}
    </div>
    <h1>{headline}</h1>
    <p class="sub">{subtext}</p>
    <div class="actions">
      <button id="gen" class="primary" data-ready="{1 if st["ready"] else 0}">{btn}</button>
      <button id="demo" class="ghost">先看样例</button>
    </div>
  </section>
  {banner}
  <section id="progress" class="progress hidden">
    <div class="hd"><span class="spinner"></span><span id="phd">生成中，别关页面…</span></div>
    <div id="log" class="log"></div>
  </section>
  <section class="chapters">{chapters}</section>
  <section class="history"><h2>历史</h2>{history or '<div class="note">还没有记录</div>'}
    {'<a class="more" href="/archive">查看全部 →</a>' if history else ''}</section>
  <footer>词表来自墨墨官方开放 API · 仅供个人学习</footer>
</main>"""
    return _shell("momo·daily", body, js)


def login_page(error: bool = False) -> str:
    tip = '<p class="note" style="color:var(--warn)">口令不对，再试一次</p>' if error else ""
    body = f"""{_topbar()}
<main style="max-width:420px">
  <h1 style="font-size:20px;margin:6px 0 4px">需要口令</h1>
  <p class="sub">这个实例设置了访问口令。</p>
  <form method="post" action="/login">
    <label>访问口令</label>
    <input type="password" name="password" autofocus autocomplete="current-password"
           placeholder="在「设置」里填的那个">
    {tip}
    <div class="actions" style="margin-top:20px">
      <button class="primary" type="submit">进入</button>
    </div>
  </form>
</main>"""
    return _shell("口令 · momo·daily", body, "")


def archive(days: list[dict]) -> str:
    if not days:
        blocks = ('<div class="note">还没有生成过文章。'
                  '回<a href="/">首页</a>选一天开始。</div>')
        total = "0 天"
    else:
        total = f"{len(days)} 天 · {sum(d['count'] for d in days)} 篇"
        parts, cur = [], None
        for d in days:
            month = d["date"][:7]
            if month != cur:
                year, mon = month.split("-")
                parts.append(f'<div class="month">{year} 年 {int(mon)} 月</div>')
                cur = month
            cards = "".join(_chapter_card(a, d["date"], False) for a in d["articles"])
            parts.append(
                f'<div class="dayblock"><div class="dayhead">'
                f'<a href="/?date={d["date"]}">{d["date"]} {d.get("weekday", "")}</a>'
                f'<span>{d["count"]} 篇 · {d["words"]} 词 · '
                f'<a class="mini" href="/export/{d["date"]}.zip">导出 PDF</a></span></div>{cards}</div>')
        blocks = "".join(parts)

    body = f"""{_topbar()}
<main>
  <h1 style="font-size:20px;margin:6px 0 4px">归档</h1>
  <p class="sub">一共 {total}</p>
  <div class="actions" style="margin:14px 0 4px">
    <a class="btn" href="/export/all.zip">批量导出全部 PDF（ZIP）</a>
  </div>
  {blocks}
  <footer><a href="/">← 回首页</a></footer>
</main>"""
    return _shell("归档 · momo·daily", body, "")


def setup_page(state: dict) -> str:
    st = state["cfg"]
    public = state.get("public")
    token_ph = f"已设置 {html.escape(st['token_hint'])}，留空不修改" if st["token_set"] else "粘贴 Token"
    key_ph = f"已设置 {html.escape(st['llm_key_hint'])}，留空不修改" if st["llm_key_set"] else "sk-…"
    pass_ph = "已设置，留空不修改" if st.get("pass_set") else "不设置就留空"

    if public:
        intro = ("公共实例：填你自己的墨墨 Token 和模型 Key。它们只保存在这台服务器上属于你这次访问的空间里，"
                 "不会和别人的混在一起；换浏览器或清 Cookie 后需要重新填。")
        pass_block = ""
        foot = "你的 Token / Key 只写进你这次的会话目录，站长看不到内容，也不会用你的额度"
    else:
        intro = "填一次，之后每天点一个按钮就行。密钥只写在本机的 .env 里。"
        pass_block = f"""<label>访问口令（可选）</label>
  <input id="pass" type="password" placeholder="{pass_ph}" autocomplete="new-password">
  <p class="note">留空 = 不设口令，只有能连到你电脑的人打得开。要发布到公网（Cloudflare Tunnel 等）时
  <b>务必设置</b>——否则任何人点一下生成就烧你的模型额度，还能看到你的词表和文章。</p>"""
        foot = "Token / Key 不会上传到任何地方，只写进本机 .env"

    body = f"""{_topbar()}
<main>
  <h1 style="font-size:20px;margin:6px 0 4px">设置</h1>
  <p class="sub">{intro}</p>

  <label>墨墨开放 API Token</label>
  <input id="token" type="password" placeholder="{token_ph}" autocomplete="off" spellcheck="false">
  <ol class="steps">
    <li>打开墨墨背单词 App</li>
    <li>我的 → 开放 API</li>
    <li>复制 Token 粘贴到上面</li>
  </ol>
  <p class="note">网页版也能取（<a href="https://open.maimemo.com/open/api/v1/tokens/openapi" target="_blank">open.maimemo.com</a>），
  但只有 7 天有效期；App 里的更耐久。需要 App 内开启「自动同步」，否则学习数据是空的。</p>

  <label>模型 Key</label>
  <input id="key" type="password" placeholder="{key_ph}" autocomplete="off" spellcheck="false">
  <p class="note">DeepSeek 控制台 → API keys。也可以用任何 OpenAI 兼容服务。</p>

  {pass_block}

  <div class="row2">
    <div><label>接口地址</label>
      <input id="base" value="{html.escape(st['base_url'])}" spellcheck="false"></div>
    <div><label>模型名</label>
      <input id="model" value="{html.escape(st['model'])}" spellcheck="false"></div>
  </div>

  <label>生成方式</label>
  <div class="seg">
    <label class="opt">
      <input type="radio" name="mode" value="single" {"checked" if st.get("mode") != "split" else ""}>
      <span><b>一次生成一篇</b><em>默认。不管今天多少词，都写成同一个故事；词多时文章会自动变长</em></span>
    </label>
    <label class="opt">
      <input type="radio" name="mode" value="split" {"checked" if st.get("mode") == "split" else ""}>
      <span><b>按篇拆分</b><em>每篇
        <input id="per" type="number" min="10" max="60" value="{html.escape(st['per'])}"> 个词（最少 10）</em></span>
    </label>
  </div>

  <label>难度</label>
  <select id="level">{_level_select(st['level'])}</select>
  <p class="note">只影响正文里<b>非目标词</b>的用词难度，词表本身不变。改完从下次生成开始生效。</p>

  <div class="actions" style="margin-top:26px">
    <button id="save" class="primary">保存</button>
    <button id="test" class="ghost">测试连接</button>
    <a href="/" class="ghost" style="padding:10px 18px;font-size:13.5px;border:1px solid var(--line);
       border-radius:10px;color:var(--ink)">返回</a>
  </div>
  <p class="note" id="msg"></p>
  <pre class="out hidden" id="out"></pre>
  <footer>{foot}</footer>
</main>"""
    return _shell("设置 · momo·daily", body, _JS_SETUP)
