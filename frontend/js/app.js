/* SmarTraderAI — live terminal client */

const TOKEN = localStorage.getItem('stai_token') || localStorage.getItem('ssai_token') || localStorage.getItem('stap_token');
if (!TOKEN) location.replace('/login');
const USER = JSON.parse(localStorage.getItem('stai_user') || localStorage.getItem('ssai_user') || localStorage.getItem('stap_user') || '{}');

const state = {
  view: 'overview', symbol: 'RELIANCE', interval: '5m', signalFilter: 'ALL',
  tvSymbol: 'RELIANCE.NS', tvInterval: '15',
  dashboard: null, quote: null, candles: null, analysis: null, model: null,
  watchlist: [], indices: [], symbols: [], signals: [], positions: null,
  trades: null, strategies: [], alerts: null, settings: null, catalog: null, connected: false,
  targets: [], targetsMeta: null, targetFailures: [], targetGroup: 'all',
  targetSort: 'confidence', targetQuery: '', targetLoading: false, targetProgress: '',
  brief: null, briefStatus: null, briefLoading: false, briefError: '',
  profile: null, profileTab: 'overview'
};

const $ = (s) => document.querySelector(s);
const fmt = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const money = (n) => '₹' + fmt(n);
const signCls = (v) => Number(v) >= 0 ? 'pos' : 'neg';
const signStr = (v) => (Number(v) >= 0 ? '+' : '') + fmt(v);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${TOKEN}`, ...(options.headers || {}) }
  });
  if (res.status === 401) { localStorage.clear(); location.href = '/login'; throw new Error('Session expired'); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function toast(msg) {
  const el = $('#toast'); el.textContent = msg; el.classList.add('show');
  clearTimeout(toast._t); toast._t = setTimeout(() => el.classList.remove('show'), 2800);
}

/* ---------------- SVG charts ---------------- */
function lineChart(data, { height = 220, color = '#818cf8' } = {}) {
  if (!data || !data.length) return '<div class="empty">No data</div>';
  const W = 760, H = height, P = { l: 8, r: 62, t: 12, b: 26 };
  const vals = data.map(d => d.v), min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
  const x = i => P.l + i * (W - P.l - P.r) / Math.max(1, data.length - 1);
  const y = v => P.t + (1 - (v - min) / span) * (H - P.t - P.b);
  const pts = data.map((d, i) => `${x(i).toFixed(1)},${y(d.v).toFixed(1)}`).join(' ');
  const area = `${P.l},${H - P.b} ${pts} ${x(data.length - 1)},${H - P.b}`;
  let grid = '';
  for (let i = 0; i <= 4; i++) {
    const gy = P.t + i * (H - P.t - P.b) / 4;
    grid += `<line x1="${P.l}" y1="${gy}" x2="${W - P.r}" y2="${gy}" stroke="#222c42"/>
      <text x="${W - P.r + 8}" y="${gy + 4}" fill="#6f7b92" font-size="10">${fmt((max - i * span / 4) / 1000)}k</text>`;
  }
  return `<div class="chart-wrap"><svg viewBox="0 0 ${W} ${H}"><defs>
    <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="${color}" stop-opacity=".35"/>
    <stop offset="100%" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>${grid}
    <polygon points="${area}" fill="url(#eq)"/><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="2"/>
    <circle cx="${x(data.length - 1)}" cy="${y(vals[vals.length - 1])}" r="4" fill="${color}"/></svg></div>`;
}

function candleChart(candles, ind) {
  if (!candles || !candles.length) return '<div class="empty">No candle data</div>';
  const W = 900, H = 350, P = { l: 10, r: 64, t: 14, b: 44 };
  const volH = 58, priceH = H - P.t - P.b - volH - 12;
  const min = Math.min(...candles.map(c => c.l)), max = Math.max(...candles.map(c => c.h)), span = (max - min) || 1;
  const y = v => P.t + (1 - (v - min) / span) * priceH;
  const slot = (W - P.l - P.r) / candles.length, bw = Math.max(2, slot * 0.58);
  const maxVol = Math.max(...candles.map(c => c.v));
  let bars = '';
  candles.forEach((c, i) => {
    const cx = P.l + slot * i + slot / 2, col = c.c >= c.o ? '#22c55e' : '#ef4444';
    bars += `<line x1="${cx}" y1="${y(c.h)}" x2="${cx}" y2="${y(c.l)}" stroke="${col}"/>`;
    bars += `<rect x="${cx - bw / 2}" y="${y(Math.max(c.o, c.c))}" width="${bw}" height="${Math.max(1, y(Math.min(c.o, c.c)) - y(Math.max(c.o, c.c)))}" fill="${col}" rx="1"/>`;
    const vh = c.v / (maxVol || 1) * volH;
    bars += `<rect x="${cx - bw / 2}" y="${H - P.b - vh}" width="${bw}" height="${vh}" fill="${col}" opacity=".35"/>`;
  });
  const overlay = (key, color) => {
    if (!ind || !ind[key]) return '';
    const pts = [];
    ind[key].forEach((v, i) => { if (v != null) pts.push(`${(P.l + slot * i + slot / 2).toFixed(1)},${y(v).toFixed(1)}`); });
    return pts.length > 1 ? `<polyline points="${pts.join(' ')}" fill="none" stroke="${color}" stroke-width="1.5"/>` : '';
  };
  let grid = '';
  for (let i = 0; i <= 4; i++) {
    const gy = P.t + i * priceH / 4;
    grid += `<line x1="${P.l}" y1="${gy}" x2="${W - P.r}" y2="${gy}" stroke="#222c42"/>
      <text x="${W - P.r + 8}" y="${gy + 4}" fill="#6f7b92" font-size="10">${fmt(max - i * span / 4)}</text>`;
  }
  return `<div class="chart-wrap"><svg viewBox="0 0 ${W} ${H}">${grid}
    ${overlay('ema20', '#38bdf8')}${overlay('ema50', '#f59e0b')}${overlay('bb_upper', '#6366f188')}${overlay('bb_lower', '#6366f188')}
    ${bars}</svg></div><div class="legend"><span><i style="background:#38bdf8"></i>EMA 20</span>
    <span><i style="background:#f59e0b"></i>EMA 50</span><span><i style="background:#6366f1"></i>Bollinger</span>
    <span><i style="background:#22c55e"></i>Bullish</span><span><i style="background:#ef4444"></i>Bearish</span></div>`;
}

function spark(vals, color = '#818cf8') {
  if (!vals || vals.length < 2) return '';
  const min = Math.min(...vals), max = Math.max(...vals), span = (max - min) || 1;
  return `<svg viewBox="0 0 100 28" style="width:100px;height:28px"><polyline points="${vals.map((v, i) => `${i * 100 / (vals.length - 1)},${26 - (v - min) / span * 22}`).join(' ')}" fill="none" stroke="${color}" stroke-width="1.8"/></svg>`;
}

function breadthBar(b) {
  const total = b.advances + b.declines + b.unchanged || 1;
  return `<div style="display:flex;height:10px;border-radius:8px;overflow:hidden;background:#222c42">
    <i style="width:${b.advances / total * 100}%;background:#22c55e"></i>
    <i style="width:${b.unchanged / total * 100}%;background:#64748b"></i>
    <i style="width:${b.declines / total * 100}%;background:#ef4444"></i></div>
    <div class="legend"><span class="pos">▲ ${b.advances} advances</span><span>${b.unchanged} unchanged</span><span class="neg">▼ ${b.declines} declines</span></div>`;
}

/* ---------------- TradingView ---------------- */
function tvSymbol(symbol) {
  const s = String(symbol || '').trim().toUpperCase();
  if (s === '^NSEI') return 'NSE:NIFTY50';
  if (s === '^NSEBANK') return 'NSE:BANKNIFTY';
  if (s === '^BSESN') return 'BSE:SENSEX';
  if (s.endsWith('.NS')) return 'NSE:' + s.slice(0, -3);
  if (s.endsWith('.BO')) return 'BSE:' + s.slice(0, -3);
  if (s.startsWith('^')) return 'BSE:' + s.slice(1);
  return 'NSE:' + s;
}

function tvInterval(interval) {
  return ({ '1m': '1', '2m': '2', '5m': '5', '15m': '15', '30m': '30', '1h': '60', '60m': '60', '1d': 'D', '1wk': 'W' })[interval] || '15';
}

function mountTradingView() {
  const host = $('#tvChart');
  if (!host) return;
  document.querySelectorAll('script[data-tv-widget]').forEach(s => s.remove());
  host.innerHTML = '<div class="tradingview-widget-container__widget"></div>';
  const script = document.createElement('script');
  script.dataset.tvWidget = '1';
  script.type = 'text/javascript';
  script.async = true;
  script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
  script.innerHTML = JSON.stringify({
    autosize: true,
    symbol: tvSymbol(state.tvSymbol),
    interval: tvInterval(state.tvInterval),
    timezone: 'Asia/Kolkata',
    theme: 'dark',
    style: '1',
    locale: 'en',
    backgroundColor: '#111726',
    gridColor: '#222c42',
    hide_top_toolbar: false,
    hide_legend: false,
    allow_symbol_change: true,
    save_image: false,
    calendar: false,
    support_host: 'https://www.tradingview.com'
  });
  script.onerror = () => {
    host.innerHTML = '<div class="empty">Could not load TradingView. Allow scripts from s3.tradingview.com and retry.</div>';
  };
  host.appendChild(script);
}

function setTvFullscreen(active) {
  const wrap = $('#tvFullWrap');
  const btn = $('#tvFullBtn');
  document.body.classList.toggle('tv-focus', active);
  if (wrap) wrap.classList.toggle('is-fullscreen', active);
  if (btn) {
    btn.textContent = active ? '✕ Exit Fullscreen' : '⛶ Fullscreen';
    btn.title = active ? 'Exit fullscreen (Esc)' : 'Expand chart to fullscreen';
    // Keep keyboard events in the parent document so Escape works even when
    // the cross-origin TradingView iframe had focus before entering fullscreen.
    if (active) btn.focus();
  }
  if (state.view === 'tradingview') setTimeout(mountTradingView, 120);
}

function toggleTvFullscreen() {
  setTvFullscreen(!document.body.classList.contains('tv-focus'));
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && document.body.classList.contains('tv-focus')) {
    setTvFullscreen(false);
  }
});

/* ---------------- Views ---------------- */
function kpi(label, value, foot, tone = '') {
  return `<div class="card kpi"><div class="kpi-label">${label}</div>
    <div class="kpi-value ${tone}">${value}</div><div class="kpi-foot">${foot}</div></div>`;
}

function renderOverview() {
  const d = state.dashboard; if (!d) return '<div class="loading">Loading…</div>';
  const idx = d.indices || [], b = d.breadth;
  return `<div class="grid g3" style="margin-bottom:16px">
      ${idx.slice(0, 3).map(q => kpi(q.symbol, money(q.price),
        `<span class="${signCls(q.change_pct)}">${signStr(q.change_pct)}%</span> · ${esc(q.exchange)}`, signCls(q.change_pct))).join('')}
    </div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="card"><div class="section-title">Market Breadth <small>${d.stats.watchlist_size} watchlist symbols</small></div>
        ${breadthBar(b)}<p class="note" style="margin-top:14px">Average move <strong class="${signCls(b.average_change)}">${signStr(b.average_change)}%</strong>
        · Model out-of-sample accuracy <strong>${d.stats.model_accuracy ?? '—'}%</strong>
        · Last scan ${esc(d.stats.last_scan || 'pending')}</p></div>
      <div class="card"><div class="section-title">Top Movers <small>Live Yahoo data</small></div>
        <div class="tbl-scroll"><table><thead><tr><th>Symbol</th><th>Price</th><th>Change</th></tr></thead><tbody>
        ${d.top_movers.map(q => `<tr><td><div class="sym">${q.symbol}</div><div class="sub">${esc(q.name)}</div></td>
          <td>${money(q.price)}</td><td class="${signCls(q.change_pct)}">${signStr(q.change_pct)}%</td></tr>`).join('')}
        </tbody></table></div></div>
    </div>
    <div class="grid g2">
      <div class="card"><div class="section-title">Gainers & Losers</div>
        <div class="tbl-scroll"><table><thead><tr><th>Gainers</th><th>%</th><th>Losers</th><th>%</th></tr></thead><tbody>
        ${d.gainers.map((g, i) => `<tr><td class="sym">${g.symbol}</td><td class="pos">${signStr(g.change_pct)}%</td>
          <td class="sym">${d.losers[i]?.symbol || ''}</td><td class="neg">${signStr(d.losers[i]?.change_pct || 0)}%</td></tr>`).join('')}
        </tbody></table></div></div>
      <div class="card"><div class="section-title">Latest ML Signals <small><button class="btn" data-go="signals">View all</button></small></div>
        ${d.signals.length ? d.signals.map(sigRow).join('') : '<div class="empty">No signals yet — run a scan.</div>'}</div>
    </div>`;
}

function sigRow(s) {
  return `<div class="signal-row"><div class="side-tag ${s.side === 'BUY' ? 'buy' : 'sell'}">${s.side}</div>
    <div style="flex:1;min-width:0"><div class="sym">${s.symbol} <span class="sub">${esc(s.strategy)}</span></div>
    <div class="sub">Entry ${money(s.entry)} · Target ${money(s.target)} · SL ${money(s.stoploss)} · ML ${s.ml_bias} ${s.ml_probability_up}↑/${s.ml_probability_down}↓</div></div>
    <div style="text-align:right"><strong>${s.confidence}%</strong><div class="meter"><i style="width:${s.confidence}%"></i></div></div></div>`;
}

function catalogGroups() {
  const cat = state.catalog || {};
  return [
    ['INDICES · NIFTY 50 / NIFTY BANK / SENSEX', cat.indices || []],
    ['NSE BANKS', cat.banks || []],
    ['NSE COMPANIES', cat.nse_companies || []],
    ['BSE COMPANIES', cat.bse_companies || []]
  ];
}

function catalogSymbolSet() {
  return new Set(catalogGroups().flatMap(([, items]) => items.map(x => x.symbol)));
}

function symbolOptions() {
  const list = state.watchlist.length ? state.watchlist.map(q => q.symbol) : (state.symbols || []);
  return [...new Set([...catalogSymbolSet(), ...list, state.symbol])];
}

function catalogOptions(selected) {
  const known = catalogSymbolSet();
  const extras = [...new Set([...symbolOptions(), selected])].filter(s => !known.has(s));
  const extraOptions = extras.length
    ? `<optgroup label="WATCHLIST / OTHER">${extras.map(s => `<option value="${esc(s)}" ${s === selected ? 'selected' : ''}>${esc(s)}</option>`).join('')}</optgroup>` : '';
  return extraOptions + catalogGroups().map(([label, items]) =>
    `<optgroup label="${esc(label)}">${items.map(x =>
      `<option value="${esc(x.symbol)}" ${x.symbol === selected ? 'selected' : ''}>${esc(x.name)} · ${esc(x.exchange)}</option>`
    ).join('')}</optgroup>`).join('');
}

function catalogChips(selected, attr, quoteMap = {}) {
  return catalogGroups().map(([label, items]) => `<div class="tv-group">
    <div class="tv-group-label">${esc(label)} <span>${items.length}</span></div>
    <div class="tv-chips">${items.map(x => {
      const q = quoteMap[x.symbol];
      return `<button class="tv-chip ${x.symbol === selected ? 'active' : ''}" ${attr}="${esc(x.symbol)}">${esc(x.name)}<span class="${q ? signCls(q.change_pct) : ''}">${q ? signStr(q.change_pct) + '%' : esc(x.exchange)}</span></button>`;
    }).join('')}</div></div>`).join('');
}

function tvForSymbol(symbol) {
  for (const [, items] of catalogGroups()) {
    const hit = items.find(x => x.symbol === symbol);
    if (hit) return hit.tv_symbol || tvSymbol(symbol);
  }
  return tvSymbol(symbol);
}

function renderMarkets() {
  const q = state.quote, c = state.candles, a = state.analysis, cat = state.catalog || {};
  if (!q || !c) return '<div class="loading">Loading market data…</div>';
  const quoteMap = Object.fromEntries([...(state.indices || []), ...(state.watchlist || [])].map(x => [x.symbol, x]));
  return `<div class="input-row" style="max-width:820px;flex-wrap:wrap">
      <select id="mktSymbol">${catalogOptions(state.symbol)}</select>
      <select id="mktInterval">${['1m','5m','15m','30m','1h','1d'].map(i => `<option ${i === state.interval ? 'selected' : ''}>${i}</option>`).join('')}</select>
      <button class="btn primary" id="mktLoad">Load Chart</button>
      <a class="btn" href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(tvForSymbol(state.symbol))}" target="_blank" rel="noopener">TradingView ↗</a>
      <span class="note">${esc(q.exchange)} · ${esc(q.currency)} · ${esc(q.delay_note || '')}</span>
    </div>
    <div class="grid g4" style="margin-bottom:16px">
      ${kpi(q.symbol + ' · LTP', money(q.price), `<span class="${signCls(q.change_pct)}">${signStr(q.change_pct)}%</span>`, signCls(q.change))}
      ${kpi('Day High', money(q.day_high), 'Live session')}
      ${kpi('Day Low', money(q.day_low), 'Live session')}
      ${kpi('Volume', fmt(q.volume), 'Cumulative')}
    </div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="card"><div class="section-title">${q.symbol} · ${state.interval} <small>${esc(q.name)}</small></div>
        ${candleChart(c.candles, c.indicators)}</div>
      <div class="card ai-hero"><div class="section-title">ML Model Read <small>RandomForest</small></div>
        <div class="bias ${a.bias === 'BULLISH' ? 'pos' : a.bias === 'BEARISH' ? 'neg' : ''}">${a.bias}</div>
        <div class="sub" style="margin:8px 0">Direction confidence ${a.confidence}%</div>
        <div class="meter" style="width:100%;margin-bottom:12px"><i style="width:${a.confidence}%"></i></div>
        <div class="grid g3" style="gap:8px;margin-bottom:14px">
          <div><div class="kpi-label">UP</div><strong class="pos">${a.probability_up}%</strong></div>
          <div><div class="kpi-label">DOWN</div><strong class="neg">${a.probability_down}%</strong></div>
          <div><div class="kpi-label">MODEL EDGE</div><strong class="${a.model.edge_over_baseline >= 0 ? 'pos' : 'neg'}">${a.model.edge_over_baseline >= 0 ? '+' : ''}${a.model.edge_over_baseline}%</strong></div>
        </div>
        <p style="font-size:12px;line-height:1.6;color:#c3ccdd">${esc(a.summary)}</p>
        <div style="margin-top:10px">${a.key_points.map(p => `<div class="point">${esc(p)}</div>`).join('')}</div>
      </div>
    </div>
    <div class="card" style="margin-top:16px"><div class="section-title">Symbol universe <small>${cat.total || 0} verified NSE/BSE symbols · click any symbol to open its live chart</small></div>
      <input id="mktSearch" class="tv-search" placeholder="Filter symbols (e.g. BANK, RELIANCE, SENSEX)" />
      ${catalogChips(state.symbol, 'data-mktsymbol', quoteMap)}
      <p class="note" style="margin-top:14px">Clicking a symbol loads Yahoo OHLCV candles, indicators and the live ML read here. NSE uses <code>.NS</code>, BSE uses <code>.BO</code>, and indices use Yahoo index symbols. Yahoo quotes may be delayed ~15 minutes.</p>
    </div>
    <div class="card" style="margin-top:16px"><div class="section-title">Watchlist <small>${state.watchlist.length} symbols · live ticks</small></div>
      <div class="tbl-scroll"><table><thead><tr><th>Symbol</th><th>Price</th><th>Change %</th><th>High</th><th>Low</th><th>Volume</th></tr></thead><tbody>
      ${state.watchlist.map(x => `<tr style="cursor:pointer" data-symbol="${x.symbol}"><td><div class="sym">${x.symbol}</div><div class="sub">${esc(x.name)}</div></td>
        <td>${money(x.price)}</td><td class="${signCls(x.change_pct)}">${signStr(x.change_pct)}%</td>
        <td>${money(x.day_high)}</td><td>${money(x.day_low)}</td><td>${fmt(x.volume)}</td></tr>`).join('')}
      </tbody></table></div></div>`;
}

function renderSignals() {
  const list = state.signals.filter(s => state.signalFilter === 'ALL' || s.side === state.signalFilter);
  return `<div class="card"><div class="section-title">ML-Filtered Trade Signals
      <div><span class="chip indigo">${state.signals.length} ACTIVE</span>
      <button class="btn" data-filter="ALL">All</button><button class="btn" data-filter="BUY">Buy</button>
      <button class="btn" data-filter="SELL">Sell</button><button class="btn primary" id="scanBtn2">⟳ Rescan</button></div></div>
    ${list.length ? list.map(sigRow).join('') : '<div class="empty">No signals. Run a scan against live data.</div>'}
    <div class="note" style="margin-top:14px">Last scan: ${esc(state.dashboard?.stats?.last_scan || '—')} · Signals require technical setup + ML agreement.</div></div>`;
}

function renderPositions() {
  const b = state.positions?.broker || {};
  return `<div class="card"><div class="section-title">Broker Connection <small>${esc(b.broker || '')}</small></div>
    <div class="grid g4" style="gap:10px;margin-bottom:14px">
      <div class="kpi-label">Configured: <strong>${b.configured ? 'Yes' : 'No'}</strong></div>
      <div class="kpi-label">Connected: <strong>${b.connected ? 'Yes' : 'No'}</strong></div>
      <div class="kpi-label">Live orders: <strong>${b.trading_enabled ? 'Enabled' : 'Disabled'}</strong></div>
      <div class="kpi-label">Mode: <strong>LIVE MARKET</strong></div>
    </div>
    <p class="note">${esc(b.message || '')}</p></div>
    <div class="card" style="margin-top:16px"><div class="section-title">Positions</div>
      <div class="empty">${state.positions?.positions?.length ? '' : 'No broker session connected — no holdings loaded.'}</div></div>
    <div class="card" style="margin-top:16px"><div class="section-title">Trade History</div>
      <div class="empty">${state.trades?.trades?.length ? '' : 'No broker session connected — no trades loaded.'}</div></div>`;
}

function renderStrategies() {
  return `<div class="grid g3">${state.strategies.map(s => `<div class="card strategy-card">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div><div class="sym">${esc(s.name)}</div><div class="sub">${esc(s.type)}</div></div>
      <button class="switch ${s.enabled ? 'on' : ''}" data-toggle="${s.id}"></button></div>
    <p class="sub" style="line-height:1.5">${esc(s.description)}</p>
    <div style="display:flex;gap:8px;align-items:center"><span class="chip ${s.status === 'ACTIVE' ? 'green' : 'amber'}">${s.status}</span>
      <span class="chip ${s.risk === 'LOW' ? 'green' : s.risk === 'HIGH' ? 'red' : 'amber'}">${s.risk} RISK</span></div>
    </div>`).join('')}</div>`;
}

function renderAI() {
  const a = state.analysis, m = state.model;
  return `<div class="input-row" style="max-width:560px">
      <select id="aiSymbol">${symbolOptions().map(s => `<option ${s === state.symbol ? 'selected' : ''}>${s}</option>`).join('')}</select>
      <select id="aiInterval">${['1m','5m','15m','1h','1d'].map(i => `<option ${i === state.interval ? 'selected' : ''}>${i}</option>`).join('')}</select>
      <button class="btn primary" id="aiRun">✦ Analyse</button></div>
    ${a ? `<div class="grid g2"><div class="card ai-hero">
      <div class="section-title">${esc(a.name)} <small>${a.symbol}</small></div>
      <div class="bias ${a.bias === 'BULLISH' ? 'pos' : a.bias === 'BEARISH' ? 'neg' : ''}">${a.bias}</div>
      <div class="sub" style="margin:8px 0">Confidence ${a.confidence}% · LTP ${money(a.price)} · ${signStr(a.change_pct)}%</div>
      <div class="meter" style="width:100%;margin-bottom:16px"><i style="width:${a.confidence}%"></i></div>
      <p style="line-height:1.7;color:#c3ccdd">${esc(a.summary)}</p>
      <div style="margin-top:14px"><span class="chip indigo">KEY OBSERVATIONS</span>
        ${a.key_points.map(p => `<div class="point">${esc(p)}</div>`).join('')}</div>
      </div><div class="card"><div class="section-title">Action Plan</div>
        <div class="chip green">SUGGESTION</div><p style="margin-top:12px;line-height:1.7;font-size:13px">${esc(a.suggestion)}</p>
        <div style="margin-top:18px;border-top:1px solid var(--line);padding-top:14px">
          <div class="kpi-label">Market time</div><p class="sub" style="margin-top:6px">${esc(a.market_time)}</p>
          <div class="kpi-label" style="margin-top:12px">Source</div><p class="sub" style="margin-top:6px">${esc(a.source)}</p>
        </div></div></div>
      ${m ? `<div class="card" style="margin-top:16px"><div class="section-title">Model Performance <small>${esc(m.algorithm)}</small></div>
        <div class="grid g4" style="gap:10px;margin-bottom:14px">
          <div><div class="kpi-label">Out-of-sample accuracy</div><strong class="pos">${m.out_of_sample_accuracy}%</strong></div>
          <div><div class="kpi-label">Baseline accuracy</div><strong>${m.baseline_accuracy}%</strong></div>
          <div><div class="kpi-label">Edge over baseline</div><strong class="${m.edge_over_baseline >= 0 ? 'pos' : 'neg'}">${m.edge_over_baseline >= 0 ? '+' : ''}${m.edge_over_baseline}%</strong></div>
          <div><div class="kpi-label">Macro precision</div><strong>${m.macro_precision}%</strong></div>
        </div>
        <div class="section-title">Feature Importance <small>${esc(m.label)}</small></div>
        ${Object.entries(m.feature_importance).map(([k, v]) => `<div class="bar-row"><span>${esc(k)}</span>
          <div class="bar-track"><i style="width:${(v * 100).toFixed(1)}%"></i></div><strong>${(v * 100).toFixed(1)}%</strong></div>`).join('')}
        <p class="note" style="margin-top:14px">Trained ${esc(m.trained_at)} on ${m.symbols.length} live symbols with ${fmt(m.train_samples)} train / ${fmt(m.test_samples)} held-out samples. Model retrains every 15 minutes.</p>
      </div>` : ''}` : '<div class="loading">Run an analysis to see ML predictions.</div>'}
    <div class="card" style="margin-top:16px"><div class="section-title">TARGET & STOPLOSS <small>Momentum + RandomForest levels for every bank, company and index</small></div>
      <p class="note">Live Yahoo 5-minute candles power Entry, Target, Stoploss and the buy zone for NIFTY 50, NIFTY BANK, all NSE banks and every company in the catalog.</p>
      <button class="btn primary" data-go="targets" style="margin-top:12px">Open Target &amp; Stoploss →</button>
    </div>`;
}

function renderBrief() {
  const s = state.briefStatus || {};
  const b = state.brief;
  const e = b?.evidence || {};
  const rf = e.random_forest || {};
  const mom = e.momentum || {};
  const lv = e.atr_derived_levels || {};
  const n = b?.narrative || {};
  const connected = !!s.configured;
  const fallback = !!(b?.meta?.fallback);
  const fallbackReason = esc(b?.meta?.fallback_reason || '');
  const fallbackBanner = fallback ? `<div class="empty" style="color:#fbbf24;border:1px solid #f59e0b55;border-radius:8px;margin-bottom:14px">OpenAI unavailable (${fallbackReason || 'no quota'}) — showing a clearly labelled local summary built from the same live evidence.</div>` : '';

  const evidenceCard = b ? `<div class="card" style="margin-top:16px">
    <div class="section-title">LIVE EVIDENCE USED FOR BRIEF <small>${esc(b.interval_used)} · ${esc(e.data_source || '')}</small></div>
    <div class="grid g4" style="gap:10px;margin-bottom:14px">
      ${kpi('Last traded price', money(e.last_price), `${signStr(e.change_pct)}% · ${esc(e.market_time_ist || '—')}`, signCls(e.change_pct))}
      ${kpi('Terminal signal', esc(e.terminal_signal), `confidence ${e.terminal_confidence_pct}%`, e.terminal_signal === 'BUY' ? 'pos' : e.terminal_signal === 'SELL' ? 'neg' : '')}
      ${kpi('RandomForest', esc(rf.bias), `${rf.confidence_pct}% · out-of-sample ${rf.out_of_sample_accuracy_pct}%`)}
      ${kpi('ATR levels', `${money(lv.target)} / ${money(lv.stoploss)}`, `entry ${money(lv.entry)} · R:R 1:${lv.risk_reward}`)}
    </div>
    <div class="grid g2" style="gap:10px">
      <div><div class="kpi-label">Momentum</div><p class="sub" style="margin-top:6px">Score ${esc(mom.score)} · side ${esc(mom.side)} · EMA20 ${money(mom.ema20)} · EMA50 ${money(mom.ema50)} · RSI ${mom.rsi_value ?? '—'}</p>
        <p class="sub" style="margin-top:6px">${(mom.notes || []).map(x => esc(x)).join(' · ')}</p></div>
      <div><div class="kpi-label">Levels &amp; horizon</div><p class="sub" style="margin-top:6px">Watch zone ${money(lv.watch_zone_low)}–${money(lv.watch_zone_high)} · ${esc(e.horizon)}</p>
        <p class="sub" style="margin-top:6px">${e.reference_only ? 'Reference only — no actionable signal.' : 'Signal met the terminal confidence rules.'}${e.stale ? ' Yahoo candle is stale.' : ''}</p></div>
    </div>
    <p class="note" style="margin-top:14px">${esc(e.delay_note || '')} · ${esc(b.meta?.source || '')}</p>
  </div>` : '';

  const narrativeCard = b ? `<div class="card" style="margin-top:16px">
    <div class="section-title">${fallback ? 'LIVE EVIDENCE BRIEF (LOCAL)' : 'OPENAI MARKET BRIEF'} <small>${esc(b.meta?.provider || '')} · ${esc(b.meta?.generated_at || '')} · cache ${esc(b.meta?.cache || '')}</small></div>
    <p style="line-height:1.75;color:#c3ccdd">${esc(n.summary || '')}</p>
    <div class="grid g3" style="gap:12px;margin-top:16px">
      <div><span class="chip indigo">OBSERVATIONS</span>${(n.observations || []).map(x => `<div class="point">${esc(x)}</div>`).join('') || '<p class="sub">—</p>'}</div>
      <div><span class="chip amber">RISKS</span>${(n.risks || []).map(x => `<div class="point">${esc(x)}</div>`).join('') || '<p class="sub">—</p>'}</div>
      <div><span class="chip green">RE-CHECK</span>${(n.watch_conditions || []).map(x => `<div class="point">${esc(x)}</div>`).join('') || '<p class="sub">—</p>'}</div>
    </div>
    <p class="note" style="margin-top:16px">${esc(b.disclaimer || '')}</p>
  </div>` : '';

  return `<div class="input-row" style="flex-wrap:wrap">
      <select id="briefSymbol">${catalogOptions(state.symbol)}</select>
      <select id="briefInterval">${['5m', '1d'].map(i => `<option ${i === state.interval ? 'selected' : ''}>${i}</option>`).join('')}</select>
      <button class="btn primary" id="briefRun" ${state.briefLoading ? 'disabled' : ''}>${state.briefLoading ? '✧ Writing…' : '✧ Generate brief'}</button>
    </div>
    <div style="margin-bottom:14px"><span class="chip ${connected && !fallback ? 'green' : 'amber'}">${fallback ? 'LOCAL EVIDENCE MODE' : connected ? 'OPENAI CONNECTED' : 'LOCAL MODE · NO OPENAI KEY'}</span>
      <span class="sub" style="margin-left:10px">${fallback ? `OpenAI unavailable: ${fallbackReason || 'no quota'}. Local mode is active.` : connected ? `Model ${esc(s.model || '')}` : 'Add OPENAI_API_KEY to the server .env and restart to enable OpenAI text.'}</span></div>
    ${state.briefError ? `<div class="empty" style="color:#fca5a5;border:1px solid #ef444455;border-radius:8px">${esc(state.briefError)}</div>` : ''}
    ${state.briefLoading ? '<div class="loading">Fetching live Yahoo data and writing the grounded brief…</div>' : ''}
    ${fallbackBanner}${narrativeCard}${evidenceCard}
    <div class="card" style="margin-top:16px"><div class="section-title">How this works</div>
      <p class="note">OpenAI writes the narrative when the key has quota. If OpenAI is missing, exhausted or failing, the same compact JSON of real Yahoo OHLCV-derived levels, genuine RandomForest output and terminal momentum notes is summarised locally and clearly labelled as a fallback. Failed symbols are never estimated. This is research text only — no buy/sell order is placed and no outcome is guaranteed. ${esc(s.note || '')}</p>
    </div>`;
}

function targetRow(r) {
  const sideClass = r.signal === 'BUY' ? 'buy' : r.signal === 'SELL' ? 'sell' : 'wait';
  return `<tr data-targetsymbol="${esc(r.symbol)}" style="cursor:pointer">
    <td><div class="sym">${esc(r.symbol)}</div><div class="sub">${esc(r.name)}</div></td>
    <td><span class="chip indigo">${esc(r.group_label)}</span><div class="sub">${esc(r.exchange)} · ${esc(r.interval_used || '5m')}</div></td>
    <td>${money(r.price)}<div class="sub ${signCls(r.change_pct)}">${signStr(r.change_pct)}%</div></td>
    <td><span class="side-tag ${sideClass}">${esc(r.signal)}</span><div class="sub">ML ${esc(r.ml_bias)}</div></td>
    <td><strong>${r.confidence}%</strong><div class="meter"><i style="width:${r.confidence}%"></i></div>
      <div class="sub">Momentum ${r.momentum_score > 0 ? '+' : ''}${r.momentum_score} · RSI ${r.rsi14 ?? '—'}</div>
      ${r.stale_days > 10 ? `<div class="sub" style="color:#fca5a5">Stale ${r.stale_days}d · reference only</div>` : ''}</td>
    <td>${money(r.entry)}<div class="sub ts-zone">${esc(r.zone_label)} ${money(r.zone_low)}–${money(r.zone_high)}</div></td>
    <td class="pos">${money(r.target)}</td>
    <td class="neg">${money(r.stoploss)}</td>
    <td>1:${r.risk_reward}<div class="sub">ATR14 ${money(r.atr14)}</div></td>
    <td style="max-width:340px"><div class="ts-action">${esc(r.action)}</div><div class="sub">${esc(r.reason)}</div></td>
  </tr>`;
}

function renderTargets() {
  const meta = { ...(state.targetsMeta || {}), failed: state.targetFailures.length };
  const cat = state.catalog || {};
  const sorted = [...state.targets];
  if (state.targetSort === 'rr') sorted.sort((a, b) => b.risk_reward - a.risk_reward);
  else if (state.targetSort === 'change') sorted.sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct));
  else sorted.sort((a, b) => (a.signal === 'WAIT') - (b.signal === 'WAIT') || b.confidence - a.confidence);

  const q = state.targetQuery.trim().toLowerCase();
  const rows = q
    ? sorted.filter(r => `${r.symbol} ${r.name} ${r.group_label} ${r.exchange} ${r.interval_used || ''}`.toLowerCase().includes(q))
    : sorted;
  const failures = state.targetFailures;

  const counts = {
    all: cat.total || 196, indices: (cat.indices || []).length || 3,
    banks: (cat.banks || []).length || 24,
    nse_companies: (cat.nse_companies || []).length || 95,
    bse_companies: (cat.bse_companies || []).length || 74
  };
  const groups = [
    ['all', `ALL SYMBOLS (${counts.all})`], ['indices', `INDICES · NIFTY 50 / BANK / SENSEX (${counts.indices})`],
    ['banks', `NSE BANKS (${counts.banks})`], ['nse_companies', `NSE COMPANIES (${counts.nse_companies})`],
    ['bse_companies', `BSE COMPANIES (${counts.bse_companies})`]
  ];
  const buys = rows.filter(r => r.signal === 'BUY').length;
  const sells = rows.filter(r => r.signal === 'SELL').length;
  const waits = rows.filter(r => r.signal === 'WAIT').length;
  const avgConf = rows.length ? Math.round(rows.reduce((n, r) => n + r.confidence, 0) / rows.length) : 0;
  const progress = state.targetLoading
    ? `<div class="ts-progress"><i></i><span>${esc(state.targetProgress || 'Scanning live Yahoo data…')}</span></div>` : '';

  return `<div class="input-row" style="flex-wrap:wrap">
      <select id="targetGroup">${groups.map(([v, label]) => `<option value="${v}" ${v === state.targetGroup ? 'selected' : ''}>${esc(label)}</option>`).join('')}</select>
      <select id="targetSort">
        <option value="confidence" ${state.targetSort === 'confidence' ? 'selected' : ''}>Sort: ML confidence</option>
        <option value="rr" ${state.targetSort === 'rr' ? 'selected' : ''}>Sort: risk : reward</option>
        <option value="change" ${state.targetSort === 'change' ? 'selected' : ''}>Sort: price move</option>
      </select>
      <input id="targetSearch" value="${esc(state.targetQuery)}" placeholder="Filter symbol / bank / company…" />
      <button class="btn primary" id="targetRefresh" ${state.targetLoading ? 'disabled' : ''}>${state.targetLoading ? '⟳ Scanning…' : '⟳ Refresh live scan'}</button>
    </div>
    ${progress}
    <div class="grid g4" style="margin-bottom:16px">
      ${kpi('Symbols scanned', rows.length, `${esc(meta.generated_at || 'awaiting live scan')}${q ? ` · filtered from ${state.targets.length}` : ''}`)}
      ${kpi('Buy setups', buys, 'ML + momentum agree', 'pos')}
      ${kpi('Sell setups', sells, 'ML + momentum agree', 'neg')}
      ${kpi('Average confidence', avgConf + '%', `RF accuracy ${meta.model_accuracy ?? '—'}% · edge ${meta.model_edge ?? '—'}% · ${meta.failed} unavailable`)}
    </div>
    <div class="card"><div class="section-title">TARGET & STOPLOSS
        <small>5m primary · real 1d fallback where needed · ATR(14) levels · ${waits} watch-only</small></div>
      ${rows.length ? `<div class="tbl-scroll"><table><thead><tr>
        <th>Symbol</th><th>Group</th><th>LTP</th><th>Signal</th><th>Confidence</th>
        <th>Entry / Where to buy</th><th>Target</th><th>Stoploss</th><th>R:R</th><th>Plan</th>
      </tr></thead><tbody>${rows.map(targetRow).join('')}</tbody></table></div>`
        : `<div class="empty">${state.targetLoading ? 'Fetching real Yahoo candles and scoring each symbol…' : q ? 'No rows match this filter.' : 'No live predictions loaded yet. Click Refresh live scan.'}</div>`}
      ${failures.length ? `<div class="sub" style="margin-top:8px;color:#fca5a5">Unavailable from Yahoo: ${failures.slice(0, 6).map(f => `${esc(f.symbol)} (${esc(f.reason)})`).join(' · ')}${failures.length > 6 ? ` · +${failures.length - 6} more` : ''}</div>` : ''}
      <p class="note" style="margin-top:14px">${esc(meta.note || 'Levels are derived from live Yahoo Finance candles and the genuine RandomForest model. No orders are placed.')}
        ${meta.trained_symbols ? ` Model trained on ${meta.trained_symbols.length} live watchlist symbols.` : ''}
        ${esc(meta.delay_note || 'Yahoo Finance · NSE quotes may be delayed ~15 minutes')}. Click any row to open its live chart in Markets.</p>
    </div>`;
}

async function loadTargets(force = false) {
  if (state.targetLoading) return;
  const ticket = (loadTargets.ticket || 0) + 1;
  loadTargets.ticket = ticket;
  state.targetLoading = true;
  state.targets = [];
  state.targetsMeta = null;
  state.targetFailures = [];

  const groups = state.targetGroup === 'all'
    ? ['indices', 'banks', 'nse_companies', 'bse_companies'] : [state.targetGroup];
  const labels = {
    indices: 'NIFTY / SENSEX', banks: 'NSE BANKS',
    nse_companies: 'NSE COMPANIES', bse_companies: 'BSE COMPANIES'
  };
  const fallback = { indices: 3, banks: 24, nse_companies: 95, bse_companies: 74 };
  const pageSize = 16;

  try {
    for (const group of groups) {
      const total = (state.catalog?.[group] || []).length || fallback[group];
      for (let offset = 0; offset < total; offset += pageSize) {
        state.targetProgress = `${labels[group]} · ${Math.min(offset + pageSize, total)}/${total} symbols · ${state.targets.length} levels ready`;
        if (state.view === 'targets') $('#view').innerHTML = renderTargets();
        const data = await api(`/api/ai/targets?group=${group}&offset=${offset}&limit=${pageSize}${force ? '&refresh=true' : ''}`);
        if (ticket !== loadTargets.ticket) return;
        state.targets.push(...data.targets);
        state.targetsMeta = data.meta;
        state.targetFailures.push(...(data.meta?.failed_symbols || []));
      }
    }
    const failed = state.targetFailures.length;
    state.targetProgress = `Complete · ${state.targets.length} live predictions · ${failed} unavailable${failed ? ' — see note below' : ''}`;
  } catch (err) {
    if (ticket !== loadTargets.ticket) return;
    state.targetProgress = `Scan failed: ${err.message}`;
    toast(`Target scan failed: ${err.message}`);
  } finally {
    if (ticket !== loadTargets.ticket) return;
    state.targetLoading = false;
    if (state.view === 'targets') $('#view').innerHTML = renderTargets();
  }
}

async function generateBrief(force = false) {
  if (state.briefLoading) return;
  state.briefLoading = true;
  state.briefError = '';
  if (state.view === 'brief') $('#view').innerHTML = renderBrief();
  try {
    state.brief = await api('/api/ai/brief', {
      method: 'POST',
      body: JSON.stringify({ symbol: state.symbol, interval: state.interval, refresh: force })
    });
  } catch (err) {
    state.brief = null;
    state.briefError = err.message;
    toast(`Brief failed: ${err.message}`);
  } finally {
    state.briefLoading = false;
    if (state.view === 'brief') $('#view').innerHTML = renderBrief();
  }
}

function renderAlerts() {
  const list = state.alerts?.alerts || [];
  return `<div class="card"><div class="section-title">Live Scanner Alerts <small><button class="btn" id="readAlerts">Mark all as read</button></small></div>
    ${list.length ? list.map(a => `<div class="alert-item ${a.read ? '' : 'unread'} ${a.type.toLowerCase()}">
      <div class="alert-icon">${a.type === 'SELL' ? '↓' : '↑'}</div>
      <div style="flex:1"><div><strong>${a.symbol}</strong> <span class="chip ${a.type === 'SELL' ? 'red' : 'green'}">${a.type}</span></div>
      <div style="color:#b4bfd2;font-size:12px;margin-top:4px">${esc(a.message)}</div></div>
      <div class="sub">${a.time}</div></div>`).join('') : '<div class="empty">No alerts yet — run a scan.</div>'}</div>`;
}

function renderTradingView() {
  const sym = state.tvSymbol, interval = state.tvInterval, cat = state.catalog || {};
  const quoteMap = Object.fromEntries([...(state.indices || []), ...(state.watchlist || [])].map(q => [q.symbol, q]));
  const mapped = tvForSymbol(sym);
  const options = catalogOptions(sym);
  const chips = catalogChips(sym, 'data-tvsymbol', quoteMap);
  return `<div class="input-row" style="max-width:820px;flex-wrap:wrap">
      <select id="tvSymbol">${options}</select>
      <select id="tvInterval">${['1m','5m','15m','30m','1h','1d'].map(i => `<option ${i === interval ? 'selected' : ''}>${i}</option>`).join('')}</select>
      <button class="btn primary" id="tvLoad">Load Chart</button>
      <a class="btn" href="https://www.tradingview.com/chart/?symbol=${encodeURIComponent(mapped)}" target="_blank" rel="noopener">Open on TradingView ↗</a>
    </div>
    <div id="tvFullWrap" class="tv-full-wrap">
      <div class="card tv-card">
        <div class="section-title"><span>${esc(mapped)} · ${esc(interval)} <small>TradingView advanced chart · IST</small></span>
          <button class="btn" id="tvFullBtn">⛶ Fullscreen</button></div>
        <div id="tvChart" class="tradingview-widget-container tv-chart">
          <div class="tradingview-widget-container__widget"></div>
        </div>
      </div>
    </div>
    <div class="card" style="margin-top:16px"><div class="section-title">Symbol universe <small>${cat.total || 0} verified NSE/BSE symbols · click to switch chart</small></div>
      <input id="tvSearch" class="tv-search" placeholder="Filter symbols (e.g. BANK, RELIANCE, SENSEX)" />
      ${chips}
      <p class="note" style="margin-top:14px">The chart is rendered by TradingView's public widget and streams from TradingView's own feeds; its built-in symbol search also reaches every NSE/BSE instrument. Yahoo Finance powers the live quote tags and the terminal's native charts. If the chart is blank, allow scripts from <code>s3.tradingview.com</code>.</p>
    </div>`;
}

function profileTabBtn(id, icon, label) {
  const active = state.profileTab === id ? 'active' : '';
  return `<button class="${active}" data-profile-tab="${id}"><span class="ico">${icon}</span><span>${label}</span></button>`;
}
function profileToggle(key, on, label, desc) {
  return `<div class="settings-row"><div class="meta"><strong>${esc(label)}</strong><span>${esc(desc)}</span></div>
    <button class="toggle ${on ? 'on' : ''}" data-pref-toggle="${esc(key)}" data-pref-value="${on ? '1' : '0'}" type="button"></button></div>`;
}
function profileSaveBar(id, label='Save changes') {
  return `<div class="form-actions"><button class="btn ghost" type="button" data-profile-reset="${id}">Cancel</button><button class="btn primary" type="submit">${label}</button></div>`;
}
function fmtDate(s) { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? esc(s) : d.toLocaleString('en-IN', { dateStyle:'medium', timeStyle:'short' }); }
function initials(name, email) { return ((name||email||'U').trim().slice(0,2).toUpperCase()); }

function renderProfile() {
  const p = state.profile || {};
  const tab = state.profileTab || 'overview';
  const prefs = p.preferences || {};
  const trading = prefs.trading || {};
  const ai = prefs.ai || {};
  const app = prefs.app || {};
  const notif = p.notifications || {};
  const avatar = p.avatar_url ? `<img src="${esc(p.avatar_url)}" alt="avatar">` : esc(initials(p.name, p.email));
  const verified = p.email_verified ? '<span class="badge ok">Verified</span>' : '<span class="badge warn">Unverified</span>';
  const tabs = [
    ['overview','◉','Overview'],['personal','✎','Personal Info'],['security','🔒','Security'],
    ['trading','⌁','Trading Prefs'],['ai','✦','AI Personalization'],['notifications','◔','Notifications'],
    ['billing','▤','Subscription'],['services','⇄','Connected Services'],['activity','◷','Activity'],
    ['app','⚙','App Prefs'],['support','?','Help & Support'],['data','▣','Account Data'],
  ];
  const panel = renderProfilePanel(tab, p, trading, ai, app, notif);
  return `<div class="profile-layout">
    <aside class="card profile-side">
      <div class="profile-hero">
        <div class="profile-hero-avatar">${avatar}</div>
        <div><h3>${esc(p.name||'User')}</h3><p>@${esc(p.username||'user')}</p><div style="margin-top:8px">${verified} <span class="badge">${esc(p.membership_plan||'Free')}</span></div></div>
      </div>
      <div class="profile-side-nav">${tabs.map(t=>profileTabBtn(t[0],t[1],t[2])).join('')}<button id="logoutBtn" class="profile-logout-nav" type="button"><span class="ico"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg></span><span>Logout</span></button></div>
    </aside>
    <section class="profile-main stack">${panel}</section>
  </div>`;
}

function renderProfilePanel(tab, p, trading, ai, app, notif) {
  if (tab === 'overview') return profileOverview(p);
  if (tab === 'personal') return profilePersonal(p);
  if (tab === 'security') return profileSecurity(p);
  if (tab === 'trading') return profileTrading(trading);
  if (tab === 'ai') return profileAI(ai);
  if (tab === 'notifications') return profileNotifications(notif);
  if (tab === 'billing') return profileBilling(p);
  if (tab === 'services') return profileServices(p);
  if (tab === 'activity') return profileActivity(p);
  if (tab === 'app') return profileAppPrefs(app);
  if (tab === 'support') return profileSupport();
  if (tab === 'data') return profileData(p);
  return profileOverview(p);
}

function profileOverview(p) {
  return `<div class="card"><div class="section-title">Profile Overview <small>Manage your SmarTraderAI account</small></div>
    <div class="profile-kpis">
      <div class="profile-kpi"><div class="label">User ID</div><div class="value">#${esc(p.id)}</div><div class="sub">Unique account</div></div>
      <div class="profile-kpi"><div class="label">Membership</div><div class="value">${esc(p.membership_plan||'Free')}</div><div class="sub">${esc(p.membership_status||'Active')}</div></div>
      <div class="profile-kpi"><div class="label">Email</div><div class="value" style="font-size:14px;word-break:break-word">${esc(p.email||'—')}</div><div class="sub">${p.email_verified?'Verified':'Verification pending'}</div></div>
      <div class="profile-kpi"><div class="label">Member since</div><div class="value" style="font-size:14px">${esc((p.created_at||'').slice(0,10)||'—')}</div><div class="sub">Account created</div></div>
    </div>
    <div class="inline-actions"><button class="btn primary" data-profile-tab="personal">Edit Profile</button><button class="btn ghost" data-profile-tab="security">Security</button><button class="btn ghost" data-profile-tab="trading">Trading Preferences</button></div></div>
    <div class="card"><div class="section-title">Quick Account Information</div>
      <div class="settings-list">
        ${[['Full name', p.name],['Username','@'+(p.username||'')],['Country',p.country||'Not set'],['Timezone',p.timezone||'Asia/Kolkata'],['Last updated',fmtDate(p.updated_at)]].map(([k,v])=>`<div class="settings-row"><div class="meta"><strong>${esc(k)}</strong><span>${esc(v||'—')}</span></div></div>`).join('')}
      </div></div>`;
}

function profilePersonal(p) {
  return `<div class="card"><div class="section-title">Personal Information <small>Update your account details</small></div>
    <form id="profilePersonalForm">
      <div class="form-grid">
        <div class="field"><label>Full name</label><input name="name" value="${esc(p.name||'')}" required maxlength="80"></div>
        <div class="field"><label>Username</label><input name="username" value="${esc(p.username||'')}" required maxlength="40"></div>
        <div class="field"><label>Email address</label><input name="email" type="email" value="${esc(p.email||'')}" required></div>
        <div class="field"><label>Mobile number</label><input name="mobile" value="${esc(p.mobile||'')}" maxlength="30" placeholder="+91 ..."></div>
        <div class="field"><label>Country</label><input name="country" value="${esc(p.country||'')}" maxlength="80" placeholder="India"></div>
        <div class="field"><label>Timezone</label><input name="timezone" value="${esc(p.timezone||'Asia/Kolkata')}" maxlength="80"></div>
        <div class="field field-full"><label>Profile photo</label><input type="file" id="avatarFile" accept="image/*"><div class="field-help">Upload a small image (stored as profile avatar). Use Remove to clear it.</div>
          <div class="inline-actions" style="margin-top:8px"><button class="btn ghost" type="button" id="removeAvatarBtn">Remove photo</button></div></div>
        <div class="field field-full"><label>Bio / optional details</label><textarea name="bio" maxlength="300" placeholder="Optional short bio">${esc(p.bio||'')}</textarea></div>
      </div>
      ${profileSaveBar('personal')}
    </form></div>`;
}

function profileSecurity(p) {
  return `<div class="card"><div class="section-title">Security & Privacy <small>Protect your account</small></div>
    <form id="passwordForm" class="stack" style="gap:14px">
      <div class="form-grid">
        <div class="field field-full"><label>Current password</label><input name="current_password" type="password" required></div>
        <div class="field"><label>New password</label><input name="new_password" type="password" minlength="8" required></div>
        <div class="field"><label>Confirm new password</label><input name="confirm_password" type="password" minlength="8" required></div>
      </div>
      <div class="form-actions"><button class="btn primary" type="submit">Change password</button></div>
    </form>
    <div class="divider"></div>
    <div class="settings-list">
      <div class="settings-row"><div class="meta"><strong>Two-factor authentication</strong><span>2FA enrollment is not configured on this server. You can still secure your account with a strong password, session management, and security alerts.</span></div><span class="badge muted">Not configured</span></div>
      <div class="settings-row"><div class="meta"><strong>Login notifications</strong><span>Security alerts for sign-ins and account changes are controlled in Notifications.</span></div><button class="btn ghost" type="button" data-profile-tab="notifications">Open</button></div>
    </div></div>
    <div class="card"><div class="section-title">Active Sessions <small>Devices currently signed in</small></div>
      <div id="sessionsList" class="muted">Loading sessions…</div>
      <div class="form-actions"><button class="btn danger" type="button" id="logoutAllBtn">Logout from all other devices</button></div></div>
    <div class="card"><div class="section-title">Login History <small>Recent account security events</small></div>
      <div id="securityActivity" class="muted">Loading activity…</div></div>`;
}

function profileTrading(trading) {
  const segs = ['Equity','Indices','F&O','Commodities','Currency'];
  const indicators = ['EMA','RSI','MACD','Bollinger Bands','ATR','VWAP'];
  const tfs = ['1m','5m','15m','1h','1d'];
  return `<div class="card"><div class="section-title">Trading Preferences <small>Personalize your trading workspace</small></div>
    <form id="tradingPrefsForm">
      <div class="form-grid">
        <div class="field"><label>Preferred exchange</label><select name="preferred_exchange">${['NSE','BSE'].map(x=>`<option ${trading.preferred_exchange===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="field"><label>Default chart timeframe</label><select name="default_chart_timeframe">${tfs.map(x=>`<option ${trading.default_chart_timeframe===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="field"><label>Default landing page</label><select name="default_landing_page">${['overview','markets','signals','positions','ai','profile'].map(x=>`<option value="${x}" ${trading.default_landing_page===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="field"><label>Dashboard layout</label><select name="dashboard_layout">${['comfortable','compact'].map(x=>`<option ${trading.dashboard_layout===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="field field-full"><label>Preferred market segments</label><div class="inline-actions">${segs.map(s=>`<label class="pill"><input type="checkbox" name="preferred_segments" value="${s}" ${(trading.preferred_segments||[]).includes(s)?'checked':''}> ${s}</label>`).join('')}</div></div>
        <div class="field field-full"><label>Preferred indicators</label><div class="inline-actions">${indicators.map(s=>`<label class="pill"><input type="checkbox" name="preferred_indicators" value="${s}" ${(trading.preferred_indicators||[]).includes(s)?'checked':''}> ${s}</label>`).join('')}</div></div>
        <div class="field field-full"><label>Default watchlist (comma separated symbols)</label><input name="default_watchlist" value="${esc((trading.default_watchlist||[]).join(', '))}"></div>
        <div class="field field-full"><label>Favorite stocks (comma separated)</label><input name="favorite_stocks" value="${esc((trading.favorite_stocks||[]).join(', '))}"></div>
      </div>
      ${profileSaveBar('trading')}
    </form></div>`;
}

function profileAI(ai) {
  const patterns = ['Engulfing','Doji','Hammer','Shooting Star','Morning Star','Evening Star'];
  return `<div class="card"><div class="section-title">AI Personalization Center <small>Customize AI insights without changing the underlying model</small></div>
    <form id="aiPrefsForm">
      <div class="form-grid">
        <div class="field"><label>Analysis style</label><select name="analysis_style">${['conservative','balanced','aggressive'].map(x=>`<option ${ai.analysis_style===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="field"><label>Insight depth</label><select name="insight_depth">${['brief','standard','detailed'].map(x=>`<option ${ai.insight_depth===x?'selected':''}>${x}</option>`).join('')}</select></div>
        <div class="field"><label>EMA fast</label><input name="ema_fast" type="number" min="1" value="${esc(ai.ema_fast??20)}"></div>
        <div class="field"><label>EMA slow</label><input name="ema_slow" type="number" min="1" value="${esc(ai.ema_slow??50)}"></div>
        <div class="field"><label>RSI period</label><input name="rsi_period" type="number" min="1" value="${esc(ai.rsi_period??14)}"></div>
        <div class="field"><label>MACD fast/slow/signal</label><div class="inline-actions"><input name="macd_fast" type="number" min="1" value="${esc(ai.macd_fast??12)}" style="width:90px"><input name="macd_slow" type="number" min="1" value="${esc(ai.macd_slow??26)}" style="width:90px"><input name="macd_signal" type="number" min="1" value="${esc(ai.macd_signal??9)}" style="width:90px"></div></div>
        <div class="field field-full"><label>Candlestick pattern preferences</label><div class="inline-actions">${patterns.map(s=>`<label class="pill"><input type="checkbox" name="candlestick_patterns" value="${s}" ${(ai.candlestick_patterns||[]).includes(s)?'checked':''}> ${s}</label>`).join('')}</div></div>
        <div class="field field-full"><label>Preferred indicators</label><div class="inline-actions">${['EMA','RSI','MACD','Bollinger Bands','ATR'].map(s=>`<label class="pill"><input type="checkbox" name="preferred_indicators" value="${s}" ${(ai.preferred_indicators||[]).includes(s)?'checked':''}> ${s}</label>`).join('')}</div></div>
      </div>
      <div class="settings-list" style="margin-top:14px">
        ${profileToggle('ai_signal_notifications', !!ai.signal_notifications, 'AI signal notifications', 'Receive AI signal alerts in your notification preferences.')}
        ${profileToggle('show_model_info', !!ai.show_model_info, 'Show model information', 'Display AI model details in insights panels.')}
      </div>
      ${profileSaveBar('ai')}
    </form></div>
    <div class="card"><div class="section-title">AI Model Information</div><div class="note-box">Model: <strong>RandomForest (genuine sklearn)</strong> for direction filtering, plus rule-based technical evidence and optional OpenAI brief when configured. Your preferences here personalize display/analysis preferences and do not automatically retrain or replace the underlying model.</div></div>`;
}

function profileNotifications(notif) {
  const rows = [
    ['email_notifications','Email notifications','Receive account and alert emails when email delivery is configured.'],
    ['browser_push','Browser push notifications','Allow browser push alerts when supported by your browser.'],
    ['price_alerts','Price alerts','Notify when watched price levels or moves trigger.'],
    ['ai_signal_notifications','AI signal notifications','Notify when AI/ML signal setups are generated.'],
    ['market_news_notifications','Market news notifications','Receive important market news updates.'],
    ['watchlist_notifications','Watchlist notifications','Updates for symbols in your watchlist.'],
    ['security_alerts','Security alerts','Login, password and security-related notifications.'],
    ['risk_notifications','Risk notifications','Risk and exposure warnings.'],
  ];
  return `<div class="card"><div class="section-title">Notification Center <small>Control how SmarTraderAI contacts you</small></div>
    <form id="notifPrefsForm"><div class="settings-list">${rows.map(r=>profileToggle(r[0], !!notif[r[0]], r[1], r[2])).join('')}</div>${profileSaveBar('notifications')}</form></div>`;
}

function profileBilling(p) {
  return `<div class="card"><div class="section-title">Subscription & Billing <small>Current plan details</small></div>
    <div class="profile-kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      <div class="profile-kpi"><div class="label">Current plan</div><div class="value">${esc(p.membership_plan||'Free')}</div><div class="sub">${esc(p.membership_status||'Active')}</div></div>
      <div class="profile-kpi"><div class="label">Billing cycle</div><div class="value" style="font-size:16px">Not configured</div><div class="sub">No fake billing data shown</div></div>
      <div class="profile-kpi"><div class="label">Usage</div><div class="value" style="font-size:16px">Live terminal</div><div class="sub">Real account access</div></div>
    </div>
    <div class="note-box">This workspace currently shows only real account plan information. Payment/invoice history, upgrades, and renewals will appear when a billing provider is connected. No demo transactions are displayed.</div>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn ghost" type="button" disabled>Upgrade plan (billing not configured)</button></div></div>`;
}

function profileServices(p) {
  return `<div class="card"><div class="section-title">Connected Services <small>Manage integrations securely</small></div>
    <div id="servicesList" class="muted">Loading services…</div>
    <div class="divider"></div>
    <form id="serviceForm"><div class="form-grid">
      <div class="field"><label>Service type</label><select name="service_type"><option value="market_data">Market data provider</option><option value="broker">Broker integration</option><option value="external_app">External application</option><option value="api">API integration</option></select></div>
      <div class="field"><label>Service name</label><input name="name" required maxlength="80" placeholder="e.g. Broker API"></div>
      <div class="field field-full"><label>Configuration note (non-secret)</label><input name="config_note" maxlength="120" placeholder="Optional label or endpoint note"></div>
      <div class="field field-full"><label>API key / secret (optional)</label><input name="secret" type="password" maxlength="200" placeholder="Stored as hint only; raw secret is not persisted by this form"></div>
    </div><div class="form-actions"><button class="btn primary" type="submit">Connect / Update</button></div></form>
    <p class="field-help">For security, raw secrets are not stored in browser or profile DB by this endpoint. Configure production credentials in backend environment/secret manager.</p></div>`;
}

function profileActivity(p) {
  return `<div class="card"><div class="section-title">Activity Timeline <small>Recent account events</small></div>
    <div id="activityList" class="muted">Loading activity…</div></div>`;
}

function profileAppPrefs(app) {
  return `<div class="card"><div class="section-title">App Preferences <small>Customize your workspace</small></div>
    <form id="appPrefsForm"><div class="form-grid">
      <div class="field"><label>Theme</label><select name="theme"><option value="dark" ${app.theme==='dark'?'selected':''}>Dark</option><option value="light" ${app.theme==='light'?'selected':''}>Light (saved preference)</option></select></div>
      <div class="field"><label>Language</label><select name="language">${[['en','English'],['hi','Hindi']].map(([v,l])=>`<option value="${v}" ${app.language===v?'selected':''}>${l}</option>`).join('')}</select></div>
      <div class="field"><label>Currency</label><select name="currency">${['INR','USD'].map(x=>`<option ${app.currency===x?'selected':''}>${x}</option>`).join('')}</select></div>
      <div class="field"><label>Timezone</label><input name="timezone" value="${esc(app.timezone||'Asia/Kolkata')}"></div>
      <div class="field"><label>Date format</label><select name="date_format">${['DD MMM YYYY','YYYY-MM-DD','DD/MM/YYYY'].map(x=>`<option ${app.date_format===x?'selected':''}>${x}</option>`).join('')}</select></div>
      <div class="field"><label>Dashboard density</label><select name="dashboard_density">${['comfortable','compact'].map(x=>`<option ${app.dashboard_density===x?'selected':''}>${x}</option>`).join('')}</select></div>
    </div>
    <div class="settings-list" style="margin-top:14px">
      ${profileToggle('reduced_motion', !!app.accessibility?.reduced_motion, 'Reduced motion', 'Minimize animations and transitions.')}
      ${profileToggle('high_contrast', !!app.accessibility?.high_contrast, 'High contrast', 'Increase contrast for readability.')}
      ${profileToggle('large_text', !!app.accessibility?.large_text, 'Large text', 'Use larger text in supported areas.')}
    </div>
    ${profileSaveBar('app')}
    </form></div>`;
}

function profileSupport() {
  return `<div class="card"><div class="section-title">Help & Support</div>
    <div class="service-grid">
      <div class="service-card"><h4>Help Center</h4><p>Guides for dashboard, signals, AI brief, and account settings.</p><button class="btn ghost" type="button" onclick="toast('Help Center: use README/docs and in-app sections for guidance.')">Open</button></div>
      <div class="service-card"><h4>FAQs</h4><p>Common questions about live data, signals, and account management.</p><button class="btn ghost" type="button" onclick="toast('FAQ: Live data comes from Yahoo; signals are ML-filtered; credentials stay in .env.')">View</button></div>
      <div class="service-card"><h4>Contact Support</h4><p>Report issues or request account assistance.</p><a class="btn ghost" href="mailto:support@smartraderai.local">Email support</a></div>
      <div class="service-card"><h4>Report a Bug / Feedback</h4><p>Submit bugs or feature requests from your GitHub repository issues.</p><a class="btn ghost" href="https://github.com/ghanshyamsharma-ai/SmarTradeAI/issues" target="_blank" rel="noopener">Open GitHub Issues</a></div>
    </div>
    <div class="divider"></div><div class="note-box">Application version: <strong>${esc(state.settings?.version || state.dashboard?.version || 'v1')}</strong>. For sensitive account issues, include your User ID, not passwords or API keys.</div></div>`;
}

function profileData(p) {
  return `<div class="card"><div class="section-title">Account Data Management <small>Export or manage your account</small></div>
    <div class="settings-list">
      <div class="settings-row"><div class="meta"><strong>Download personal data</strong><span>Export your profile, preferences, activity, sessions, and connected service metadata as JSON.</span></div><button class="btn ghost" id="exportDataBtn" type="button">Download</button></div>
      <div class="settings-row"><div class="meta"><strong>Privacy policy / Terms</strong><span>Review how data is handled and the terms for using SmarTraderAI.</span></div><div class="inline-actions"><button class="btn ghost" type="button" onclick="toast('Privacy: profile data is stored in your account DB; secrets should be kept in backend env/secret manager.')">Privacy</button><button class="btn ghost" type="button" onclick="toast('Terms: SmarTraderAI provides market analytics; no guaranteed profits or automated trading without explicit broker authorization.')">Terms</button></div></div>
    </div></div>
    <div class="card danger-zone"><h4>Danger Zone</h4><p>Deactivation disables your account. Permanent deletion removes account/profile records. These actions require confirmation.</p>
      <div class="form-grid">
        <div class="field"><label>Deactivate account (type DEACTIVATE)</label><input id="deactivateConfirm" placeholder="DEACTIVATE"><div class="form-actions" style="justify-content:flex-start"><button class="btn danger" id="deactivateBtn" type="button">Deactivate</button></div></div>
        <div class="field"><label>Delete account (type DELETE your-email)</label><input id="deleteConfirm" placeholder="DELETE ${esc(p.email||'email@example.com')}"><div class="form-actions" style="justify-content:flex-start"><button class="btn danger" id="deleteAccountBtn" type="button">Delete permanently</button></div></div>
      </div></div>`;
}


const TITLES = {
  overview: ['Overview', 'Live market command center'], markets: ['Markets', 'Real-time Yahoo charts and watchlist'],
  signals: ['Signals', 'ML-filtered trade setups'], positions: ['Positions', 'Broker holdings and order history'],
  strategies: ['Strategies', 'Trading models'], ai: ['AI Insights', 'Machine-learning market analysis'],
  brief: ['AI Market Brief', 'Grounded research from live Yahoo data · OpenAI when available'],
  targets: ['Target & Stoploss', 'AI + momentum levels for every bank, company and index'],
  alerts: ['Alerts', 'Scanner notifications'], tradingview: ['TradingView', 'Professional charts for NSE symbols'],
  profile: ['Profile', 'Account, security, preferences and personalization']
};
const RENDERERS = { overview: renderOverview, markets: renderMarkets, signals: renderSignals,
  positions: renderPositions, strategies: renderStrategies, ai: renderAI, brief: renderBrief,
  targets: renderTargets, alerts: renderAlerts, tradingview: renderTradingView, profile: renderProfile };

async function loadView() {
  $('#view').innerHTML = '<div class="loading">Loading…</div>';
  try {
    if (state.view === 'overview') state.dashboard = await api('/api/dashboard');
    if (state.view === 'markets') {
      const [q, c, a, w, i, cat] = await Promise.all([
        api(`/api/market/quote?symbol=${encodeURIComponent(state.symbol)}`),
        api(`/api/market/candles?symbol=${encodeURIComponent(state.symbol)}&interval=${state.interval}&limit=120`),
        api(`/api/ai/analysis?symbol=${encodeURIComponent(state.symbol)}&interval=${state.interval}`),
        api('/api/market/watchlist'),
        api('/api/market/indices'),
        api('/api/market/catalog')
      ]);
      state.quote = q; state.candles = c; state.analysis = a;
      state.watchlist = w.watchlist; state.indices = i.indices; state.catalog = cat;
    }
    if (state.view === 'signals') { const d = await api('/api/signals'); state.signals = d.signals; }
    if (state.view === 'positions') {
      const [p, t] = await Promise.all([api('/api/positions'), api('/api/trades')]);
      state.positions = p; state.trades = t;
    }
    if (state.view === 'strategies') state.strategies = (await api('/api/strategies')).strategies;
    if (state.view === 'ai') {
      const [a, m] = await Promise.all([
        api(`/api/ai/analysis?symbol=${state.symbol}&interval=${state.interval}`),
        api(`/api/ai/model?interval=${state.interval}`)
      ]);
      state.analysis = a; state.model = m;
    }
    if (state.view === 'brief') {
      if (!state.catalog) state.catalog = await api('/api/market/catalog');
      state.briefStatus = await api('/api/ai/brief/status');
      await generateBrief();
    }
    if (state.view === 'targets') {
      state.catalog = await api('/api/market/catalog');
      $('#view').innerHTML = renderTargets();
      await loadTargets();
    }
    if (state.view === 'alerts') state.alerts = await api('/api/alerts');
    if (state.view === 'tradingview') {
      const [w, i, cat] = await Promise.all([
        api('/api/market/watchlist'), api('/api/market/indices'), api('/api/market/catalog')
      ]);
      state.watchlist = w.watchlist; state.indices = i.indices; state.catalog = cat;
    }
    if (state.view === 'profile') state.profile = await api('/api/profile');
    $('#view').innerHTML = RENDERERS[state.view]();
    if (state.view === 'tradingview') mountTradingView();
    if (state.view === 'profile') loadProfileExtras();
    updateBadges();
  } catch (e) { $('#view').innerHTML = `<div class="empty">Could not load: ${esc(e.message)}</div>`; }
}

function updateBadges() {
  $('#navSignals').textContent = state.signals.length || state.dashboard?.stats?.active_signals || 0;
  $('#navAlerts').textContent = state.alerts?.alerts?.filter(a => !a.read).length || 0;
}

function navigate(view) {
  state.view = view;
  document.querySelectorAll('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  $('#pageTitle').textContent = TITLES[view][0]; $('#pageSub').textContent = TITLES[view][1];
  $('#sidebar').classList.remove('open'); loadView();
}

let pollTimer = null;
let wsRetryTimer = null;

function applyTicks(indices, watchlist) {
  state.indices = indices || state.indices;
  state.watchlist = watchlist || state.watchlist;
  if (state.view === 'markets') {
    const q = state.quote;
    const fresh = (state.watchlist || []).find(x => x.symbol === q?.symbol);
    if (fresh) { state.quote = fresh; $('#view').innerHTML = renderMarkets(); }
  } else if (state.view === 'overview' && state.dashboard) {
    state.dashboard.indices = state.indices;
    state.dashboard.top_movers = [...(state.watchlist || [])].sort((a, b) => Math.abs(b.change_pct) - Math.abs(a.change_pct)).slice(0, 5);
    $('#view').innerHTML = renderOverview();
  }
}

async function pollTicks() {
  try {
    const [indicesRes, watchlistRes] = await Promise.all([api('/api/market/indices'), api('/api/market/watchlist')]);
    const indices = Array.isArray(indicesRes) ? indicesRes : (indicesRes?.indices || []);
    const watchlist = Array.isArray(watchlistRes) ? watchlistRes : (watchlistRes?.watchlist || []);
    applyTicks(indices, watchlist);
    const pill = $('#livePill');
    if (pill) { pill.className = 'live-pill'; pill.querySelector('span').textContent = 'LIVE · YAHOO'; }
  } catch (err) {
    const pill = $('#livePill');
    if (pill && !state.connected) { pill.className = 'live-pill off'; pill.querySelector('span').textContent = 'RECONNECTING'; }
  }
}

function startPolling() {
  if (pollTimer) return;
  pollTicks();
  pollTimer = setInterval(pollTicks, 5000);
}

function stopPolling() {
  if (!pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
}

function connectSocket() {
  if (!TOKEN) return;
  if (wsRetryTimer) { clearTimeout(wsRetryTimer); wsRetryTimer = null; }
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const pill = $('#livePill');
  let ws;
  try {
    // JWT travels as a WebSocket subprotocol, not in the URL/access logs.
    ws = new WebSocket(`${proto}://${location.host}/ws/market`, [TOKEN]);
  } catch (err) {
    startPolling();
    wsRetryTimer = setTimeout(connectSocket, 15000);
    return;
  }
  ws.onopen = () => {
    state.connected = true;
    stopPolling();
    if (pill) { pill.className = 'live-pill'; pill.querySelector('span').textContent = 'LIVE · YAHOO'; }
  };
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type !== 'ticks') return;
      applyTicks(msg.indices, msg.watchlist);
    } catch {}
  };
  ws.onclose = () => {
    state.connected = false;
    const wasPolling = !!pollTimer;
    startPolling();
    if (!wasPolling && pill) { pill.className = 'live-pill off'; pill.querySelector('span').textContent = 'RECONNECTING'; }
    // Fallback for serverless deployments (e.g. Vercel) where WebSockets are unavailable.
    wsRetryTimer = setTimeout(connectSocket, 15000);
  };
}

document.addEventListener('click', async (e) => {
  const nav = e.target.closest('.nav-item'); if (nav) return navigate(nav.dataset.view);
  const go = e.target.closest('[data-go]'); if (go) return navigate(go.dataset.go);
  const profileTab = e.target.closest('[data-profile-tab]');
  if (profileTab) {
    state.profileTab = profileTab.dataset.profileTab;
    if (state.view !== 'profile') return navigate('profile');
    $('#view').innerHTML = renderProfile();
    loadProfileExtras();
    return;
  }
  const prefToggle = e.target.closest('[data-pref-toggle]');
  if (prefToggle) { prefToggle.classList.toggle('on'); prefToggle.dataset.prefValue = prefToggle.classList.contains('on') ? '1' : '0'; return; }
  if (e.target.closest('#removeAvatarBtn')) {
    try { state.profile = await api('/api/profile', { method:'PUT', body: JSON.stringify({avatar_url:''}) }); toast('Profile photo removed'); loadView(); } catch(err){ toast(err.message); }
    return;
  }
  if (e.target.closest('#exportDataBtn')) {
    try {
      const res = await fetch('/api/profile/export', { headers: { 'Authorization': `Bearer ${TOKEN}` } });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob(); const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'smartraderai-profile-export.json'; a.click(); URL.revokeObjectURL(url);
      toast('Profile data exported');
    } catch(err){ toast(err.message); }
    return;
  }
  if (e.target.closest('#logoutAllBtn')) {
    try { const r = await api('/api/profile/sessions/revoke-all', { method:'POST' }); toast(`Revoked ${r.revoked} session(s)`); loadProfileExtras(); } catch(err){ toast(err.message); }
    return;
  }
  const revoke = e.target.closest('[data-revoke-session]');
  if (revoke) {
    try { await api(`/api/profile/sessions/${encodeURIComponent(revoke.dataset.revokeSession)}/revoke`, { method:'POST' }); toast('Session revoked'); loadProfileExtras(); } catch(err){ toast(err.message); }
    return;
  }
  const disc = e.target.closest('[data-disconnect-service]');
  if (disc) {
    try { await api(`/api/profile/services/${disc.dataset.disconnectService}`, { method:'DELETE' }); toast('Service removed'); loadProfileExtras(); } catch(err){ toast(err.message); }
    return;
  }
  if (e.target.closest('#deactivateBtn')) {
    const v = $('#deactivateConfirm')?.value?.trim();
    if (v !== 'DEACTIVATE') return toast('Type DEACTIVATE to confirm');
    try { await api('/api/profile/deactivate', { method:'POST', body: JSON.stringify({confirm:v}) }); toast('Account deactivated'); localStorage.clear(); location.href='/login'; } catch(err){ toast(err.message); }
    return;
  }
  if (e.target.closest('#deleteAccountBtn')) {
    const v = $('#deleteConfirm')?.value?.trim();
    try { await api('/api/profile', { method:'DELETE', body: JSON.stringify({confirm:v}) }); toast('Account deleted'); localStorage.clear(); location.href='/login'; } catch(err){ toast(err.message); }
    return;
  }
  const reset = e.target.closest('[data-profile-reset]'); if (reset) { loadView(); return; }
  const filter = e.target.closest('[data-filter]'); if (filter) { state.signalFilter = filter.dataset.filter; return renderSignals(); }
  const toggle = e.target.closest('[data-toggle]');
  if (toggle) {
    const id = toggle.dataset.toggle, d = await api(`/api/strategies/${id}/toggle`, { method: 'POST' });
    const s = d.strategy, item = state.strategies.find(x => x.id === id); Object.assign(item, s);
    toggle.classList.toggle('on', s.enabled); toast(`${s.name} ${s.enabled ? 'enabled' : 'paused'}`); return;
  }
  if (e.target.closest('#tvFullBtn')) { toggleTvFullscreen(); return; }
  const mktChip = e.target.closest('[data-mktsymbol]'); if (mktChip) { state.symbol = mktChip.dataset.mktsymbol; return loadView(); }
  const tvChip = e.target.closest('[data-tvsymbol]'); if (tvChip) { state.tvSymbol = tvChip.dataset.tvsymbol; return loadView(); }
  if (e.target.closest('#tvLoad')) { state.tvSymbol = $('#tvSymbol').value; state.tvInterval = $('#tvInterval').value; return loadView(); }
  const sym = e.target.closest('[data-symbol]'); if (sym) { state.symbol = sym.dataset.symbol; return navigate('markets'); }
  if (e.target.closest('#scanBtn') || e.target.closest('#scanBtn2')) {
    toast('Scanning live market data…');
    try {
      const r = await api('/api/scan', { method: 'POST' });
      state.signals = r.signals;
      if (state.dashboard) state.dashboard.stats.active_signals = r.signals_generated;
      toast(`${r.scanned} symbols · ${r.signals_generated} signals`);
      if (state.view === 'signals') renderSignals(); else updateBadges();
    } catch (err) { toast(err.message); }
    return;
  }
  if (e.target.closest('#mktLoad')) { state.symbol = $('#mktSymbol').value; state.interval = $('#mktInterval').value; return loadView(); }
  if (e.target.closest('#aiRun')) { state.symbol = $('#aiSymbol').value; state.interval = $('#aiInterval').value; return loadView(); }
  if (e.target.closest('#briefRun')) {
    state.symbol = $('#briefSymbol').value; state.interval = $('#briefInterval').value;
    return generateBrief(true);
  }
  if (e.target.closest('#targetRefresh')) { loadTargets(true); return; }
  const tSym = e.target.closest('[data-targetsymbol]'); if (tSym) { state.symbol = tSym.dataset.targetsymbol; return navigate('markets'); }
  if (e.target.closest('#readAlerts')) { await api('/api/alerts/read', { method: 'POST' }); toast('Alerts marked as read'); return loadView(); }
  if (e.target.closest('#logoutBtn')) { localStorage.clear(); location.href = '/login'; return; }
  if (e.target.closest('#avatarBtn')) { return navigate('profile'); }
  if (e.target.closest('#sidebarToggle') || e.target.closest('#menuBtn')) {
    const mobile = window.matchMedia('(max-width: 760px)').matches;
    if (mobile) {
      $('#sidebar').classList.toggle('open');
    } else {
      document.querySelector('.app').classList.toggle('sidebar-collapsed');
      const collapsed = document.querySelector('.app').classList.contains('sidebar-collapsed');
      const btn = $('#sidebarToggle') || $('#menuBtn');
      if (btn) btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    }
    return;
  }
  const sidebar = $('#sidebar');
  if (sidebar && sidebar.classList.contains('open') && window.matchMedia('(max-width: 760px)').matches && !e.target.closest('#sidebar') && !e.target.closest('#sidebarToggle')) {
    sidebar.classList.remove('open');
  }
});

async function loadProfileExtras() {
  if (state.view !== 'profile') return;
  const tab = state.profileTab;
  try {
    if (tab === 'security') {
      const [s, a] = await Promise.all([api('/api/profile/sessions'), api('/api/profile/activity?limit=20')]);
      const sessEl = $('#sessionsList');
      if (sessEl) sessEl.innerHTML = (s.sessions||[]).map(x => `<div class="session-item"><div class="session-meta"><strong>${esc(x.device||'Session')} ${x.is_current?'<span class="badge ok">Current</span>':''}</strong><span>${esc(x.ip_address||'—')} · ${esc((x.user_agent||'').slice(0,80))}</span><span>Last seen: ${fmtDate(x.last_seen_at)}${x.revoked_at?' · Revoked':''}</span></div><div class="inline-actions">${!x.revoked_at && !x.is_current?`<button class="btn ghost" data-revoke-session="${esc(x.session_id)}">Revoke</button>`:''}</div></div>`).join('') || '<div class="muted">No sessions found.</div>';
      const actEl = $('#securityActivity');
      const sec = (a.activity||[]).filter(x => ['security','account','profile','integration','settings'].includes(x.event_type)).slice(0,10);
      if (actEl) actEl.innerHTML = sec.map(x => `<div class="activity-item"><div class="activity-dot ${esc(x.event_type)}"></div><div class="activity-body"><strong>${esc(x.label)}</strong><p>${esc(x.detail||x.event_type)}</p></div><div class="activity-time">${fmtDate(x.created_at)}</div></div>`).join('') || '<div class="muted">No security activity yet.</div>';
    }
    if (tab === 'activity') {
      const a = await api('/api/profile/activity?limit=50');
      const el = $('#activityList');
      if (el) el.innerHTML = (a.activity||[]).map(x => `<div class="activity-item"><div class="activity-dot ${esc(x.event_type)}"></div><div class="activity-body"><strong>${esc(x.label)}</strong><p>${esc(x.detail||'')}${x.ip_address?` · IP ${esc(x.ip_address)}`:''}</p></div><div class="activity-time">${fmtDate(x.created_at)}</div></div>`).join('') || '<div class="muted">No activity recorded yet.</div>';
    }
    if (tab === 'services') {
      const r = await api('/api/profile/services');
      const el = $('#servicesList');
      if (el) el.innerHTML = `<div class="service-grid">${(r.services||[]).map(s => `<div class="service-card"><div class="service-head"><div><h4>${esc(s.name)}</h4><span class="badge ${s.status==='connected'?'ok':'muted'}">${esc(s.status)}</span></div></div><p>${esc(s.service_type)} ${s.secret_hint?`· Secret ${esc(s.secret_hint)}`:''}</p><div class="inline-actions"><button class="btn danger" data-disconnect-service="${s.id}">Revoke</button></div></div>`).join('') || '<div class="note-box">No connected services yet. Add one below.</div>'}</div>`;
    }
  } catch (e) { console.warn('profile extras', e); }
}

function collectChecks(form, name) { return [...form.querySelectorAll(`input[name="${name}"]:checked`)].map(i=>i.value); }
function collectToggles(container) {
  const out = {};
  container.querySelectorAll('[data-pref-toggle]').forEach(btn => { out[btn.dataset.prefToggle] = btn.classList.contains('on'); });
  return out;
}

document.addEventListener('submit', async (e) => {
  const f = e.target;
  if (!(f instanceof HTMLFormElement)) return;
  if (f.id === 'profilePersonalForm') {
    e.preventDefault();
    const fd = new FormData(f);
    const payload = Object.fromEntries([...fd.entries()].map(([k,v])=>[k, String(v).trim()]));
    delete payload.avatar; // file handled separately
    try {
      const p = await api('/api/profile', { method:'PUT', body: JSON.stringify(payload) });
      state.profile = p; USER.name = p.name; USER.email = p.email; localStorage.setItem('stai_user', JSON.stringify(USER));
      const av = $('#avatarBtn'); if (av) av.textContent = initials(p.name,p.email);
      toast('Profile updated'); loadView();
    } catch (err) { toast(err.message); }
  }
  if (f.id === 'passwordForm') {
    e.preventDefault();
    const fd = new FormData(f);
    const cur = String(fd.get('current_password')||'');
    const nw = String(fd.get('new_password')||'');
    const cf = String(fd.get('confirm_password')||'');
    if (nw !== cf) return toast('New passwords do not match');
    try { await api('/api/profile/password', { method:'POST', body: JSON.stringify({current_password:cur, new_password:nw}) }); f.reset(); toast('Password changed'); }
    catch (err) { toast(err.message); }
  }
  if (f.id === 'tradingPrefsForm') {
    e.preventDefault();
    const fd = new FormData(f);
    const prefs = {
      preferred_exchange: String(fd.get('preferred_exchange')||'NSE'),
      default_chart_timeframe: String(fd.get('default_chart_timeframe')||'5m'),
      default_landing_page: String(fd.get('default_landing_page')||'overview'),
      dashboard_layout: String(fd.get('dashboard_layout')||'comfortable'),
      preferred_segments: collectChecks(f,'preferred_segments'),
      preferred_indicators: collectChecks(f,'preferred_indicators'),
      default_watchlist: String(fd.get('default_watchlist')||'').split(',').map(s=>s.trim()).filter(Boolean),
      favorite_stocks: String(fd.get('favorite_stocks')||'').split(',').map(s=>s.trim()).filter(Boolean),
    };
    try { await api('/api/profile/preferences', { method:'PUT', body: JSON.stringify({section:'trading', preferences:prefs}) }); state.profile.preferences.trading = prefs; toast('Trading preferences saved'); }
    catch (err) { toast(err.message); }
  }
  if (f.id === 'aiPrefsForm') {
    e.preventDefault();
    const fd = new FormData(f);
    const prefs = {
      analysis_style: String(fd.get('analysis_style')||'balanced'),
      insight_depth: String(fd.get('insight_depth')||'standard'),
      ema_fast: Number(fd.get('ema_fast')||20), ema_slow: Number(fd.get('ema_slow')||50),
      rsi_period: Number(fd.get('rsi_period')||14),
      macd_fast: Number(fd.get('macd_fast')||12), macd_slow: Number(fd.get('macd_slow')||26), macd_signal: Number(fd.get('macd_signal')||9),
      candlestick_patterns: collectChecks(f,'candlestick_patterns'),
      preferred_indicators: collectChecks(f,'preferred_indicators'),
      ...collectToggles(f),
    };
    try { await api('/api/profile/preferences', { method:'PUT', body: JSON.stringify({section:'ai', preferences:prefs}) }); state.profile.preferences.ai = prefs; toast('AI preferences saved'); }
    catch (err) { toast(err.message); }
  }
  if (f.id === 'notifPrefsForm') {
    e.preventDefault();
    const prefs = collectToggles(f);
    try { await api('/api/profile/notifications', { method:'PUT', body: JSON.stringify({preferences:prefs}) }); state.profile.notifications = prefs; toast('Notification preferences saved'); }
    catch (err) { toast(err.message); }
  }
  if (f.id === 'appPrefsForm') {
    e.preventDefault();
    const fd = new FormData(f);
    const prefs = {
      theme: String(fd.get('theme')||'dark'), language: String(fd.get('language')||'en'),
      currency: String(fd.get('currency')||'INR'), timezone: String(fd.get('timezone')||'Asia/Kolkata'),
      date_format: String(fd.get('date_format')||'DD MMM YYYY'), dashboard_density: String(fd.get('dashboard_density')||'comfortable'),
      accessibility: collectToggles(f),
    };
    try { await api('/api/profile/preferences', { method:'PUT', body: JSON.stringify({section:'app', preferences:prefs}) }); state.profile.preferences.app = prefs; toast('App preferences saved'); }
    catch (err) { toast(err.message); }
  }
  if (f.id === 'serviceForm') {
    e.preventDefault();
    const fd = new FormData(f);
    const payload = {
      service_type: String(fd.get('service_type')||'api'),
      name: String(fd.get('name')||'').trim(),
      config: { note: String(fd.get('config_note')||'').trim() },
      secret_hint: ''
    };
    const secret = String(fd.get('secret')||'').trim();
    if (secret) payload.config.api_key = secret; // backend strips raw secret and stores hint only
    try { await api('/api/profile/services', { method:'POST', body: JSON.stringify(payload) }); f.reset(); toast('Service saved'); loadProfileExtras(); }
    catch (err) { toast(err.message); }
  }
});

document.addEventListener('change', (e) => {
  if (e.target.matches('#targetGroup')) { state.targetGroup = e.target.value; loadTargets(); }
  if (e.target.matches('#targetSort')) { state.targetSort = e.target.value; renderTargets(); }
  if (e.target.matches('#avatarFile')) {
    const file = e.target.files?.[0]; if (!file) return;
    if (file.size > 1_500_000) { toast('Image too large (max 1.5MB)'); e.target.value=''; return; }
    const reader = new FileReader();
    reader.onload = async () => {
      try {
        const p = await api('/api/profile', { method:'PUT', body: JSON.stringify({avatar_url:String(reader.result)}) });
        state.profile = p; toast('Profile photo updated'); loadView();
      } catch (err) { toast(err.message); }
    };
    reader.readAsDataURL(file);
  }
});

document.addEventListener('input', (e) => {
  const isTv = e.target.matches('#tvSearch');
  const isMkt = e.target.matches('#mktSearch');
  const isTarget = e.target.matches('#targetSearch');
  if (!isTv && !isMkt && !isTarget) return;
  if (isTarget) state.targetQuery = e.target.value;
  const q = e.target.value.trim().toLowerCase();
  const selector = isTv ? '[data-tvsymbol]' : isMkt ? '[data-mktsymbol]' : '[data-targetsymbol]';
  document.querySelectorAll(`#view ${selector}`).forEach(el => {
    el.classList.toggle('hidden', !!q && !el.textContent.toLowerCase().includes(q));
  });
});

$('#globalSearch').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.target.value.trim()) {
    state.symbol = e.target.value.trim().toUpperCase(); e.target.value = ''; navigate('markets');
  }
});

if (TOKEN) {
  const avatarEl = $('#avatarBtn') || $('#avatar');
  if (avatarEl) avatarEl.textContent = ((USER.name || USER.email || 'U').slice(0, 2).toUpperCase());
  setInterval(() => { $('#clock').textContent = new Date().toLocaleTimeString('en-IN', { hour12: false }); }, 1000);
  $('#clock').textContent = new Date().toLocaleTimeString('en-IN', { hour12: false });
  connectSocket();
  loadView();
}
