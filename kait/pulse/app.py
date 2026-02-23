#!/usr/bin/env python3
"""Kait Pulse — inline FastAPI dashboard serving health, status, and ops endpoints."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import asdict
from pathlib import Path

# Ensure repo root is importable when running as a script.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(title="Kait Pulse", docs_url="/docs")

PULSE_PORT = int(os.environ.get("KAIT_PULSE_PORT", "8765"))


# ── HTML dashboard (root) ──────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(_DASHBOARD_HTML)


# ── /api/status — heartbeat / health probe ─────────────────────────
@app.get("/api/status")
async def api_status():
    result: dict = {"pulse": "ok", "timestamp": time.time()}
    try:
        from lib.service_control import service_status

        result["services"] = service_status(include_pulse_probe=False)
    except Exception:
        result["services"] = {}

    kaitd_healthy = False
    try:
        from lib.ports import KAITD_HEALTH_URL
        from urllib.request import urlopen

        with urlopen(KAITD_HEALTH_URL, timeout=2) as resp:  # noqa: S310
            kaitd_healthy = resp.status == 200
    except Exception:
        pass
    result["kaitd_healthy"] = kaitd_healthy
    return JSONResponse(result)


# ── /api/intelligence — consolidated metrics payload ───────────────
@app.get("/api/intelligence")
async def api_intelligence():
    payload: dict = {"timestamp": time.time()}

    # EIDOS metrics
    try:
        from lib.eidos.metrics import get_metrics_calculator

        calc = get_metrics_calculator()
        payload["eidos"] = calc.all_metrics()
    except Exception:
        payload["eidos"] = None

    # Aha tracker
    try:
        from lib.aha_tracker import get_aha_tracker

        tracker = get_aha_tracker()
        payload["aha"] = {
            "stats": tracker.get_stats(),
            "recent_surprises": tracker.get_recent_surprises(limit=5),
        }
    except Exception:
        payload["aha"] = None

    # Cognitive learner
    try:
        from lib.cognitive_learner import get_cognitive_learner

        learner = get_cognitive_learner()
        payload["cognitive"] = learner.get_stats()
    except Exception:
        payload["cognitive"] = None

    # Advisory engine
    try:
        from lib.advisory_engine import get_engine_status

        payload["advisory"] = get_engine_status()
    except Exception:
        payload["advisory"] = None

    return JSONResponse(payload)


# ── /api/queue — lightweight queue stats ───────────────────────────
@app.get("/api/queue")
async def api_queue():
    try:
        from lib.queue import get_queue_stats, count_events

        stats = get_queue_stats()
        return JSONResponse(stats)
    except Exception:
        return JSONResponse({"event_count": 0, "size_mb": 0, "needs_rotation": False})


# ── /api/mission — mission KPIs stub ───────────────────────────────
@app.get("/api/mission")
async def api_mission():
    return JSONResponse({"mission_kpis": []})


# ── /api/acceptance — acceptance board stub ─────────────────────────
@app.get("/api/acceptance")
async def api_acceptance():
    return JSONResponse({"acceptance_items": []})


# ── /api/ops — operational aggregates ──────────────────────────────
@app.get("/api/ops")
async def api_ops():
    services: dict = {}
    try:
        from lib.service_control import service_status

        services = service_status()
    except Exception:
        pass
    return JSONResponse({"services": services})


# ── Dashboard HTML ─────────────────────────────────────────────────

_DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Kait Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif&family=JetBrains+Mono:wght@300;400;500;600&display=swap" rel="stylesheet"/>
<style>
:root {
  --bg: #0e1016;
  --bg2: #151820;
  --bg3: #1c202a;
  --bg-card: #1a1e28;
  --text1: #e2e4e9;
  --text2: #9aa3b5;
  --text3: #6b7489;
  --border: #2a3042;
  --green: #00C49A;
  --green-glow: rgba(0,196,154,0.4);
  --green-dim: rgba(0,196,154,0.15);
  --orange: #D97757;
  --orange-glow: rgba(217,119,87,0.4);
  --gold: #c8a84e;
  --gold-glow: rgba(200,168,78,0.4);
  --gold-dim: rgba(200,168,78,0.15);
  --red: #FF4D4D;
  --purple: #9B59B6;
  --font-mono: 'JetBrains Mono', 'Consolas', monospace;
  --font-serif: 'Instrument Serif', Georgia, serif;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  background: var(--bg);
  color: var(--text1);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.5;
}

/* ── Grid Layout ───────────────────────── */
.shell {
  display: grid;
  grid-template-rows: 48px 1fr 36px;
  grid-template-columns: 280px 1fr 300px;
  height: 100vh;
  gap: 1px;
  background: var(--border);
}
.header {
  grid-column: 1 / -1;
  background: var(--bg2);
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 12px;
}
.header h1 {
  font-family: var(--font-serif);
  font-size: 20px;
  font-weight: 400;
  letter-spacing: 2px;
  color: var(--text1);
}
.header .status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--green);
  box-shadow: 0 0 6px var(--green-glow);
  transition: background 0.5s, box-shadow 0.5s;
}
.header .status-dot.warn {
  background: var(--orange);
  box-shadow: 0 0 6px var(--orange-glow);
}
.header .status-dot.err {
  background: var(--red);
  box-shadow: 0 0 6px rgba(255,77,77,0.4);
}
.header .spacer { flex: 1; }
.header .ts {
  font-size: 11px;
  color: var(--text3);
  transition: color 0.5s;
}
.header .ts.stale { color: var(--red); }

/* Panels */
.panel-left, .panel-right {
  background: var(--bg);
  overflow-y: auto;
  padding: 12px;
}
.panel-left::-webkit-scrollbar, .panel-right::-webkit-scrollbar { width: 4px; }
.panel-left::-webkit-scrollbar-thumb, .panel-right::-webkit-scrollbar-thumb {
  background: var(--border); border-radius: 2px;
}

.center {
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}
#avatar-canvas { width: 100%; height: 100%; display: block; }

.footer {
  grid-column: 1 / -1;
  background: var(--bg2);
  display: flex;
  align-items: center;
  padding: 0 20px;
  gap: 20px;
  font-size: 11px;
  color: var(--text3);
}
.footer .tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: var(--bg3);
  border-radius: 3px;
  color: var(--text2);
}

/* ── Cards ─────────────────────────────── */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 10px;
}
.card-title {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--text3);
  margin-bottom: 8px;
}

/* Service dots */
.svc-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.svc-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--text3);
  flex-shrink: 0;
  transition: background 0.4s, box-shadow 0.4s;
}
.svc-dot.up { background: var(--green); box-shadow: 0 0 4px var(--green-glow); }
.svc-dot.warn { background: var(--orange); box-shadow: 0 0 4px var(--orange-glow); }
.svc-dot.down { background: var(--red); box-shadow: 0 0 4px rgba(255,77,77,0.3); }
.svc-name { color: var(--text2); font-size: 11px; }

/* Big number */
.big-num {
  font-size: 32px;
  font-weight: 300;
  color: var(--green);
  line-height: 1.1;
}
.big-num.warn { color: var(--orange); }
.big-label { font-size: 10px; color: var(--text3); margin-top: 2px; }

/* Gauge bar */
.gauge { height: 6px; background: var(--bg3); border-radius: 3px; margin-top: 6px; overflow: hidden; }
.gauge-fill {
  height: 100%; border-radius: 3px;
  background: var(--green);
  transition: width 0.6s ease, background 0.4s;
}
.gauge-fill.warn { background: var(--orange); }
.gauge-fill.gold { background: var(--gold); }

/* Stat row */
.stat-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.stat-label { color: var(--text3); font-size: 11px; }
.stat-val { color: var(--text2); font-size: 11px; font-weight: 500; }
.stat-val.green { color: var(--green); }
.stat-val.orange { color: var(--orange); }
.stat-val.gold { color: var(--gold); }

/* Surprise feed */
.surprise-item {
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
}
.surprise-item:last-child { border-bottom: none; }
.surprise-type {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--gold);
  margin-bottom: 2px;
}
.surprise-detail { color: var(--text3); }

/* Bar chart */
.bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.bar-label { width: 80px; font-size: 10px; color: var(--text3); text-align: right; flex-shrink: 0; }
.bar-track { flex: 1; height: 5px; background: var(--bg3); border-radius: 2px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 2px; background: var(--green); transition: width 0.5s; }
.bar-val { width: 36px; font-size: 10px; color: var(--text2); }

/* Responsive */
@media (max-width: 900px) {
  .shell {
    grid-template-columns: 1fr;
    grid-template-rows: 48px auto auto auto 36px;
  }
  .panel-left, .panel-right { max-height: 40vh; }
}
</style>
</head>
<body>
<div class="shell">

  <!-- HEADER -->
  <div class="header">
    <div class="status-dot" id="hdr-dot"></div>
    <h1>KAIT INTELLIGENCE</h1>
    <div class="spacer"></div>
    <span class="ts" id="hdr-ts">--</span>
  </div>

  <!-- LEFT PANEL -->
  <div class="panel-left">

    <!-- Services -->
    <div class="card">
      <div class="card-title">Services</div>
      <div id="svc-list">
        <div class="svc-row"><div class="svc-dot" id="svc-kaitd"></div><span class="svc-name">kaitd</span></div>
        <div class="svc-row"><div class="svc-dot" id="svc-pulse"></div><span class="svc-name">pulse</span></div>
        <div class="svc-row"><div class="svc-dot" id="svc-bridge"></div><span class="svc-name">bridge</span></div>
        <div class="svc-row"><div class="svc-dot" id="svc-scheduler"></div><span class="svc-name">scheduler</span></div>
        <div class="svc-row"><div class="svc-dot" id="svc-watchdog"></div><span class="svc-name">watchdog</span></div>
      </div>
    </div>

    <!-- North Star -->
    <div class="card">
      <div class="card-title">North Star</div>
      <div class="big-num" id="ns-rate">--</div>
      <div class="big-label">compounding rate % (target: 40%)</div>
      <div class="gauge"><div class="gauge-fill" id="ns-gauge" style="width:0%"></div></div>
    </div>

    <!-- Memory Effectiveness -->
    <div class="card">
      <div class="card-title">Memory</div>
      <div class="stat-row"><span class="stat-label">with memory</span><span class="stat-val green" id="mem-with">--</span></div>
      <div class="stat-row"><span class="stat-label">without</span><span class="stat-val" id="mem-without">--</span></div>
      <div class="stat-row"><span class="stat-label">advantage</span><span class="stat-val gold" id="mem-adv">--</span></div>
    </div>

    <!-- Weekly -->
    <div class="card">
      <div class="card-title">This Week</div>
      <div class="stat-row"><span class="stat-label">episodes</span><span class="stat-val" id="wk-ep">--</span></div>
      <div class="stat-row"><span class="stat-label">success rate</span><span class="stat-val green" id="wk-sr">--</span></div>
      <div class="stat-row"><span class="stat-label">new heuristics</span><span class="stat-val" id="wk-heur">--</span></div>
      <div class="stat-row"><span class="stat-label">sharp edges</span><span class="stat-val" id="wk-se">--</span></div>
    </div>
  </div>

  <!-- CENTER: Avatar Canvas -->
  <div class="center">
    <canvas id="avatar-canvas"></canvas>
  </div>

  <!-- RIGHT PANEL -->
  <div class="panel-right">

    <!-- Surprises -->
    <div class="card">
      <div class="card-title">Surprises</div>
      <div class="stat-row"><span class="stat-label">total</span><span class="stat-val gold" id="aha-total">--</span></div>
      <div id="aha-feed"></div>
    </div>

    <!-- Cognitive -->
    <div class="card">
      <div class="card-title">Cognitive</div>
      <div class="stat-row"><span class="stat-label">total insights</span><span class="stat-val" id="cog-total">--</span></div>
      <div class="stat-row"><span class="stat-label">avg reliability</span><span class="stat-val green" id="cog-rel">--</span></div>
      <div id="cog-bars"></div>
    </div>

    <!-- Distillation -->
    <div class="card">
      <div class="card-title">Distillation</div>
      <div id="dist-bars"></div>
    </div>
  </div>

  <!-- FOOTER -->
  <div class="footer">
    <span class="tag" id="ft-events">events: --</span>
    <span class="tag" id="ft-queue">queue: --</span>
    <span class="tag" id="ft-rotation">rotation: --</span>
    <span class="spacer" style="flex:1"></span>
    <span id="ft-ts" style="color:var(--text3)">--</span>
  </div>

</div>

<script>
// ═════════════════════════════════════════════════════════
// Kait Pulse Dashboard — Canvas Avatar + Data Panels
// ═════════════════════════════════════════════════════════

const C = {
  bg:'#0e1016', bg2:'#151820', bg3:'#1c202a',
  green:'#00C49A', orange:'#D97757', gold:'#c8a84e',
  red:'#FF4D4D', purple:'#9B59B6',
  text1:'#e2e4e9', text2:'#9aa3b5', text3:'#6b7489',
};

// ── State ──────────────────────────────────────
let statusData = null, intelData = null, queueData = null;
let lastStatusOk = 0, lastIntelOk = 0, lastQueueOk = 0;
let connectionLost = false;
let avatarState = {
  healthRatio: 1,      // 0-1 how many services healthy
  eventRate: 0,        // events count for activity
  onTarget: false,     // compounding rate >= 40
  newAha: false,       // flash when new aha detected
  ahaFlashT: 0,
  prevAhaCount: -1,
};

// ── Polling ────────────────────────────────────
function fetchJSON(url) {
  return fetch(url).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); });
}

function pollStatus() {
  fetchJSON('/api/status').then(d => {
    statusData = d;
    lastStatusOk = Date.now();
    connectionLost = false;
    updateStatusUI(d);
  }).catch(() => {
    if (Date.now() - lastStatusOk > 15000) connectionLost = true;
  });
}

function pollQueue() {
  fetchJSON('/api/queue').then(d => {
    queueData = d;
    lastQueueOk = Date.now();
    updateQueueUI(d);
  }).catch(() => {});
}

function pollIntelligence() {
  fetchJSON('/api/intelligence').then(d => {
    intelData = d;
    lastIntelOk = Date.now();
    updateIntelUI(d);
  }).catch(() => {});
}

// Staggered start
setTimeout(pollStatus, 200);
setTimeout(pollQueue, 800);
setTimeout(pollIntelligence, 1500);
setInterval(pollStatus, 5000);
setInterval(pollQueue, 5000);
setInterval(pollIntelligence, 10000);

// ── Update Timestamp ───────────────────────────
function fmtTime(ts) {
  if (!ts) return '--';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
}

function updateTimestamps() {
  const now = Date.now();
  const hdrTs = document.getElementById('hdr-ts');
  const ftTs = document.getElementById('ft-ts');
  if (statusData) hdrTs.textContent = fmtTime(statusData.timestamp);
  if (connectionLost) {
    hdrTs.classList.add('stale');
    ftTs.style.color = C.red;
    ftTs.textContent = 'CONNECTION LOST';
  } else {
    hdrTs.classList.remove('stale');
    ftTs.style.color = C.text3;
    if (intelData) ftTs.textContent = 'updated ' + fmtTime(intelData.timestamp);
  }
}
setInterval(updateTimestamps, 1000);

// ── Status UI ──────────────────────────────────
function svcDotClass(svc) {
  if (!svc) return '';
  if (svc.healthy) return 'up';
  if (svc.running) return 'warn';
  return 'down';
}

function updateStatusUI(d) {
  const svcs = d.services || {};
  const map = {
    'svc-kaitd': svcs.kaitd,
    'svc-pulse': svcs.pulse,
    'svc-bridge': svcs.bridge_worker,
    'svc-scheduler': svcs.scheduler,
    'svc-watchdog': svcs.watchdog,
  };

  let up = 0, total = 0;
  for (const [id, svc] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (!el) continue;
    total++;
    el.className = 'svc-dot';
    if (!svc) { el.classList.add('down'); continue; }
    // watchdog / scheduler don't have "healthy" — treat running as up
    const isUp = svc.healthy || (svc.running && svc.healthy === undefined);
    if (isUp) { el.classList.add('up'); up++; }
    else if (svc.running) { el.classList.add('warn'); up += 0.5; }
    else { el.classList.add('down'); }
  }

  // Pulse is always running from our perspective
  const pulseDot = document.getElementById('svc-pulse');
  if (pulseDot && !pulseDot.classList.contains('up')) { pulseDot.className = 'svc-dot up'; up = Math.min(up + 1, total); }

  avatarState.healthRatio = total > 0 ? up / total : 1;

  // Header dot
  const hdrDot = document.getElementById('hdr-dot');
  if (avatarState.healthRatio >= 0.8) { hdrDot.className = 'status-dot'; }
  else if (avatarState.healthRatio >= 0.4) { hdrDot.className = 'status-dot warn'; }
  else { hdrDot.className = 'status-dot err'; }
}

// ── Queue UI ───────────────────────────────────
function updateQueueUI(d) {
  document.getElementById('ft-events').textContent = 'events: ' + (d.event_count ?? '--');
  document.getElementById('ft-queue').textContent = 'queue: ' + (d.size_mb ?? 0) + ' MB';
  document.getElementById('ft-rotation').textContent = 'rotation: ' + (d.needs_rotation ? 'needed' : 'ok');
  avatarState.eventRate = d.event_count || 0;
}

// ── Intelligence UI ────────────────────────────
function updateIntelUI(d) {
  // EIDOS
  if (d.eidos) {
    const ns = d.eidos.north_star || {};
    const rate = ns.compounding_rate_pct ?? 0;
    const el = document.getElementById('ns-rate');
    el.textContent = rate.toFixed(1) + '%';
    el.className = 'big-num' + (rate < 40 ? ' warn' : '');

    const gauge = document.getElementById('ns-gauge');
    gauge.style.width = Math.min(100, (rate / 40) * 100) + '%';
    gauge.className = 'gauge-fill' + (rate >= 40 ? ' gold' : rate < 20 ? ' warn' : '');
    avatarState.onTarget = rate >= 40;

    // Effectiveness
    const eff = d.eidos.effectiveness || {};
    const wm = eff.with_memory || {};
    const wom = eff.without_memory || {};
    document.getElementById('mem-with').textContent = (wm.rate_pct ?? '--') + '%';
    document.getElementById('mem-without').textContent = (wom.rate_pct ?? '--') + '%';
    document.getElementById('mem-adv').textContent = (eff.memory_advantage_pct != null ? (eff.memory_advantage_pct > 0 ? '+' : '') + eff.memory_advantage_pct + '%' : '--');

    // Weekly
    const wk = d.eidos.weekly || {};
    document.getElementById('wk-ep').textContent = wk.episodes ?? '--';
    document.getElementById('wk-sr').textContent = (wk.success_rate_pct ?? '--') + '%';
    document.getElementById('wk-heur').textContent = wk.new_heuristics ?? '--';
    document.getElementById('wk-se').textContent = wk.new_sharp_edges ?? '--';

    // Distillation
    const distArr = d.eidos.distillation_quality || [];
    const distEl = document.getElementById('dist-bars');
    distEl.innerHTML = '';
    if (distArr.length === 0) {
      distEl.innerHTML = '<div style="color:var(--text3);font-size:11px">no distillations yet</div>';
    }
    for (const dt of distArr) {
      const pct = dt.effectiveness_pct || 0;
      distEl.innerHTML += `<div class="bar-row"><span class="bar-label">${dt.type}</span><div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${pct>50?C.green:C.orange}"></div></div><span class="bar-val">${pct}%</span></div>`;
    }
  }

  // Aha
  if (d.aha) {
    const stats = d.aha.stats || {};
    const totalEl = document.getElementById('aha-total');
    const newTotal = stats.total_captured || stats.unique_moments || 0;
    totalEl.textContent = newTotal;

    // Flash detection
    if (avatarState.prevAhaCount >= 0 && newTotal > avatarState.prevAhaCount) {
      avatarState.newAha = true;
      avatarState.ahaFlashT = performance.now();
    }
    avatarState.prevAhaCount = newTotal;

    const feed = document.getElementById('aha-feed');
    const surprises = d.aha.recent_surprises || [];
    feed.innerHTML = '';
    if (surprises.length === 0) {
      feed.innerHTML = '<div style="color:var(--text3);font-size:11px">no surprises yet</div>';
    }
    for (const s of surprises.slice(0, 5)) {
      const type = (s.surprise_type || '').replace(/_/g, ' ');
      feed.innerHTML += `<div class="surprise-item"><div class="surprise-type">${type}${(s.occurrences||1)>1?' (x'+(s.occurrences)+')':''}</div><div class="surprise-detail">predicted: ${(s.predicted_outcome||'--').substring(0,60)}</div><div class="surprise-detail">actual: ${(s.actual_outcome||'--').substring(0,60)}</div></div>`;
    }
  }

  // Cognitive
  if (d.cognitive) {
    document.getElementById('cog-total').textContent = d.cognitive.total_insights ?? '--';
    const rel = d.cognitive.avg_reliability;
    document.getElementById('cog-rel').textContent = rel != null ? (rel * 100).toFixed(0) + '%' : '--';

    const cats = d.cognitive.by_category || {};
    const barsEl = document.getElementById('cog-bars');
    barsEl.innerHTML = '';
    const maxCat = Math.max(1, ...Object.values(cats));
    for (const [cat, count] of Object.entries(cats)) {
      const pct = (count / maxCat) * 100;
      barsEl.innerHTML += `<div class="bar-row"><span class="bar-label">${cat}</span><div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${C.green}"></div></div><span class="bar-val">${count}</span></div>`;
    }
    if (Object.keys(cats).length === 0) {
      barsEl.innerHTML = '<div style="color:var(--text3);font-size:11px">no insights yet</div>';
    }
  }
}

// ═════════════════════════════════════════════════════════
// Canvas AI Avatar
// ═════════════════════════════════════════════════════════

const canvas = document.getElementById('avatar-canvas');
const ctx = canvas.getContext('2d');
let W, H, cx, cy, coreR;

function resize() {
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * devicePixelRatio;
  canvas.height = rect.height * devicePixelRatio;
  W = canvas.width; H = canvas.height;
  cx = W / 2; cy = H / 2;
  coreR = Math.min(W, H) * 0.15;
  initParticles();
  initNeuralLines();
}
window.addEventListener('resize', resize);

// ── Particles ──────────────────────────────────
let particles = [];
function initParticles() {
  particles = [];
  const count = 80 + Math.floor(Math.random() * 40);
  for (let i = 0; i < count; i++) {
    particles.push({
      x: Math.random() * W,
      y: Math.random() * H,
      vx: (Math.random() - 0.5) * 0.3,
      vy: (Math.random() - 0.5) * 0.3,
      r: 1 + Math.random() * 2,
      color: [C.green, C.gold, C.orange][Math.floor(Math.random() * 3)],
      alpha: 0.2 + Math.random() * 0.4,
    });
  }
}

function drawParticles(t) {
  for (const p of particles) {
    p.x += p.vx; p.y += p.vy;
    if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
    if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
    const flicker = 0.7 + 0.3 * Math.sin(t * 0.001 + p.x * 0.01);
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fillStyle = p.color;
    ctx.globalAlpha = p.alpha * flicker;
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

// ── Neural Lines ───────────────────────────────
let neuralLines = [];
function initNeuralLines() {
  neuralLines = [];
  const count = 15 + Math.floor(Math.random() * 10);
  for (let i = 0; i < count; i++) {
    const angle = (Math.PI * 2 * i) / count + (Math.random() - 0.5) * 0.3;
    const len = coreR * (2 + Math.random() * 2.5);
    neuralLines.push({
      angle, len,
      pulsePos: Math.random(),
      pulseSpeed: 0.003 + Math.random() * 0.004,
      width: 0.5 + Math.random() * 1,
    });
  }
}

function drawNeuralLines(t) {
  const speedMult = 1 + (avatarState.eventRate / 5000);
  for (const nl of neuralLines) {
    nl.pulsePos = (nl.pulsePos + nl.pulseSpeed * speedMult) % 1;
    const x1 = cx + Math.cos(nl.angle) * coreR * 0.8;
    const y1 = cy + Math.sin(nl.angle) * coreR * 0.8;
    const x2 = cx + Math.cos(nl.angle) * nl.len;
    const y2 = cy + Math.sin(nl.angle) * nl.len;

    // Line
    ctx.beginPath();
    ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
    ctx.strokeStyle = C.green;
    ctx.globalAlpha = 0.08;
    ctx.lineWidth = nl.width;
    ctx.stroke();

    // Traveling pulse
    const px = x1 + (x2 - x1) * nl.pulsePos;
    const py = y1 + (y2 - y1) * nl.pulsePos;
    ctx.beginPath();
    ctx.arc(px, py, 2, 0, Math.PI * 2);
    ctx.fillStyle = C.green;
    ctx.globalAlpha = 0.6;
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

// ── Orbital Rings ──────────────────────────────
function drawOrbitalRings(t) {
  const rings = [
    { rx: coreR * 1.8, ry: coreR * 0.6, tilt: -0.3, speed: 0.0004, dots: 6, color: C.green },
    { rx: coreR * 2.2, ry: coreR * 0.8, tilt: 0.4, speed: -0.0003, dots: 5, color: C.gold },
    { rx: coreR * 1.5, ry: coreR * 1.2, tilt: 0.1, speed: 0.0005, dots: 4, color: C.orange },
  ];
  const speedMult = 1 + (avatarState.eventRate / 8000);
  for (const ring of rings) {
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(ring.tilt);
    // Orbit ellipse
    ctx.beginPath();
    ctx.ellipse(0, 0, ring.rx, ring.ry, 0, 0, Math.PI * 2);
    ctx.strokeStyle = ring.color;
    ctx.globalAlpha = 0.06;
    ctx.lineWidth = 1;
    ctx.stroke();
    // Dots
    for (let i = 0; i < ring.dots; i++) {
      const a = t * ring.speed * speedMult + (Math.PI * 2 * i) / ring.dots;
      const dx = Math.cos(a) * ring.rx;
      const dy = Math.sin(a) * ring.ry;
      ctx.beginPath();
      ctx.arc(dx, dy, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = ring.color;
      ctx.globalAlpha = 0.5;
      ctx.fill();
    }
    ctx.restore();
  }
  ctx.globalAlpha = 1;
}

// ── Core Entity ────────────────────────────────
function drawCore(t) {
  const breath = 1 + 0.03 * Math.sin(t * 0.002);
  // Pulse speed adapts to health
  const pulseFreq = avatarState.healthRatio >= 0.8 ? 0.002 : 0.004;
  const pulseBreath = 1 + 0.03 * Math.sin(t * pulseFreq);
  const scale = breath * pulseBreath;
  const rX = coreR * 1.1 * scale;
  const rY = coreR * 0.95 * scale;

  // Pick colors based on health
  let coreColor = C.green;
  let glowColor = 'rgba(0,196,154,';
  if (avatarState.healthRatio < 0.4) {
    coreColor = C.red;
    glowColor = 'rgba(255,77,77,';
  } else if (avatarState.healthRatio < 0.8) {
    coreColor = C.orange;
    glowColor = 'rgba(217,119,87,';
  }

  // Outer glow
  const glowGrad = ctx.createRadialGradient(cx, cy, rX * 0.2, cx, cy, rX * 2);
  glowGrad.addColorStop(0, glowColor + '0.15)');
  glowGrad.addColorStop(0.5, glowColor + '0.04)');
  glowGrad.addColorStop(1, glowColor + '0)');
  ctx.fillStyle = glowGrad;
  ctx.fillRect(0, 0, W, H);

  // Core ellipse
  ctx.save();
  ctx.translate(cx, cy);
  ctx.beginPath();
  ctx.ellipse(0, 0, rX, rY, 0, 0, Math.PI * 2);
  const grad = ctx.createRadialGradient(0, -rY * 0.3, rX * 0.1, 0, 0, rX);
  grad.addColorStop(0, coreColor);
  grad.addColorStop(0.5, glowColor + '0.3)');
  grad.addColorStop(1, glowColor + '0)');
  ctx.fillStyle = grad;
  ctx.fill();

  // Gold ring when on target
  if (avatarState.onTarget) {
    ctx.beginPath();
    ctx.ellipse(0, 0, rX * 1.15, rY * 1.15, 0, 0, Math.PI * 2);
    ctx.strokeStyle = C.gold;
    ctx.globalAlpha = 0.3 + 0.15 * Math.sin(t * 0.001);
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  ctx.restore();
}

// ── Aha Burst ──────────────────────────────────
let burstParticles = [];
function triggerBurst() {
  for (let i = 0; i < 30; i++) {
    const angle = Math.random() * Math.PI * 2;
    const speed = 2 + Math.random() * 4;
    burstParticles.push({
      x: cx, y: cy,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      life: 1,
      color: [C.green, C.gold, C.orange][Math.floor(Math.random() * 3)],
    });
  }
}

function drawBurst() {
  for (let i = burstParticles.length - 1; i >= 0; i--) {
    const bp = burstParticles[i];
    bp.x += bp.vx; bp.y += bp.vy;
    bp.life -= 0.015;
    if (bp.life <= 0) { burstParticles.splice(i, 1); continue; }
    ctx.beginPath();
    ctx.arc(bp.x, bp.y, 3 * bp.life, 0, Math.PI * 2);
    ctx.fillStyle = bp.color;
    ctx.globalAlpha = bp.life * 0.7;
    ctx.fill();
  }
  ctx.globalAlpha = 1;
}

// ── Glow Overlay ───────────────────────────────
function drawGlowOverlay(t) {
  const pulse = 0.03 + 0.02 * Math.sin(t * 0.001);
  let glowColor = avatarState.healthRatio >= 0.8 ? C.green : (avatarState.healthRatio >= 0.4 ? C.orange : C.red);
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(W, H) * 0.5);
  grad.addColorStop(0, glowColor);
  grad.addColorStop(1, 'transparent');
  ctx.globalAlpha = pulse;
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, W, H);
  ctx.globalAlpha = 1;
}

// ── Animation Loop ─────────────────────────────
function frame(t) {
  ctx.clearRect(0, 0, W, H);

  // Check for aha burst
  if (avatarState.newAha && t - avatarState.ahaFlashT < 100) {
    triggerBurst();
    avatarState.newAha = false;
  }

  drawParticles(t);
  drawNeuralLines(t);
  drawOrbitalRings(t);
  drawCore(t);
  drawBurst();
  drawGlowOverlay(t);

  requestAnimationFrame(frame);
}

resize();
requestAnimationFrame(frame);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=PULSE_PORT)
