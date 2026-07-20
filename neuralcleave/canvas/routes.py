"""Canvas REST endpoints, WebSocket subscription, and the canvas HTML page."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from neuralcleave.canvas.block import BLOCK_TYPES, CanvasBlock
from neuralcleave.canvas.renderer import CanvasRenderer

logger = logging.getLogger(__name__)

# REST endpoints — included under /api/v1 prefix in main.py
api_router = APIRouter(prefix="/canvas", tags=["Canvas"])

# WebSocket + HTML page — no prefix
page_router = APIRouter(tags=["Canvas"])

_renderer: CanvasRenderer | None = None


def set_canvas_renderer(r: CanvasRenderer | None) -> None:
    global _renderer
    _renderer = r


def get_canvas_renderer() -> CanvasRenderer | None:
    return _renderer


# ---------------------------------------------------------------------------
# REST — state / render / clear / status
# ---------------------------------------------------------------------------


@api_router.get("/state")
async def canvas_state() -> dict:
    """Return the current block list."""
    r = get_canvas_renderer()
    if r is None:
        return {"available": False, "blocks": [], "count": 0}
    return {"available": True, **r.get_state()}


@api_router.post("/render", status_code=201)
async def canvas_render(body: dict) -> dict:
    """Add a new block to the canvas."""
    from fastapi import HTTPException

    r = get_canvas_renderer()
    if r is None:
        raise HTTPException(status_code=503, detail="Canvas renderer not initialised")

    block_type = body.get("block_type", "")
    if block_type not in BLOCK_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown block_type {block_type!r}. Allowed: {sorted(BLOCK_TYPES)}",
        )

    content: Any = body.get("content", "")
    title: str = body.get("title", "")
    block = CanvasBlock.new(block_type, content, title)
    await r.add_block(block)
    return block.to_dict()


@api_router.delete("/clear", status_code=204)
async def canvas_clear() -> None:
    """Remove all blocks from the canvas."""
    from fastapi import HTTPException

    r = get_canvas_renderer()
    if r is None:
        raise HTTPException(status_code=503, detail="Canvas renderer not initialised")
    await r.clear()


@api_router.get("/status")
async def canvas_status() -> dict:
    """Return availability and subscriber + block counts."""
    r = get_canvas_renderer()
    if r is None:
        return {"available": False, "block_count": 0, "subscriber_count": 0}
    return {
        "available": True,
        "block_count": r.block_count(),
        "subscriber_count": r.subscriber_count(),
    }


# ---------------------------------------------------------------------------
# WebSocket — real-time canvas subscription
# ---------------------------------------------------------------------------


@page_router.websocket("/ws/canvas")
async def canvas_websocket(ws: WebSocket) -> None:
    """Real-time canvas subscription.

    On connect: client receives ``{"type": "state", "blocks": [...]}`` with the
    current canvas.

    Subsequent server → client events:
    - ``{"type": "add", "block": {...}}``
    - ``{"type": "clear"}``

    Client → server messages are ignored (read-only canvas).
    """
    await ws.accept()
    r = get_canvas_renderer()
    if r is None:
        await ws.send_text(json.dumps({"type": "error", "detail": "Canvas not available"}))
        await ws.close()
        return

    await r.subscribe(ws)
    try:
        while True:
            # Keep the connection alive; client messages are intentionally ignored
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("canvas websocket error: %s", exc)
    finally:
        r.unsubscribe(ws)


# ---------------------------------------------------------------------------
# HTML canvas page
# ---------------------------------------------------------------------------

_CANVAS_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>NeuralCleave Live Canvas</title>
<style>
:root {
  --bg: #f8f9fa; --surface: #fff; --border: #e0e3e8;
  --text: #1a1d23; --muted: #6b7280; --accent: #4f6ef7;
  --code-bg: #f1f3f7; --pre-text: #24292e;
  --header-bg: #fff; --shadow: 0 1px 4px rgba(0,0,0,.08);
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #0f1117; --surface: #1c1e26; --border: #2d3040;
    --text: #e4e6f0; --muted: #8b91a8; --accent: #6b8cff;
    --code-bg: #23263a; --pre-text: #c9d1d9;
    --header-bg: #16181f; --shadow: 0 1px 4px rgba(0,0,0,.4); }
}
:root[data-theme="dark"] { --bg: #0f1117; --surface: #1c1e26; --border: #2d3040;
  --text: #e4e6f0; --muted: #8b91a8; --accent: #6b8cff;
  --code-bg: #23263a; --pre-text: #c9d1d9;
  --header-bg: #16181f; --shadow: 0 1px 4px rgba(0,0,0,.4); }
:root[data-theme="light"] { --bg: #f8f9fa; --surface: #fff; --border: #e0e3e8;
  --text: #1a1d23; --muted: #6b7280; --accent: #4f6ef7;
  --code-bg: #f1f3f7; --pre-text: #24292e;
  --header-bg: #fff; --shadow: 0 1px 4px rgba(0,0,0,.08); }
*,*::before,*::after { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: var(--bg); color: var(--text); min-height: 100vh; }
header { position: sticky; top: 0; z-index: 10; background: var(--header-bg);
  border-bottom: 1px solid var(--border); box-shadow: var(--shadow);
  padding: 0 1.5rem; height: 52px; display: flex; align-items: center; gap: 1rem; }
header h1 { font-size: .95rem; font-weight: 600; letter-spacing: .01em; flex: 1; }
.badge { font-size: .7rem; padding: .2rem .5rem; border-radius: 999px;
  background: var(--accent); color: #fff; font-weight: 600; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: #6b7280; flex-shrink: 0; }
.dot.connected { background: #22c55e; }
button.clear-btn { font-size: .78rem; padding: .3rem .75rem; border-radius: 6px;
  border: 1px solid var(--border); background: var(--surface); color: var(--muted);
  cursor: pointer; transition: background .15s; }
button.clear-btn:hover { background: var(--code-bg); }
main { max-width: 860px; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
.empty { text-align: center; padding: 5rem 1rem; color: var(--muted); }
.empty svg { opacity: .3; margin-bottom: 1rem; }
.empty p { font-size: .9rem; }
.blocks { display: flex; flex-direction: column; gap: 1rem; }
.block { background: var(--surface); border: 1px solid var(--border);
  border-radius: 10px; overflow: hidden; box-shadow: var(--shadow); }
.block-header { padding: .55rem 1rem; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: .5rem; }
.block-type { font-size: .68rem; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: var(--accent); }
.block-title { font-size: .82rem; color: var(--muted); flex: 1; }
.block-ts { font-size: .67rem; color: var(--muted); font-variant-numeric: tabular-nums; }
.block-body { padding: 1rem; }
.block-body p { font-size: .9rem; line-height: 1.65; white-space: pre-wrap; }
.md-body { font-size: .9rem; line-height: 1.7; }
.md-body h1,.md-body h2,.md-body h3 { font-weight: 600; margin: .75rem 0 .4rem; }
.md-body h1 { font-size: 1.25rem; } .md-body h2 { font-size: 1.1rem; }
.md-body h3 { font-size: .95rem; }
.md-body p { margin-bottom: .6rem; }
.md-body ul,.md-body ol { padding-left: 1.4rem; margin-bottom: .6rem; }
.md-body li { margin-bottom: .2rem; font-size: .9rem; }
.md-body code { font-family: "SF Mono", Consolas, monospace; font-size: .82rem;
  background: var(--code-bg); padding: .1rem .3rem; border-radius: 4px; }
.md-body pre { background: var(--code-bg); padding: .8rem 1rem; border-radius: 6px;
  overflow-x: auto; margin: .5rem 0; }
.md-body pre code { background: none; padding: 0; }
pre.code-block { background: var(--code-bg); padding: .9rem 1rem; border-radius: 0;
  overflow-x: auto; color: var(--pre-text); font-size: .82rem;
  font-family: "SF Mono", Consolas, monospace; line-height: 1.55; }
.img-block img { max-width: 100%; border-radius: 6px; display: block; }
table.canvas-table { width: 100%; border-collapse: collapse; font-size: .85rem; }
table.canvas-table th { background: var(--code-bg); font-weight: 600;
  text-align: left; padding: .5rem .75rem; border-bottom: 2px solid var(--border); }
table.canvas-table td { padding: .45rem .75rem; border-bottom: 1px solid var(--border); }
table.canvas-table tr:last-child td { border-bottom: none; }
.table-wrap { overflow-x: auto; }
.chart-wrap { padding: .5rem 0; }
canvas.chart-canvas { max-width: 100%; }
.html-frame { width: 100%; border: none; min-height: 200px; }
</style>
</head>
<body>
<header>
  <span class="dot" id="dot"></span>
  <h1>NeuralCleave Live Canvas</h1>
  <span class="badge" id="badge">0</span>
  <button class="clear-btn" onclick="clearCanvas()">Clear</button>
</header>
<main id="main">
  <div class="empty" id="empty">
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <rect x="3" y="3" width="18" height="18" rx="3"/>
      <path d="M3 9h18M9 21V9"/>
    </svg>
    <p>Waiting for content…<br>Ask the AI to render something.</p>
  </div>
  <div class="blocks" id="blocks" style="display:none"></div>
</main>
<script>
const host = location.host;
const proto = location.protocol === 'https:' ? 'wss' : 'ws';
let ws, blocks = [];

function connect() {
  ws = new WebSocket(`${proto}://${host}/ws/canvas`);
  ws.onopen = () => { document.getElementById('dot').classList.add('connected'); };
  ws.onclose = () => {
    document.getElementById('dot').classList.remove('connected');
    setTimeout(connect, 3000);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'state') { blocks = msg.blocks || []; render(); }
    else if (msg.type === 'add') { blocks.push(msg.block); render(); }
    else if (msg.type === 'clear') { blocks = []; render(); }
  };
  setInterval(() => { if (ws.readyState === 1) ws.send('ping'); }, 25000);
}

function render() {
  document.getElementById('badge').textContent = blocks.length;
  const empty = document.getElementById('empty');
  const container = document.getElementById('blocks');
  if (!blocks.length) { empty.style.display = ''; container.style.display = 'none'; return; }
  empty.style.display = 'none'; container.style.display = '';
  container.innerHTML = blocks.map(b => blockHtml(b)).join('');
  container.querySelectorAll('canvas[data-chart]').forEach(drawChart);
}

function blockHtml(b) {
  const ts = b.created_at ? `<span class="block-ts">${b.created_at.replace('T',' ').replace('Z','')}</span>` : '';
  const hdr = `<div class="block-header"><span class="block-type">${esc(b.block_type)}</span><span class="block-title">${esc(b.title||'')}</span>${ts}</div>`;
  let body = '';
  const c = b.content;
  if (b.block_type === 'text') body = `<p>${esc(typeof c==='string'?c:JSON.stringify(c))}</p>`;
  else if (b.block_type === 'markdown') body = `<div class="md-body">${md(typeof c==='string'?c:'')}</div>`;
  else if (b.block_type === 'image') body = `<div class="img-block"><img src="${esc(typeof c==='string'?c:'')}" alt="${esc(b.title||'image')}"/></div>`;
  else if (b.block_type === 'table') body = tableHtml(c);
  else if (b.block_type === 'code') body = codeHtml(c);
  else if (b.block_type === 'chart') body = chartHtml(b.id, c);
  else if (b.block_type === 'html') body = `<iframe class="html-frame" srcdoc="${esc(typeof c==='string'?c:'')}" sandbox="allow-scripts"></iframe>`;
  return `<div class="block">${hdr}<div class="block-body">${body}</div></div>`;
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function md(s) {
  return s
    .replace(/^### (.+)$/gm,'<h3>$1</h3>')
    .replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^# (.+)$/gm,'<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,'<em>$1</em>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/^- (.+)$/gm,'<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, s => `<ul>${s}</ul>`)
    .replace(/\n\n+/g,'</p><p>')
    .replace(/^(?!<[h|u|o|l|p])(.+)$/gm,'<p>$1</p>');
}

function tableHtml(c) {
  if (!c || !c.headers) return '<p><em>Empty table</em></p>';
  const ths = c.headers.map(h=>`<th>${esc(h)}</th>`).join('');
  const trs = (c.rows||[]).map(r=>`<tr>${r.map(cell=>`<td>${esc(cell)}</td>`).join('')}</tr>`).join('');
  return `<div class="table-wrap"><table class="canvas-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table></div>`;
}

function codeHtml(c) {
  const code = typeof c === 'string' ? c : (c.code||'');
  return `<pre class="code-block">${esc(code)}</pre>`;
}

function chartHtml(id, c) {
  const data = JSON.stringify(c).replace(/"/g,'&quot;');
  return `<div class="chart-wrap"><canvas class="chart-canvas" id="chart-${esc(id)}" data-chart="${data}" width="700" height="300"></canvas></div>`;
}

function drawChart(canvas) {
  const c = JSON.parse(canvas.getAttribute('data-chart').replace(/&quot;/g,'"'));
  const ctx = canvas.getContext('2d');
  const labels = c.labels||[], vals = c.values||[];
  const type = c.chart_type||'bar';
  const W = canvas.width, H = canvas.height;
  const style = getComputedStyle(document.documentElement);
  const accent = style.getPropertyValue('--accent').trim()||'#4f6ef7';
  const text = style.getPropertyValue('--text').trim()||'#1a1d23';
  const border = style.getPropertyValue('--border').trim()||'#e0e3e8';
  ctx.clearRect(0,0,W,H);
  if (!vals.length) { ctx.fillStyle=text; ctx.fillText('No data',W/2,H/2); return; }
  if (type==='pie') { drawPie(ctx,W,H,labels,vals,accent); }
  else { drawBarLine(ctx,W,H,labels,vals,accent,text,border,type); }
}

function drawPie(ctx,W,H,labels,vals,accent) {
  const total = vals.reduce((a,b)=>a+b,0); if(!total)return;
  const cx=W/2,cy=H/2,r=Math.min(W,H)*0.38;
  const colors=['#4f6ef7','#22c55e','#f59e0b','#ef4444','#8b5cf6','#06b6d4','#f97316'];
  let start=-Math.PI/2;
  vals.forEach((v,i)=>{
    const slice=(v/total)*Math.PI*2;
    ctx.beginPath(); ctx.moveTo(cx,cy);
    ctx.arc(cx,cy,r,start,start+slice);
    ctx.closePath(); ctx.fillStyle=colors[i%colors.length]; ctx.fill();
    start+=slice;
  });
}

function drawBarLine(ctx,W,H,labels,vals,accent,text,border,type) {
  const pad={t:20,r:20,b:40,l:50};
  const cw=W-pad.l-pad.r, ch=H-pad.t-pad.b;
  const max=Math.max(...vals,1);
  ctx.strokeStyle=border; ctx.lineWidth=1;
  // axes
  ctx.beginPath(); ctx.moveTo(pad.l,pad.t); ctx.lineTo(pad.l,pad.t+ch); ctx.lineTo(pad.l+cw,pad.t+ch); ctx.stroke();
  ctx.fillStyle=text; ctx.font='11px sans-serif'; ctx.textAlign='right';
  [0,.25,.5,.75,1].forEach(f=>{
    const y=pad.t+ch-f*ch, v=Math.round(max*f);
    ctx.fillText(v,pad.l-4,y+4);
    ctx.strokeStyle=border; ctx.beginPath(); ctx.moveTo(pad.l,y); ctx.lineTo(pad.l+cw,y); ctx.stroke();
  });
  const bw=cw/(vals.length*1.5);
  ctx.textAlign='center';
  if(type==='bar') {
    vals.forEach((v,i)=>{
      const x=pad.l+(i+.25)*cw/vals.length, bh=(v/max)*ch;
      ctx.fillStyle=accent; ctx.fillRect(x,pad.t+ch-bh,bw,bh);
      ctx.fillStyle=text; ctx.fillText(labels[i]||'',x+bw/2,pad.t+ch+14);
    });
  } else {
    ctx.strokeStyle=accent; ctx.lineWidth=2; ctx.beginPath();
    vals.forEach((v,i)=>{
      const x=pad.l+(i+.5)*cw/vals.length, y=pad.t+ch-(v/max)*ch;
      i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
      ctx.fillStyle=text; ctx.fillText(labels[i]||'',x,pad.t+ch+14);
    });
    ctx.stroke();
    vals.forEach((v,i)=>{
      const x=pad.l+(i+.5)*cw/vals.length, y=pad.t+ch-(v/max)*ch;
      ctx.fillStyle=accent; ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2); ctx.fill();
    });
  }
}

function clearCanvas() {
  fetch('/api/v1/canvas/clear',{method:'DELETE'}).catch(()=>{});
}

connect();
</script>
</body>
</html>"""


@page_router.get("/canvas", response_class=HTMLResponse, include_in_schema=False)
async def canvas_page() -> HTMLResponse:
    """Serve the live canvas HTML page."""
    return HTMLResponse(content=_CANVAS_HTML)
