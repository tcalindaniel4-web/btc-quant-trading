/* =====================================================================
   J.A.R.V.I.S. // BTC QUANT TERMINAL - logica interfeței
   Toate datele vin din serverul local (backend/api/server.py).
   ===================================================================== */
'use strict';

const CUL = { sdca: '#0aa5c2', ai: '#c47d14', bh: '#8f78e8', pret: '#38bdd8', text: '#d9f6ff', text2: '#92b8c7',
              muted: '#5f7f8d', grila: 'rgba(0,225,255,0.07)', good: '#34d17e', bad: '#ff5a6e' };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const stare = { pagina: 'comanda', grafice: {}, zileIstoric: 365, boti: {}, date: {}, bt: null, filtruBt: 'toate' };

// ----------------------------------------------------------------- formatare
const nr = (v, d = 0) => v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const usd = (v, d = 0) => v == null || isNaN(v) ? '—' : (v < 0 ? '-$' : '$') + nr(Math.abs(v), d);
const pct = (v, d = 1, semn = true) => v == null || isNaN(v) ? '—' : (semn && v > 0 ? '+' : '') + Number(v).toFixed(d) + '%';
const semnCls = v => v > 0 ? 'poz' : v < 0 ? 'neg' : '';
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const compact = v => Math.abs(v) >= 1e9 ? '$' + (v / 1e9).toFixed(2) + 'B' : Math.abs(v) >= 1e6 ? '$' + (v / 1e6).toFixed(1) + 'M' : usd(v);

// ----------------------------------------------------------------- comunicare cu serverul
async function api(cale, optiuni = {}) {
  const r = await fetch(cale, { headers: { 'Content-Type': 'application/json' }, ...optiuni });
  let corp = null;
  try { corp = await r.json(); } catch (_) { /* fără corp JSON */ }
  if (!r.ok) {
    const err = new Error((corp && corp.detail) || `Eroare server (${r.status})`);
    err.status = r.status;
    throw err;
  }
  return corp;
}
const post = (cale, corp = {}) => api(cale, { method: 'POST', body: JSON.stringify(corp) });

function toast(text, eroare = false) {
  const el = document.createElement('div');
  el.className = 'toast' + (eroare ? ' eroare' : '');
  el.textContent = text;
  $('#toast').appendChild(el);
  setTimeout(() => el.remove(), eroare ? 7000 : 4200);
}

function confirma(titlu, text) {
  return new Promise(rez => {
    $('#modal-titlu').textContent = titlu;
    $('#modal-text').textContent = text;
    $('#modal').classList.remove('hidden');
    const gata = v => { $('#modal').classList.add('hidden'); $('#modal-da').onclick = $('#modal-nu').onclick = null; rez(v); };
    $('#modal-da').onclick = () => gata(true);
    $('#modal-nu').onclick = () => gata(false);
  });
}

const mem = {
  get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* stocare indisponibilă */ } },
};

// ----------------------------------------------------------------- boot
function boot() {
  const el = $('#boot'), txt = $('#boot-text');
  if (mem.get('jarvis-boot') === 'vazut' || matchMedia('(prefers-reduced-motion: reduce)').matches) { el.classList.add('gata'); return; }
  const linii = ['> J.A.R.V.I.S. // BTC QUANT TERMINAL v1.0', '> inițializare nucleu ............ OK',
    '> conectare Binance Spot / Futures  OK', '> pipeline Master_Index ........... OK',
    '> date on-chain BGeometrics ....... OK', '> strategii: SDCA v2 · AI Hedge Fund', '> toate sistemele online.'];
  let i = 0;
  const pas = () => {
    if (i < linii.length) { txt.textContent += linii[i++] + '\n'; setTimeout(pas, 170); }
    else setTimeout(() => el.classList.add('gata'), 380);
  };
  el.onclick = () => el.classList.add('gata');
  pas();
  mem.set('jarvis-boot', 'vazut');
}

// ----------------------------------------------------------------- navigare
function arataPagina(p) {
  stare.pagina = p;
  $$('nav.tabs button').forEach(b => b.classList.toggle('activ', b.dataset.pagina === p));
  $$('.pagina').forEach(s => s.classList.toggle('activa', s.id === 'p-' + p));
  mem.set('jarvis-pagina', p);
  if (p === 'boti') { incarcaBoti(); incarcaLoguri(); }
  if (p === 'heatmap') { if (stare.hm.d) requestAnimationFrame(deseneazaHeatmap); else incarcaHeatmap(); }
  if (p === 'stiri' && Date.now() - stare.stiri.incarcatLa > 120000) incarcaStiri();
  window.scrollTo({ top: 0 });
}

function ceas() {
  const a = new Date();
  $('#ceas-local').textContent = a.toLocaleTimeString('ro-RO');
  $('#ceas-utc').textContent = 'UTC ' + a.toISOString().slice(11, 16) + ' · ' + a.toLocaleDateString('ro-RO');
}

// ----------------------------------------------------------------- grafice (Chart.js)
const pluginCrosshair = {
  id: 'crosshair',
  afterDatasetsDraw(chart) {
    const t = chart.tooltip;
    if (!t || !t.getActiveElements().length) return;
    const x = t.getActiveElements()[0].element.x, { top, bottom } = chart.chartArea, ctx = chart.ctx;
    ctx.save(); ctx.strokeStyle = 'rgba(0,225,255,0.35)'; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); ctx.restore();
  },
};
const pluginEticheteFinal = {   // etichete directe la capătul fiecărei serii (text în culoarea textului, nu a seriei)
  id: 'eticheteFinal',
  afterDatasetsDraw(chart, _a, opt) {
    if (!opt || !opt.activ) return;
    const ctx = chart.ctx, pozitii = [];
    chart.data.datasets.forEach((ds, i) => {
      const meta = chart.getDatasetMeta(i);
      if (meta.hidden || !meta.data.length) return;
      const p = meta.data[meta.data.length - 1];
      pozitii.push({ y: p.y, x: p.x, text: `${ds.label} ${opt.format(ds.data[ds.data.length - 1])}`, cul: ds.borderColor });
    });
    pozitii.sort((a, b) => a.y - b.y);
    for (let i = 1; i < pozitii.length; i++) if (pozitii[i].y - pozitii[i - 1].y < 14) pozitii[i].y = pozitii[i - 1].y + 14;
    ctx.save(); ctx.font = '600 11px "JetBrains Mono", monospace'; ctx.textBaseline = 'middle';
    pozitii.forEach(p => {
      ctx.fillStyle = p.cul; ctx.fillRect(p.x + 6, p.y - 1, 8, 2);
      ctx.fillStyle = CUL.text; ctx.fillText(p.text, p.x + 18, p.y);
    });
    ctx.restore();
  },
};
const pluginZone = {
  id: 'zone',
  beforeDatasetsDraw(chart, _a, opt) {
    if (!opt || opt.buy == null) return;
    const { ctx, chartArea: a, scales: { y } } = chart;
    const yBuy = Math.min(Math.max(y.getPixelForValue(opt.buy), a.top), a.bottom);
    const ySell = Math.min(Math.max(y.getPixelForValue(opt.sell), a.top), a.bottom);
    ctx.save();
    ctx.fillStyle = 'rgba(52,209,126,0.10)'; ctx.fillRect(a.left, yBuy, a.right - a.left, a.bottom - yBuy);
    ctx.fillStyle = 'rgba(255,90,110,0.10)'; ctx.fillRect(a.left, a.top, a.right - a.left, ySell - a.top);
    ctx.strokeStyle = 'rgba(146,184,199,0.35)'; ctx.setLineDash([4, 4]);
    [yBuy, ySell].forEach(v => { ctx.beginPath(); ctx.moveTo(a.left, v); ctx.lineTo(a.right, v); ctx.stroke(); });
    ctx.setLineDash([]); ctx.font = '10px "JetBrains Mono", monospace'; ctx.fillStyle = CUL.muted;
    ctx.fillText('EUFORIE > 0.8', a.left + 6, ySell - 5);
    ctx.fillText('ACUMULARE < -0.5', a.left + 6, yBuy + 12);
    ctx.restore();
  },
};

function configGrafic(formatY, extra = {}) {
  if (window.innerWidth < 760 && extra.etichete) {   // ecran îngust: legenda de sus ajunge, păstrăm spațiul pentru curbe
    extra = { ...extra, etichete: { activ: false }, paddingDreapta: 8 };
  }
  return {
    type: 'line',
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 500 },
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { right: extra.paddingDreapta || 8 } },
      scales: {
        x: { grid: { color: CUL.grila, drawTicks: false }, border: { color: 'rgba(0,225,255,0.15)' },
             ticks: { color: CUL.muted, maxTicksLimit: 7, maxRotation: 0, autoSkip: true, padding: 6, font: { family: 'JetBrains Mono', size: 10.5 } } },
        y: { grid: { color: CUL.grila, drawTicks: false }, border: { display: false },
             ticks: { color: CUL.muted, padding: 8, maxTicksLimit: 6, font: { family: 'JetBrains Mono', size: 10.5 }, callback: formatY },
             ...(extra.y || {}) },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(3,10,16,0.95)', borderColor: 'rgba(0,225,255,0.4)', borderWidth: 1, padding: 10,
          titleColor: CUL.text, bodyColor: CUL.text2, titleFont: { family: 'JetBrains Mono', size: 11.5 },
          bodyFont: { family: 'JetBrains Mono', size: 11.5 }, boxWidth: 10, boxHeight: 3, usePointStyle: false,
          callbacks: extra.tooltip || {},
        },
        eticheteFinal: extra.etichete || { activ: false },
        zone: extra.zone || {},
      },
      elements: { point: { radius: 0, hoverRadius: 4, hitRadius: 8 }, line: { borderWidth: 2, tension: 0 } },
    },
    plugins: [pluginCrosshair, pluginEticheteFinal, pluginZone],
  };
}

function deseneaza(id, cfgFn, date) {
  if (typeof Chart === 'undefined') return;   // librăria nu s-a încărcat (fără internet)
  const vechi = stare.grafice[id];
  if (vechi) vechi.destroy();
  const cfg = cfgFn();
  cfg.data = date;
  stare.grafice[id] = new Chart(document.getElementById(id), cfg);
}

const serie = (label, data, cul, extra = {}) => ({ label, data, borderColor: cul, backgroundColor: cul, pointBackgroundColor: cul,
  pointBorderColor: '#08131d', pointBorderWidth: 2, ...extra });

// ----------------------------------------------------------------- PREȚ ÎN TIMP REAL (WebSocket Binance)
// Browserul se conectează direct la fluxul public Binance (fără cheie): prețul vine la ~1 secundă, fără să
// treacă prin server. Dacă fluxul pică, reconectare automată, iar între timp prețul vine din server la 15 s.
const WS_URLURI = ['wss://stream.binance.com:9443/ws/btcusdt@ticker', 'wss://stream.binance.com:443/ws/btcusdt@ticker'];
stare.live = { ws: null, ultimMesaj: 0, pret: null, incercari: 0, ultimDesenHm: 0 };
const liveActiv = () => Date.now() - stare.live.ultimMesaj < 6000;

function afiseazaPret(p) {
  const el = $('#pret'), vechi = stare.live.pretAfisat;
  el.textContent = usd(p.pret, 2);
  if (vechi != null && p.pret !== vechi) {          // clipire verde / roșie la fiecare schimbare de preț
    el.classList.remove('flash-sus', 'flash-jos');
    void el.offsetWidth;
    el.classList.add(p.pret > vechi ? 'flash-sus' : 'flash-jos');
    clearTimeout(stare.live.tFlash);
    stare.live.tFlash = setTimeout(() => el.classList.remove('flash-sus', 'flash-jos'), 350);
  }
  stare.live.pretAfisat = p.pret;
  if (p.variatie != null) {
    const elv = $('#variatie');
    elv.textContent = (p.variatie >= 0 ? '▲ ' : '▼ ') + pct(p.variatie, 2);
    elv.className = 'variatie ' + (p.variatie >= 0 ? 'sus' : 'jos');
  }
  if (p.max != null) $('#max24').textContent = usd(p.max, 0);
  if (p.min != null) $('#min24').textContent = usd(p.min, 0);
  if (p.volum != null) $('#vol24').textContent = compact(p.volum);
  document.title = `${usd(p.pret, 0)} · J.A.R.V.I.S.`;
}

function pornesteWS() {
  if (!('WebSocket' in window)) return;
  const url = WS_URLURI[stare.live.incercari % WS_URLURI.length];
  let ws;
  try { ws = new WebSocket(url); } catch (_) { return programeazaReconectare(); }
  stare.live.ws = ws;
  ws.onmessage = ev => {
    let t;
    try { t = JSON.parse(ev.data); } catch (_) { return; }
    if (!t || t.c == null) return;
    stare.live.ultimMesaj = Date.now();
    stare.live.incercari = 0;
    const p = { pret: +t.c, variatie: +t.P, max: +t.h, min: +t.l, volum: +t.q };
    stare.live.pret = p.pret;
    afiseazaPret(p);
    $('#led-binance').className = 'led ok';
    $('#sursa-pret').innerHTML = '<i class="led ok puls"></i>LIVE · Binance WebSocket';
    if (Date.now() - stare.live.ultimDesenHm > 1000) {   // heatmap-ul: cel mult o redesenare pe secundă
      stare.live.ultimDesenHm = Date.now();
      actualizeazaPretHeatmap(p.pret);
    }
  };
  ws.onclose = () => { if (stare.live.ws === ws) programeazaReconectare(); };
  ws.onerror = () => { try { ws.close(); } catch (_) { /* deja închis */ } };
}

function programeazaReconectare() {
  stare.live.ws = null;
  stare.live.incercari++;
  $('#sursa-pret').innerHTML = '<i class="led warn"></i>reconectare la fluxul live… (preț din server la 15 s)';
  setTimeout(pornesteWS, Math.min(30000, 1500 * 2 ** Math.min(stare.live.incercari, 5)));
}

function pazaWS() {   // dacă fluxul tace (rețea blocată, tab adormit), îl repornim
  const ws = stare.live.ws;
  if (ws && ws.readyState === WebSocket.OPEN && Date.now() - stare.live.ultimMesaj > 15000) ws.close();
}

// ----------------------------------------------------------------- REACTOR (instrumentul central)
// Cadran de 270°: Master_Index de la -2 (stânga-jos) la +2 (dreapta-jos), cu zonele acumulare / neutru / euforie
// și un ac indicator. Inelul exterior: cele 6 componente ale indexului; lungimea arcului = mărimea contribuției,
// culoarea + semnul din etichetă = direcția (cyan pozitiv, chihlimbar negativ).
const R_NUME = { Z_VWAP: 'VWAP', Z_MACD: 'MACD', Z_RSI: 'RSI', Z_Funding_Rate: 'FUNDING', Adjusted_MVRV: 'MVRV', Z_SOPR: 'SOPR' };

function deseneazaReactor(m) {
  const P = (r, a) => { const t = (a - 90) * Math.PI / 180; return [100 + r * Math.cos(t), 100 + r * Math.sin(t)]; };
  const arc = (r, a0, a1) => {
    const [x0, y0] = P(r, a0), [x1, y1] = P(r, a1);
    return `M${x0.toFixed(2)} ${y0.toFixed(2)}A${r} ${r} 0 ${Math.abs(a1 - a0) > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
  };
  const unghi = v => Math.max(-2, Math.min(2, v)) / 2 * 135;
  const linie = (cls, r0, r1, a) => { const [x0, y0] = P(r0, a), [x1, y1] = P(r1, a);
    return `<line class="${cls}" x1="${x0.toFixed(2)}" y1="${y0.toFixed(2)}" x2="${x1.toFixed(2)}" y2="${y1.toFixed(2)}"/>`; };
  let s = '';

  m.componente.forEach((c, i) => {
    const centru = i * 60, jum = 26 * Math.max(0.07, Math.min(1, Math.abs(c.contributie) / 0.4));
    const [x, y] = P(110, centru);
    s += `<path class="r-pista" stroke-width="7" d="${arc(95, centru - 26, centru + 26)}"/>` +
         `<path class="r-comp r-anim ${c.contributie < 0 ? 'neg' : 'poz'}" pathLength="1" stroke-width="7" d="${arc(95, centru - jum, centru + jum)}"/>` +
         `<text class="r-nume" x="${x.toFixed(1)}" y="${(y - 0.8).toFixed(1)}">${esc(R_NUME[c.cheie] || c.nume)}</text>` +
         `<text class="r-val" x="${x.toFixed(1)}" y="${(y + 6.2).toFixed(1)}">${(c.contributie >= 0 ? '+' : '−') + Math.abs(c.contributie).toFixed(2)}</text>`;
  });

  [[-2, m.prag_buy, 'acc'], [m.prag_buy, m.prag_sell, 'neu'], [m.prag_sell, 2, 'euf']].forEach(([a, b, cls]) => {
    s += `<path class="r-zona r-anim ${cls}" pathLength="1" stroke-width="4.5" d="${arc(77, unghi(a) + 0.9, unghi(b) - 0.9)}"/>`;
  });
  [-2, -1, 0, 1, 2].forEach(v => {
    const [x, y] = P(67, unghi(v));
    s += linie('r-gradatie', 80.5, 83.5, unghi(v)) +
         `<text class="r-cifra" x="${x.toFixed(1)}" y="${(y + 2).toFixed(1)}">${v > 0 ? '+' + v : v}</text>`;
  });
  s += linie('r-ac', 62, 86, unghi(m.valoare));

  $('#reactor-dinamic').innerHTML = s;
  if (!stare.reactorPornit) {       // animația de pornire rulează o singură dată, după ecranul de boot
    stare.reactorPornit = true;
    const porneste = () => requestAnimationFrame(() => requestAnimationFrame(() => $('#reactor').classList.add('pornit')));
    if ($('#boot').classList.contains('gata')) porneste(); else setTimeout(porneste, 1900);
  }
}

// ----------------------------------------------------------------- PIAȚĂ
async function incarcaPiata() {
  try {
    const d = await api('/api/piata');
    stare.date.piata = d;
    if (!liveActiv()) {   // prețul vine din WebSocket când e conectat; serverul e doar rezervă
      afiseazaPret({ pret: d.pret, variatie: d.live.ok ? d.live.variatie_24h : null,
                     max: d.live.ok ? d.live.max_24h : null, min: d.live.ok ? d.live.min_24h : null,
                     volum: d.live.ok ? d.live.volum_24h_usd : null });
      $('#led-binance').className = 'led ' + (d.live.ok ? 'ok' : 'bad');
    }
    $('#rsi').textContent = nr(d.master.rsi, 1);
    $('#led-master').className = 'led ' + (d.prospetime.la_zi ? 'ok' : 'warn');
    const zileOnchain = d.prospetime.onchain_zi ? Math.round((new Date(d.prospetime.azi_utc) - new Date(d.prospetime.onchain_zi)) / 864e5) : 99;
    $('#led-onchain').className = 'led ' + (zileOnchain <= 9 ? 'ok' : 'warn');

    const m = d.master;
    $('#reactor-valoare').textContent = (m.valoare >= 0 ? '+' : '') + m.valoare.toFixed(2);
    const sem = $('#reactor-semnal'); sem.textContent = m.semnal; sem.className = 'semnal ' + m.semnal;
    deseneazaReactor(m);

    $('#componente').innerHTML = m.componente.map(c => {
      const w = Math.min(50, Math.abs(c.contributie) / 0.4 * 50);
      const stanga = c.contributie >= 0 ? 50 : 50 - w;
      return `<div class="comp" title="${esc(c.nume)}: valoare ${nr(c.valoare, 2)} × pondere ${c.pondere}">
        <span class="nume">${esc(c.nume)}</span>
        <span class="bara"><i class="${c.contributie < 0 ? 'neg' : ''}" style="left:${stanga}%;width:${w}%"></i></span>
        <span class="val">${(c.contributie >= 0 ? '+' : '') + c.contributie.toFixed(2)}</span></div>`;
    }).join('');
    if (!liveActiv()) actualizeazaPretHeatmap(d.pret);
    $('#nota-onchain').textContent = `Master_Index din ${m.data}. Date on-chain (MVRV, SOPR) din ${m.data_onchain || '—'}: ` +
      `BGeometrics gratuit le publică cu ~7 zile întârziere, exact cum le folosește și backtest-ul.`;
  } catch (e) {
    if (!liveActiv()) $('#led-binance').className = 'led bad';
    toast('Nu pot citi datele de piață: ' + e.message, true);
  }
}

// ----------------------------------------------------------------- carduri boți (pagina COMANDĂ)
async function incarcaCarduriBoti() {
  try {
    const [s, a, b] = await Promise.all([api('/api/sdca'), api('/api/ai'), api('/api/boti')]);
    stare.date.sdca = s; stare.date.ai = a; stare.boti = b;
    const ledBot = k => b[k].ruleaza ? '<i class="led ok"></i>RULEAZĂ' : b[k].ciclu_in_curs ? '<i class="led warn"></i>CICLU' : '<i class="led"></i>OPRIT';
    const decS = s.previzualizare.mesaje.length ? s.previzualizare.mesaje.map(esc).join('<br>') : 'STANDBY — nicio condiție de execuție îndeplinită';
    const pS = s.portofoliu;
    const pA = a.portofoliu;
    const da = a.voturi.filter(v => v.da).length;
    $('#carduri-boti').innerHTML = `
      <div class="card-bot">
        <div class="cap"><span class="titlu"><i style="background:var(--s-sdca)"></i>SDCA v2</span><span class="stare-bot">${ledBot('sdca')}</span></div>
        ${pS ? `<div class="valoare-bot">${usd(pS.valoare, 0)} <span class="variatie ${pS.pl_procent >= 0 ? 'sus' : 'jos'}">${pct(pS.pl_procent, 2)}</span></div>
                <div class="t2" style="font-size:12.5px">cash ${usd(pS.cash)} · ${nr(pS.btc, 4)} BTC</div>`
             : `<div class="t2">Portofoliu neinițializat — pornește botul din BOȚI LIVE.</div>`}
        <div class="decizie"><b>Azi ar face:</b> ${decS}</div>
      </div>
      <div class="card-bot">
        <div class="cap"><span class="titlu"><i style="background:var(--s-ai)"></i>AI HEDGE FUND</span><span class="stare-bot">${ledBot('ai')}</span></div>
        ${pA ? `<div class="valoare-bot">${usd(pA.valoare, 0)} <span class="variatie ${pA.pl_procent >= 0 ? 'sus' : 'jos'}">${pct(pA.pl_procent, 2)}</span></div>
                <div class="t2" style="font-size:12.5px">Buy &amp; Hold de la pornire: ${pct(pA.buyhold_procent, 2)} · expunere ${pct(pA.expunere * 100, 0, false)}</div>
                <div class="expunere" title="Expunere BTC"><i style="width:${pA.expunere * 100}%"></i></div>`
             : `<div class="t2">Portofoliu neinițializat — pornește botul din BOȚI LIVE.</div>`}
        <div class="decizie"><b>Semnal ${esc(a.zi_semnal)}:</b> ${da}/12 experți văd trend ascendent → țintă ${pct(a.tinta_maine * 100, 0, false)}${a.funding_fierbinte ? ' (funding fierbinte)' : ''}</div>
      </div>`;
  } catch (e) {
    $('#carduri-boti').innerHTML = `<div class="t2">Nu pot citi starea boților: ${esc(e.message)}</div>`;
  }
}

// ----------------------------------------------------------------- grafice istoric
async function incarcaIstoric() {
  try {
    const d = await api('/api/istoric?zile=' + stare.zileIstoric);
    deseneaza('g-pret', () => configGrafic(v => '$' + nr(v / 1000, 0) + 'k', {
      tooltip: { label: c => ' Preț: ' + usd(c.parsed.y, 0) } }),
      { labels: d.data, datasets: [serie('Preț BTC', d.pret, CUL.pret, { fill: { target: 'origin', above: 'rgba(56,189,216,0.06)' } })] });
    deseneaza('g-master', () => configGrafic(v => v.toFixed(1), {
      zone: { buy: d.prag_buy, sell: d.prag_sell },
      tooltip: { label: c => ' Master_Index: ' + c.parsed.y.toFixed(2) } }),
      { labels: d.data, datasets: [serie('Master_Index', d.master, CUL.pret)] });
  } catch (e) { toast('Istoric indisponibil: ' + e.message, true); }
}

// ----------------------------------------------------------------- comparație strategii
async function incarcaComparatie() {
  try {
    const d = await api('/api/backtest');
    $('#comparatie-perioada').textContent = `${d.start} → ${d.end} · capital inițial ${usd(d.capital)}`;
    const idx = new Map(d.data.map((z, i) => [z, i]));
    const raze = d.data.map(() => 0), marcaje = {};
    d.marcaje_sdca.forEach(m => { const i = idx.get(m.data); if (i != null) { raze[i] = 6; marcaje[i] = m; } });
    deseneaza('g-comparatie', () => configGrafic(v => '$' + nr(v / 1000, 0) + 'k', {
      paddingDreapta: 185,
      etichete: { activ: true, format: v => usd(v, 0) },
      tooltip: {
        label: c => ` ${c.dataset.label}: ${usd(c.parsed.y, 0)}`,
        afterBody: items => {
          const m = marcaje[items[0].dataIndex];
          return m ? [``, `▲ SDCA: ${m.tip} ${m.motiv}`, `  ${usd(m.suma, 0)} @ ${usd(m.pret, 0)}`] : [];
        } } }),
      { labels: d.data, datasets: [
        serie('SDCA v2', d.sdca, CUL.sdca, { pointRadius: raze, pointStyle: 'triangle', pointHoverRadius: 6 }),
        serie('AI Hedge Fund', d.ai, CUL.ai),
        serie('Buy & Hold', d.bh, CUL.bh) ] });
    const s = d.statistici;
    const rand = (k, nume, cul) => `<tr><td><span class="eticheta-tip" style="color:${cul};border-color:${cul}">●</span> ${nume}</td>
      <td class="n">${usd(s[k].final)}</td><td class="n ${semnCls(s[k].total)}">${pct(s[k].total)}</td><td class="n">${pct(s[k].cagr)}</td>
      <td class="n neg">${pct(s[k].max_dd)}</td><td class="n">${nr(s[k].sharpe, 2)}</td><td class="n">${s[k].tranzactii}</td></tr>`;
    $('#tabel-comparatie').innerHTML = `<thead><tr><th>STRATEGIE</th><th class="n">CAPITAL FINAL</th><th class="n">RANDAMENT</th>
      <th class="n">ANUAL (CAGR)</th><th class="n">DRAWDOWN MAX</th><th class="n">SHARPE</th><th class="n">TRANZACȚII</th></tr></thead>
      <tbody>${rand('sdca', 'SDCA v2', CUL.sdca)}${rand('ai', 'AI Hedge Fund', CUL.ai)}${rand('bh', 'Buy &amp; Hold', CUL.bh)}</tbody>`;
  } catch (e) { toast('Comparația strategiilor e indisponibilă: ' + e.message, true); }
}

// ----------------------------------------------------------------- BOȚI LIVE
const INFO_BOTI = {
  sdca: { titlu: 'SDCA v2 // MASTER_INDEX', cul: 'var(--s-sdca)',
          descriere: 'Acumulează în zonele de subevaluare (Master_Index < -0.5), vinde 70% la euforie confirmată on-chain, apoi moonbag. Ciclu: date noi + decizie.' },
  ai:   { titlu: 'AI HEDGE FUND // TREND & MOMENTUM', cul: 'var(--s-ai)',
          descriere: '12 experți (6 trend SMA + 6 momentum) votează zilnic; procentul de voturi DA = expunerea BTC (trepte de 25%), cu filtru de funding.' },
};

function construiestePanouriBoti() {
  $('#panouri-boti').innerHTML = ['sdca', 'ai'].map(k => `
    <div class="panel" id="panou-${k}">
      <h2><i style="width:10px;height:10px;border-radius:2px;background:${INFO_BOTI[k].cul};display:inline-block"></i>${INFO_BOTI[k].titlu}</h2>
      <p class="t2" style="margin:-4px 0 12px;font-size:13.5px">${INFO_BOTI[k].descriere}</p>
      <div class="stare-bot" id="status-${k}" style="margin-bottom:12px"><i class="led"></i>—</div>
      <div class="rand-controale">
        <label class="camp" id="camp-capital-${k}">CAPITAL INIȚIAL ($)<input type="number" id="capital-${k}" value="10000" min="10" step="any" style="width:120px"></label>
        <label class="camp">CICLU (${k === 'sdca' ? 'ORE' : 'MINUTE'})<input type="number" id="interval-${k}" value="${k === 'sdca' ? 3 : 15}" min="${k === 'sdca' ? 0.25 : 1}" step="any" style="width:90px"></label>
        <button class="btn primar" data-actiune="porneste" data-bot="${k}">▶ PORNEȘTE</button>
        <button class="btn" data-actiune="opreste" data-bot="${k}">■ OPREȘTE</button>
        <button class="btn" data-actiune="ciclu" data-bot="${k}">⟳ UN CICLU ACUM</button>
        <button class="btn pericol" data-actiune="reseteaza" data-bot="${k}">RESETEAZĂ</button>
      </div>
      <h3>PORTOFOLIU VIRTUAL</h3>
      <div class="tiles" id="tiles-${k}"></div>
      <h3>SEMNAL CURENT</h3>
      <div id="semnal-${k}"></div>
      <h3>LOG LIVE</h3>
      <div class="terminal" id="log-${k}">Se încarcă log-ul…</div>
      ${k === 'ai' ? '<h3>ULTIMELE TRANZACȚII</h3><div class="tabel-wrap"><table id="jurnal-ai"></table></div>' : ''}
    </div>`).join('');
  $$('#panouri-boti [data-actiune]').forEach(b => b.addEventListener('click', () => actiuneBot(b.dataset.bot, b.dataset.actiune)));
}

const tile = (et, v, sub = '', cls = '') => `<div class="tile"><div class="et">${et}</div><div class="v ${cls}">${v}</div>${sub ? `<div class="sub">${sub}</div>` : ''}</div>`;

async function incarcaBoti() {
  try {
    const [s, a, b] = await Promise.all([api('/api/sdca'), api('/api/ai'), api('/api/boti')]);
    stare.date.sdca = s; stare.date.ai = a; stare.boti = b;
    actualizeazaStatusBoti(b);

    const pS = s.portofoliu;
    $('#tiles-sdca').innerHTML = pS
      ? tile('VALOARE', usd(pS.valoare, 2), `din ${usd(pS.capital_initial)}`) +
        tile('PROFIT / PIERDERE', pct(pS.pl_procent, 2), usd(pS.valoare - pS.capital_initial, 2), semnCls(pS.pl_procent)) +
        tile('CASH', usd(pS.cash, 2)) + tile('BTC', nr(pS.btc, 6), pS.pret_mediu ? 'preț mediu ' + usd(pS.pret_mediu, 0) : '') +
        tile('ULTIMA DECIZIE', esc(pS.ultima_rulare || '—'))
      : `<div class="t2">Neinițializat. Alege capitalul și apasă PORNEȘTE sau UN CICLU ACUM.</div>`;
    const c = s.context;
    $('#semnal-sdca').innerHTML = `<div class="tiles">
        ${tile('MASTER_INDEX', (c.master_index >= 0 ? '+' : '') + nr(c.master_index, 2), c.master_index < -0.5 ? 'zonă de acumulare' : c.master_index > 0.8 ? 'zonă de euforie' : 'zonă neutră')}
        ${tile('MVRV AJUSTAT', nr(c.mvrv_ajustat, 2), `prag top ${nr(c.prag_mvrv_top, 2)}`)}
        ${tile('SUB VÂRF 90Z', pct(-c.sub_varf_90z * 100, 1), `vârf ${usd(c.varf_90z)}`, 'neg')}
        ${tile('SMA 50', usd(c.sma_50), s.pret < c.sma_50 ? 'prețul e sub medie' : 'prețul e peste medie')}</div>
      <div class="decizie" style="margin-top:10px"><b>Decizia de azi (${esc(c.zi)}):</b>
        ${s.previzualizare.mesaje.length ? s.previzualizare.mesaje.map(esc).join('<br>') : 'STANDBY — nicio condiție de execuție îndeplinită'}
        <div class="muted" style="font-size:12px;margin-top:3px">${esc(s.previzualizare.nota)}</div></div>`;

    const pA = a.portofoliu;
    $('#tiles-ai').innerHTML = pA
      ? tile('VALOARE', usd(pA.valoare, 2), `din ${usd(pA.capital_initial)}`) +
        tile('PROFIT / PIERDERE', pct(pA.pl_procent, 2), `Buy & Hold: ${pct(pA.buyhold_procent, 2)}`, semnCls(pA.pl_procent)) +
        tile('EXPUNERE BTC', pct(pA.expunere * 100, 0, false), `țintă ${pct(pA.tinta * 100, 0, false)}`) +
        tile('CASH / BTC', usd(pA.cash, 0), nr(pA.btc, 6) + ' BTC') +
        tile('TRANZACȚII', pA.nr_tranzactii, `comisioane ${usd(pA.comisioane, 2)}`)
      : `<div class="t2">Neinițializat. Alege capitalul și apasă PORNEȘTE sau UN CICLU ACUM.</div>`;
    $('#semnal-ai').innerHTML = `
      <div class="voturi">${a.voturi.map(v => `<div class="vot ${v.da ? 'da' : 'nu'}" title="${v.grup}: ${v.da ? 'DA (trend ascendent)' : 'NU'}">${esc(v.nume)}<br>${v.da ? '▲' : '▼'}</div>`).join('')}</div>
      <div class="tiles" style="margin-top:10px">
        ${tile('SCOR FINAL', pct(a.scor_final * 100, 0, false), `trend ${pct(a.scor_trend * 100, 0, false)} · momentum ${pct(a.scor_momentum * 100, 0, false)}`)}
        ${tile('ȚINTĂ EXPUNERE', pct(a.tinta_maine * 100, 0, false), 'pentru următoarea închidere')}
        ${tile('FUNDING 7Z', nr(a.funding_7d, 4) + '%', a.funding_fierbinte ? '⚠ fierbinte: expunere ×0.5' : `normal (prag ${a.prag_funding}%)`)}
        ${tile('VOLATILITATE 30Z', pct(a.volatilitate_30z * 100, 0, false), `RSI ${nr(a.rsi, 0)} · sub ATH ${pct(a.sub_ath * 100, 0)}`)}</div>
      <p class="nota">Semnal calculat pe ziua închisă ${esc(a.zi_semnal)} (00:00 UTC).</p>`;
    $('#jurnal-ai').innerHTML = a.jurnal.length
      ? `<thead><tr><th>EXECUTAT</th><th>TIP</th><th class="n">PREȚ</th><th class="n">SUMĂ</th><th class="n">EXPUNERE</th><th class="n">PORTOFOLIU</th></tr></thead><tbody>` +
        a.jurnal.map(t => `<tr><td class="num">${esc(t.Executat_la)}</td><td><span class="eticheta-tip ${t.Actiune}">${t.Actiune}</span></td>
          <td class="n">${usd(t.Pret, 0)}</td><td class="n">${usd(t.Suma_USD, 2)}</td>
          <td class="n">${pct(t.Expunere_veche * 100, 0, false)} → ${pct(t.Expunere_noua * 100, 0, false)}</td><td class="n">${usd(t.Valoare_portofoliu, 2)}</td></tr>`).join('') + '</tbody>'
      : '<tbody><tr><td class="t2">Nicio tranzacție încă.</td></tr></tbody>';
  } catch (e) { toast('Nu pot citi boții: ' + e.message, true); }
}

function actualizeazaStatusBoti(b) {
  ['sdca', 'ai'].forEach(k => {
    const s = b[k], el = $('#status-' + k);
    if (!el) return;
    el.innerHTML = s.ruleaza
      ? `<i class="led ok"></i>RULEAZĂ AUTONOM · PORNIT ${esc(s.proces.pornit_la)} · CICLU LA ${s.proces.interval} ${s.proces.unitate.toUpperCase()}`
      : s.ciclu_in_curs ? '<i class="led warn"></i>CICLU MANUAL ÎN CURS…' : '<i class="led"></i>OPRIT';
    const ocupat = s.ruleaza || s.ciclu_in_curs;
    $(`[data-actiune="porneste"][data-bot="${k}"]`).disabled = ocupat;
    $(`[data-actiune="ciclu"][data-bot="${k}"]`).disabled = ocupat;
    $(`[data-actiune="reseteaza"][data-bot="${k}"]`).disabled = ocupat || !s.initializat;
    $(`[data-actiune="opreste"][data-bot="${k}"]`).disabled = !s.ruleaza;
    $('#capital-' + k).disabled = s.initializat;
    $('#camp-capital-' + k).title = s.initializat ? 'Portofoliul există deja. Resetează-l pentru un capital nou.' : '';
    $('#interval-' + k).disabled = s.ruleaza;
  });
}

async function actiuneBot(bot, actiune) {
  const capital = parseFloat($('#capital-' + bot).value) || null;
  const interval = parseFloat($('#interval-' + bot).value) || null;
  if (actiune === 'reseteaza') {
    const ok = await confirma('RESETARE PORTOFOLIU', `Portofoliul virtual ${bot === 'sdca' ? 'SDCA v2' : 'AI Hedge Fund'} va fi ARHIVAT (nu șters), iar următoarea pornire începe un portofoliu nou. Continui?`);
    if (!ok) return;
  }
  try {
    const r = await post(`/api/boti/${bot}/${actiune}`, actiune === 'opreste' || actiune === 'reseteaza' ? {} : { capital, interval });
    toast({ porneste: 'Bot pornit în mod autonom.', opreste: 'Bot oprit. Portofoliul rămâne salvat.',
            ciclu: 'Ciclu pornit — urmărește log-ul.', reseteaza: 'Portofoliu arhivat: ' + ((r.arhivate || []).join(', ') || 'nimic de arhivat') }[actiune]);
    actualizeazaStatusBoti(await api('/api/boti'));
    setTimeout(() => { incarcaLoguri(); incarcaBoti(); }, 1200);
  } catch (e) { toast(e.message, true); }
}

async function incarcaLoguri() {
  for (const k of ['sdca', 'ai']) {
    const el = $('#log-' + k);
    if (!el) continue;
    try {
      const { linii } = await api(`/api/boti/${k}/log?linii=300`);
      const jos = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      el.innerHTML = linii.length ? linii.map(l => {
        const cls = /\[PLATFORMĂ/.test(l) ? 'platforma' : /❌|Eroare|Traceback/.test(l) ? 'eroare' : /TRANZACȚIE|BUY|SELL/.test(l) ? 'tranz' : '';
        return cls ? `<span class="${cls}">${esc(l)}</span>` : esc(l);
      }).join('\n') : 'Log gol. Pornește botul sau rulează un ciclu.';
      if (jos) el.scrollTop = el.scrollHeight;
    } catch (_) { /* serverul poate fi ocupat; reîncercăm la următorul tick */ }
  }
}

// ----------------------------------------------------------------- HEATMAP LICHIDĂRI (Open Interest)
const RAMPA_HM = [[0, [8, 19, 29]], [0.15, [11, 51, 70]], [0.35, [11, 95, 122]], [0.6, [10, 165, 194]], [0.82, [98, 220, 239]], [1, [232, 252, 255]]];
const CUL_PRET_HM = '#ffb547';
stare.hm = { iv: '1h', tip: 'toate', d: null, geom: null };

function culoareHM(f) {   // rampă secvențială, o singură nuanță (cyan), luminozitate crescătoare
  for (let i = 1; i < RAMPA_HM.length; i++) {
    if (f <= RAMPA_HM[i][0]) {
      const [a, ca] = RAMPA_HM[i - 1], [b, cb] = RAMPA_HM[i], t = (f - a) / (b - a);
      return ca.map((v, k) => Math.round(v + (cb[k] - v) * t));
    }
  }
  return RAMPA_HM[RAMPA_HM.length - 1][1];
}

// Între recalculările modelului (la 60 s), lumânarea curentă urmează prețul live (actualizat la 15 s).
function actualizeazaPretHeatmap(pret) {
  const h = stare.hm.d;
  if (!h || !pret) return;
  const u = h.pret.close.length - 1;
  h.pret.close[u] = pret;
  h.pret.high[u] = Math.max(h.pret.high[u], pret);
  h.pret.low[u] = Math.min(h.pret.low[u], pret);
  h.pret_curent = pret;
  stare.hm.pretLa = Date.now();
  if (stare.pagina === 'heatmap') deseneazaHeatmap();
}

function eticheteLiveHeatmap() {
  if (stare.pagina !== 'heatmap' || !stare.hm.calculatLa) return;
  const sec = t => Math.max(0, Math.round((Date.now() - t) / 1000));
  const model = sec(stare.hm.calculatLa), pret = stare.hm.pretLa ? sec(stare.hm.pretLa) : null;
  $('#hm-live').innerHTML = `<i class="led ok puls"></i>LIVE · model recalculat acum ${model}s (la fiecare 60 s)` +
    (pret != null ? ` · preț actualizat acum ${pret}s (la fiecare 15 s)` : '');
}

async function incarcaHeatmap() {
  if (!stare.hm.d) $('#hm-incarcare').classList.remove('hidden');   // la reîmprospătări nu mai acoperim harta
  try {
    const d = await api('/api/heatmap?interval=' + stare.hm.iv);
    stare.hm.d = d;
    stare.hm.calculatLa = Date.now();
    const s = d.sumar;
    $('#hm-tiles').innerHTML =
      tile('PREȚ BTC (FUTURES)', usd(d.pret_curent, 0), `interval ${d.interval} · ${d.timp.length} lumânări`) +
      tile('OPEN INTEREST', '$' + nr(d.oi_curent / 1e9, 2) + 'B', `<span class="${semnCls(d.oi_variatie_pct)}">${pct(d.oi_variatie_pct, 1)}</span> în ${d.zile} zile`) +
      tile('LONG-URI ≤5% SUB PREȚ', compact(s.long_sub_5pct), 'lichidări estimate dacă scade 5%') +
      tile('SHORT-URI ≤5% PESTE PREȚ', compact(s.short_peste_5pct), 'lichidări estimate dacă urcă 5%');
    const randuri = [...d.clustere.peste_pret.slice().reverse(), { separator: true }, ...d.clustere.sub_pret];
    $('#hm-clustere').innerHTML = `<thead><tr><th>ZONĂ</th><th class="n">PREȚ</th><th class="n">DISTANȚĂ</th><th class="n">LICHIDĂRI EST.</th></tr></thead><tbody>` +
      randuri.map(c => c.separator
        ? `<tr><td colspan="4" class="num" style="color:${CUL_PRET_HM};text-align:center">── preț curent ${usd(d.pret_curent, 0)} ──</td></tr>`
        : `<tr><td><span class="eticheta-tip ${c.tip === 'SHORT' ? 'SELL' : 'BUY'}">${c.tip}</span></td><td class="n">${usd(c.pret, 0)}</td>
           <td class="n ${semnCls(c.distanta_pct)}">${pct(c.distanta_pct, 1)}</td><td class="n">${compact(c.usd)}</td></tr>`).join('') + '</tbody>';
    const lev = Object.entries(d.model.leviere).map(([k, v]) => `${k}x: ${Math.round(v * 100)}%`).join(', ');
    $('#hm-model').innerHTML = `Când Open Interest-ul crește, pozițiile noi sunt împărțite în long/short după raportul taker buy/sell și
      li se calculează prețul de lichidare pentru levierul presupus (${lev}; marjă de mentenanță ${d.model.marja_mentenanta * 100}%).
      Nivelurile dispar când prețul trece prin ele, iar scăderile de OI le reduc proporțional. <b>Estimare</b>, nu date exacte:
      levierul real al traderilor nu e public. Sursa: ${esc(d.model.sursa)}.`;
    deseneaza('g-oi', () => configGrafic(v => '$' + v.toFixed(1) + 'B', { tooltip: { label: c => ' Open Interest: $' + c.parsed.y.toFixed(2) + 'B' } }),
      { labels: d.timp, datasets: [serie('Open Interest', d.oi, CUL.pret, { fill: { target: 'origin', above: 'rgba(56,189,216,0.06)' } })] });
    deseneazaHeatmap();
  } catch (e) {
    toast('Heatmap indisponibil: ' + e.message, true);
  } finally { $('#hm-incarcare').classList.add('hidden'); }
}

function deseneazaHeatmap() {
  const d = stare.hm.d;
  if (!d) return;
  const cnv = $('#hm-canvas'), wrap = $('#hm-wrap'), dpr = window.devicePixelRatio || 1;
  const W = wrap.clientWidth, H = wrap.clientHeight;
  cnv.width = W * dpr; cnv.height = H * dpr;
  const ctx = cnv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const m = { st: W < 500 ? 52 : 66, dr: 10, sus: 10, jos: 26 };
  const pw = W - m.st - m.dr, ph = H - m.sus - m.jos;
  const T = d.timp.length, N = d.niveluri.length;

  // valorile afișate (după filtru) și scala de culoare (percentila 99 -> evităm ca un singur nivel extrem să "stingă" restul)
  const val = (t, i) => (stare.hm.tip !== 'short' ? d.long_k[t][i] : 0) + (stare.hm.tip !== 'long' ? d.short_k[t][i] : 0);
  const toate = [];
  for (let t = 0; t < T; t++) for (let i = 0; i < N; i++) { const v = val(t, i); if (v > 0) toate.push(v); }
  toate.sort((a, b) => a - b);
  const vmax = toate.length ? toate[Math.floor(toate.length * 0.99)] : 1;
  $('#hm-max').textContent = 'mai multe (≥ ' + compact(vmax * 1000) + ' / nivel)';

  // celulele: desenate într-o imagine T×N, apoi scalate fără netezire
  const img = new ImageData(T, N);
  for (let t = 0; t < T; t++) for (let i = 0; i < N; i++) {
    const v = val(t, i), p = ((N - 1 - i) * T + t) * 4;
    if (v <= 0) { img.data[p + 3] = 0; continue; }
    const [r, g, b] = culoareHM(Math.min(1, Math.sqrt(v / vmax)));
    img.data[p] = r; img.data[p + 1] = g; img.data[p + 2] = b; img.data[p + 3] = 255;
  }
  const off = document.createElement('canvas'); off.width = T; off.height = N;
  off.getContext('2d').putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(off, m.st, m.sus, pw, ph);

  const jos = d.niveluri[0] - d.pas_nivel / 2, sus = d.niveluri[N - 1] + d.pas_nivel / 2;
  const y = pret => m.sus + ph * (1 - (pret - jos) / (sus - jos));
  const x = t => m.st + pw * (t + 0.5) / T;

  // axa de preț + grilă
  ctx.font = '10.5px "JetBrains Mono", monospace'; ctx.textBaseline = 'middle'; ctx.textAlign = 'right';
  const pasPret = [500, 1000, 2000, 2500, 5000, 10000].find(p => (sus - jos) / p <= 9) || 20000;
  for (let p = Math.ceil(jos / pasPret) * pasPret; p <= sus; p += pasPret) {
    ctx.strokeStyle = 'rgba(0,225,255,0.06)'; ctx.beginPath(); ctx.moveTo(m.st, y(p)); ctx.lineTo(m.st + pw, y(p)); ctx.stroke();
    ctx.fillStyle = CUL.muted; ctx.fillText('$' + nr(p / 1000, pasPret < 1000 ? 1 : 0) + 'k', m.st - 6, y(p));
  }
  // axa de timp
  ctx.textAlign = 'center'; ctx.textBaseline = 'top';
  const nrEt = W < 500 ? 3 : 6;
  for (let k = 0; k < nrEt; k++) {
    const t = Math.round((T - 1) * (k + 0.5) / nrEt);
    ctx.fillStyle = CUL.muted; ctx.fillText(d.timp[t].slice(5, stare.hm.iv === '15m' ? 16 : 10), x(t), m.sus + ph + 7);
  }
  // linia prețului + prețul curent
  ctx.strokeStyle = CUL_PRET_HM; ctx.lineWidth = 1.5; ctx.beginPath();
  d.pret.close.forEach((p, t) => t ? ctx.lineTo(x(t), y(p)) : ctx.moveTo(x(t), y(p)));
  ctx.stroke();
  const yc = y(d.pret_curent);
  ctx.setLineDash([4, 4]); ctx.strokeStyle = 'rgba(255,181,71,0.55)'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(m.st, yc); ctx.lineTo(m.st + pw, yc); ctx.stroke(); ctx.setLineDash([]);

  stare.hm.geom = { m, pw, ph, T, N, jos, sus };
}

function hoverHeatmap(ev) {
  const g = stare.hm.geom, d = stare.hm.d, tip = $('#hm-tooltip');
  if (!g || !d) return;
  const r = $('#hm-canvas').getBoundingClientRect(), mx = ev.clientX - r.left, my = ev.clientY - r.top;
  if (mx < g.m.st || mx > g.m.st + g.pw || my < g.m.sus || my > g.m.sus + g.ph) { tip.classList.add('hidden'); return; }
  const t = Math.min(g.T - 1, Math.floor((mx - g.m.st) / g.pw * g.T));
  const i = Math.min(g.N - 1, Math.floor((1 - (my - g.m.sus) / g.ph) * g.N));
  const lo = d.niveluri[i] - d.pas_nivel / 2, hi = d.niveluri[i] + d.pas_nivel / 2;
  tip.innerHTML = `<b>${esc(d.timp[t])} UTC</b><br>nivel ${usd(lo, 0)} – ${usd(hi, 0)}<br>
    lichidări LONG est.: <b>${compact(d.long_k[t][i] * 1000)}</b><br>lichidări SHORT est.: <b>${compact(d.short_k[t][i] * 1000)}</b><br>
    preț închidere: ${usd(d.pret.close[t], 0)}`;
  tip.classList.remove('hidden');
  const w = tip.offsetWidth, h = tip.offsetHeight;
  tip.style.left = Math.min(mx + 14, r.width - w - 6) + 'px';
  tip.style.top = Math.max(6, Math.min(my - h / 2, r.height - h - 6)) + 'px';
}

// ----------------------------------------------------------------- ȘTIRI
stare.stiri = { d: null, cat: 'toate', incarcatLa: 0 };

function cand(iso) {   // "acum 12 min" / "acum 3 h" / data, după vechime
  const min = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (min < 60) return `acum ${min} min`;
  if (min < 24 * 60) return `acum ${Math.round(min / 60)} h`;
  return new Date(iso).toLocaleDateString('ro-RO', { day: 'numeric', month: 'short' });
}

async function incarcaStiri() {
  try {
    const d = await api('/api/stiri');
    stare.stiri.d = d; stare.stiri.incarcatLa = Date.now();
    $('#cotatii').innerHTML = d.cotatii.map(c => `
      <div class="cotatie cat-${c.categorie}">
        <div class="nume">${esc(c.nume)}</div>
        <div class="pret">${c.pret == null ? '—' : usd(c.pret, c.pret > 1000 ? 0 : 2)}</div>
        <div class="det">${c.variatie_pct == null ? 'indisponibil' :
          `<span class="${semnCls(c.variatie_pct)}">${pct(c.variatie_pct, 2)}</span><span class="det-lung"> față de închiderea anterioară, preț ${cand(c.ora)}</span>`}</div>
      </div>`).join('');
    afiseazaStiri();
    afiseazaUltimaStire();
  } catch (e) {
    if (!stare.stiri.d) $('#us-continut').innerHTML = '<span class="t2">Știrile nu sunt disponibile acum. Reîncerc automat.</span>';
    $('#lista-stiri').innerHTML = `<li class="t2" style="padding:14px 0">Nu pot încărca știrile acum (${esc(e.message)}). Reîncerc automat în câteva minute.</li>`;
  }
}

function afiseazaUltimaStire() {   // bara de pe pagina COMANDĂ: mereu cel mai nou titlu
  const d = stare.stiri.d, s = d && d.stiri[0];
  if (!s) return;
  $('#us-continut').innerHTML = `
    <time datetime="${esc(s.data)}" title="${new Date(s.data).toLocaleString('ro-RO')}">${cand(s.data)}</time>
    <span class="tag cat-${s.categorie}">${esc(d.categorii[s.categorie])}</span>
    <a href="${esc(s.link)}" target="_blank" rel="noopener noreferrer" title="${esc(s.titlu)}">${esc(s.titlu)}</a>
    <span class="sursa">${esc(s.sursa)}</span>`;
  if (stare.stiri.ultimaAfisata && stare.stiri.ultimaAfisata !== s.link) {   // titlu nou: o clipire scurtă
    const bara = $('#ultima-stire');
    bara.classList.remove('noua'); void bara.offsetWidth; bara.classList.add('noua');
  }
  stare.stiri.ultimaAfisata = s.link;
}

function afiseazaStiri() {
  const d = stare.stiri.d;
  if (!d) return;
  const lista = d.stiri.filter(s => stare.stiri.cat === 'toate' || s.categorie === stare.stiri.cat).slice(0, 80);
  $('#lista-stiri').innerHTML = lista.length ? lista.map(s => `
    <li class="stire cat-${s.categorie}">
      <time datetime="${esc(s.data)}" title="${new Date(s.data).toLocaleString('ro-RO')}">${cand(s.data)}</time>
      <a href="${esc(s.link)}" target="_blank" rel="noopener noreferrer">${esc(s.titlu)}</a>
      <div class="meta"><span class="tag">${esc(d.categorii[s.categorie])}</span><span>${esc(s.sursa)}</span></div>
    </li>`).join('') : '<li class="t2" style="padding:14px 0">Nicio știre în această categorie în ultimele 3 zile.</li>';
  $('#stiri-stare').textContent = `${lista.length} titluri · actualizat ${new Date(stare.stiri.incarcatLa).toLocaleTimeString('ro-RO', { hour: '2-digit', minute: '2-digit' })}` +
    (d.surse_cazute.length ? ` · indisponibil acum: ${d.surse_cazute.join(', ')}` : '');
}

// ----------------------------------------------------------------- BACKTEST
async function ruleazaBacktest(ev) {
  ev.preventDefault();
  const strategie = $('#bt-strategie').value, start = $('#bt-start').value, capital = parseFloat($('#bt-capital').value);
  const buton = $('#bt-ruleaza');
  buton.disabled = true;
  $('#bt-rezultate').innerHTML = '<div class="panel" style="margin-top:18px"><div class="incarcare">Rulez simularea zi cu zi</div></div>';
  try {
    const d = await post('/api/backtest/' + strategie, { start, capital });
    stare.bt = { strategie, d };
    stare.filtruBt = 'toate';
    afiseazaBacktest();
  } catch (e) {
    $('#bt-rezultate').innerHTML = `<div class="panel" style="margin-top:18px"><div class="t2">${esc(e.message)}</div></div>`;
  } finally { buton.disabled = false; }
}

function afiseazaBacktest() {
  const { strategie, d } = stare.bt;
  const s = d.statistici.strategie, b = d.statistici.buy_hold, f = d.final;
  const cul = strategie === 'sdca' ? CUL.sdca : CUL.ai, nume = strategie === 'sdca' ? 'SDCA v2' : 'AI Hedge Fund';
  const profit = s.final - d.capital;
  const extra = strategie === 'sdca'
    ? tile('PROFIT REALIZAT', usd(f.profit_realizat, 2), 'din vânzări', semnCls(f.profit_realizat)) +
      tile('PROFIT NEREALIZAT', usd(f.profit_nerealizat, 2), f.pret_mediu ? 'preț mediu ' + usd(f.pret_mediu, 0) : 'fără BTC', semnCls(f.profit_nerealizat)) +
      tile('POZIȚIE FINALĂ', usd(f.cash, 0) + ' cash', nr(f.btc, 6) + ' BTC (' + usd(f.valoare_btc, 0) + ')') +
      tile('TRANZACȚII', f.nr_cumparari + f.nr_vanzari, `${f.nr_cumparari} cumpărări · ${f.nr_vanzari} vânzări`) +
      tile('COMISIOANE', usd(f.comisioane, 2), '0.10% + 0.05% slippage')
    : tile('EXPUNERE MEDIE', pct(f.expunere_medie * 100, 0, false), 'finală ' + pct(f.expunere_finala * 100, 0, false)) +
      tile('TRANZACȚII', f.nr_tranzactii, 'rebalansări în trepte de 25%') +
      tile('COMISIOANE', usd(f.comisioane, 2), '0.10% + 0.05% slippage');

  $('#bt-rezultate').innerHTML = `
    <div class="panel" style="margin-top:18px">
      <h2>RAPORT // ${nume.toUpperCase()} · ${esc(d.start)} → ${esc(d.end)}</h2>
      <div class="tiles">
        ${tile('CAPITAL INIȚIAL', usd(d.capital, 2))}
        ${tile('CAPITAL FINAL', usd(s.final, 2), 'Buy & Hold: ' + usd(b.final, 0))}
        ${tile('PROFIT NET', usd(profit, 2), pct(s.total, 2), semnCls(profit))}
        ${tile('RANDAMENT ANUAL', pct(s.cagr, 1), 'Buy & Hold: ' + pct(b.cagr, 1), semnCls(s.cagr))}
        ${tile('DRAWDOWN MAXIM', pct(s.max_dd, 1, false), 'Buy & Hold: ' + pct(b.max_dd, 1, false), 'neg')}
        ${tile('SHARPE', nr(s.sharpe, 2), 'Buy & Hold: ' + nr(b.sharpe, 2))}
        ${extra}
      </div>
      <div class="antet-grafic" style="margin-top:16px">
        <span class="titlu-grafic">Valoarea portofoliului</span>
        <div class="legenda"><span><i style="background:${cul}"></i>${nume}</span><span><i style="background:var(--s-bh)"></i>Buy &amp; Hold</span></div>
      </div>
      <div class="grafic mare"><canvas id="g-bt"></canvas></div>
    </div>
    <div class="doua-col" style="margin-top:18px">
      <div class="panel">
        <h2>PE ANI</h2>
        <div class="tabel-wrap"><table>
          <thead><tr><th>AN</th><th class="n">${nume.toUpperCase()}</th><th class="n">BUY &amp; HOLD</th><th class="n">DRAWDOWN</th></tr></thead>
          <tbody>${d.pe_ani.map(a => `<tr><td class="num">${a.an}</td><td class="n ${semnCls(a.strategie)}">${pct(a.strategie)}</td>
            <td class="n ${semnCls(a.buy_hold)}">${pct(a.buy_hold)}</td><td class="n neg">${pct(a.max_dd, 1, false)}</td></tr>`).join('')}</tbody>
        </table></div>
      </div>
      <div class="panel">
        <h2>JURNAL // DE CE A TRANZACȚIONAT</h2>
        <div class="segment" id="seg-jurnal" style="margin-bottom:12px">
          <button data-f="toate" class="activ">TOATE</button><button data-f="BUY">CUMPĂRĂRI</button><button data-f="SELL">VÂNZĂRI</button>
          ${strategie === 'sdca' ? '<button data-f="EV">EVENIMENTE</button>' : ''}
        </div>
        <div class="jurnal" id="bt-jurnal"></div>
      </div>
    </div>`;

  deseneaza('g-bt', () => configGrafic(v => '$' + nr(v / 1000, 0) + 'k', {
    paddingDreapta: 185, etichete: { activ: true, format: v => usd(v, 0) },
    tooltip: { label: c => ` ${c.dataset.label}: ${usd(c.parsed.y, 0)}` } }),
    { labels: d.serii.data, datasets: [serie(nume, d.serii.strategie, cul), serie('Buy & Hold', d.serii.buy_hold, CUL.bh)] });
  $$('#seg-jurnal button').forEach(btn => btn.addEventListener('click', () => {
    stare.filtruBt = btn.dataset.f;
    $$('#seg-jurnal button').forEach(x => x.classList.toggle('activ', x === btn));
    afiseazaJurnalBt();
  }));
  afiseazaJurnalBt();
}

function afiseazaJurnalBt() {
  const { strategie, d } = stare.bt, f = stare.filtruBt;
  let intrari = d.tranzactii.map(t => ({ ...t, _tip: strategie === 'sdca' ? t.Tip : t.Actiune }));
  if (strategie === 'sdca') intrari = intrari.concat((d.evenimente || []).map(e => ({ ...e, _tip: 'EV' })));
  intrari.sort((a, b) => a.Data < b.Data ? -1 : a.Data > b.Data ? 1 : (a._tip === 'EV' ? -1 : 1));
  if (f !== 'toate') intrari = intrari.filter(t => t._tip === f);
  const total = intrari.length;
  const html = intrari.slice(0, 800).map((t, i) => {
    if (t._tip === 'EV') return `<div class="intrare EV"><div class="linie1"><span class="data">${esc(t.Data)}</span>
      <span class="eticheta-tip EV">EVENIMENT</span><span class="motiv">${esc(t.Eveniment)}</span></div><div class="dece">↳ ${esc(t.De_ce)}</div></div>`;
    const sdca = strategie === 'sdca';
    const motiv = sdca ? t.Motiv : `REBALANSARE ${pct(t.Expunere_veche * 100, 0, false)} → ${pct(t.Expunere_noua * 100, 0, false)}`;
    const dupa = sdca
      ? `după: cash ${usd(t.Cash_dupa, 2)} · BTC ${nr(t.BTC_dupa, 6)} · portofoliu ${usd(t.Valoare_portofoliu, 2)} · P/L total ${pct(t['PL_total_%'], 2)}`
      : `după: portofoliu ${usd(t.Valoare_portofoliu, 2)}`;
    const profit = sdca && t._tip === 'SELL' && t.Profit_realizat != null
      ? `<div class="dupa ${semnCls(t.Profit_realizat)}">profit realizat ${usd(t.Profit_realizat, 2)} (preț mediu ${usd(t.Pret_mediu, 0)})</div>` : '';
    return `<div class="intrare ${t._tip}"><div class="linie1"><span class="data">${esc(t.Data)}</span>
      <span class="eticheta-tip ${t._tip}">${t._tip}</span><span class="motiv">${esc(motiv)}</span>
      <span class="suma">${usd(t.Suma_USD, 2)} @ ${usd(t.Pret, 0)}</span></div>
      <div class="dece">↳ ${esc(t.De_ce)}</div>${profit}<div class="dupa">${dupa}</div></div>`;
  }).join('');
  $('#bt-jurnal').innerHTML = (html || '<div class="t2">Nicio intrare pentru acest filtru.</div>') +
    (total > 800 ? `<p class="nota">Se afișează primele 800 din ${total}.</p>` : '');
}

// ----------------------------------------------------------------- consola asistent
function adaugaMesaj(text, tip) {
  const el = document.createElement('div');
  el.className = 'msg ' + tip; el.textContent = text;
  $('#mesaje').appendChild(el); $('#mesaje').scrollTop = $('#mesaje').scrollHeight;
}
async function trimiteIntrebare(ev) {
  ev.preventDefault();
  const q = $('#intrebare').value.trim();
  if (!q) return;
  adaugaMesaj(q, 'tu'); $('#intrebare').value = '';
  $('#reactor').classList.add('vorbeste');
  try {
    const r = await post('/api/chat', { mesaj: q });
    adaugaMesaj(r.raspuns || '', 'jarvis');
  } catch (e) { adaugaMesaj(e.message, 'sistem'); }
  finally { setTimeout(() => $('#reactor').classList.remove('vorbeste'), 900); }
}

// ----------------------------------------------------------------- actualizare date
async function actualizeazaDate() {
  const b = $('#btn-actualizeaza');
  b.disabled = true; b.textContent = '⟳ SE ACTUALIZEAZĂ…';
  try {
    await post('/api/actualizeaza');
    let s;
    do { await new Promise(r => setTimeout(r, 3000)); s = await api('/api/actualizeaza'); } while (s.ruleaza);
    const r = s.rezultat || {};
    toast(r.pipeline && r.date_ai ? 'Date actualizate: pipeline Master_Index + istoric AI.' :
      `Actualizare parțială — pipeline: ${r.pipeline ? 'OK' : 'eșuat'}, date AI: ${r.date_ai ? 'OK' : 'eșuat'}.`, !(r.pipeline && r.date_ai));
    reincarcaTot();
    stare.versiuneDate = null;   // versiunea nouă se preia la următoarea verificare, fără notificare dublă
    verificaStatus();
  } catch (e) { toast('Actualizarea a eșuat: ' + e.message, true); }
  finally { b.disabled = false; b.textContent = '⟳ ACTUALIZEAZĂ DATE'; }
}

function reincarcaTot() {
  incarcaPiata(); incarcaCarduriBoti(); incarcaIstoric(); incarcaComparatie();
  if (stare.pagina === 'boti') incarcaBoti();
}

// ----------------------------------------------------------------- actualizare automată
// Serverul își reîmprospătează singur datele (pipeline la 60 min, istoric AI zilnic). Pagina verifică
// versiunea datelor la 30 s și redesenează DOAR când s-a schimbat ceva - fără reîncărcarea paginii.
async function verificaStatus() {
  try {
    const s = await api('/api/status');
    const led = $('#led-auto'), ruleaza = s.actualizare && s.actualizare.ruleaza;
    led.className = 'led ' + (!s.auto.activ ? '' : ruleaza ? 'warn puls' : 'ok');
    $('#auto-ora').textContent = ruleaza ? '…' : (s.master_actualizat || '').slice(11, 16);
    $('#auto-status').title = !s.auto.activ ? 'Actualizare automată dezactivată (JARVIS_AUTO_UPDATE=0)'
      : `Actualizare automată: Master_Index la fiecare ${s.auto.interval_pipeline_min} min, istoric AI la fiecare zi nouă.\n` +
        `Date Master_Index din: ${s.master_actualizat || '—'}\nUltima verificare: ${s.auto.ultima_verificare || '—'}\n` +
        `Următoarea verificare: ${s.auto.urmatoarea_verificare || '—'}` + (ruleaza ? '\nSe actualizează acum…' : '');
    if (stare.versiuneDate && stare.versiuneDate !== s.versiune_date) {
      reincarcaTot();
      if (stare.pagina === 'heatmap') incarcaHeatmap();
      toast('Date noi primite automat — panourile au fost actualizate.');
    }
    stare.versiuneDate = s.versiune_date;
  } catch (_) {
    $('#led-auto').className = 'led bad';
  }
}

// ----------------------------------------------------------------- pornire
document.addEventListener('DOMContentLoaded', () => {
  boot();
  ceas(); setInterval(ceas, 1000);
  if (typeof Chart !== 'undefined') {
    Chart.defaults.font.family = '"Chakra Petch", sans-serif';
    Chart.defaults.color = CUL.text2;
  } else {
    toast('Librăria de grafice nu s-a încărcat (verifică internetul). Restul platformei funcționează.', true);
  }
  construiestePanouriBoti();

  $$('nav.tabs button').forEach(b => b.addEventListener('click', () => arataPagina(b.dataset.pagina)));
  $$('[data-mergi]').forEach(b => b.addEventListener('click', () => arataPagina(b.dataset.mergi)));
  $$('#seg-istoric button').forEach(b => b.addEventListener('click', () => {
    stare.zileIstoric = +b.dataset.zile;
    $$('#seg-istoric button').forEach(x => x.classList.toggle('activ', x === b));
    incarcaIstoric();
  }));
  $$('#seg-hm-interval button').forEach(b => b.addEventListener('click', () => {
    stare.hm.iv = b.dataset.iv;
    stare.hm.d = null;   // alt interval -> date noi; arătăm indicatorul de încărcare
    $$('#seg-hm-interval button').forEach(x => x.classList.toggle('activ', x === b));
    incarcaHeatmap();
  }));
  $$('#seg-hm-tip button').forEach(b => b.addEventListener('click', () => {
    stare.hm.tip = b.dataset.tip;
    $$('#seg-hm-tip button').forEach(x => x.classList.toggle('activ', x === b));
    deseneazaHeatmap();
  }));
  $('#hm-canvas').addEventListener('mousemove', hoverHeatmap);
  $('#hm-canvas').addEventListener('mouseleave', () => $('#hm-tooltip').classList.add('hidden'));
  let tRedim, eraIngust = window.innerWidth < 760;
  window.addEventListener('resize', () => { clearTimeout(tRedim); tRedim = setTimeout(() => {
    if (stare.pagina === 'heatmap') deseneazaHeatmap();
    const ingust = window.innerWidth < 760;      // graficele își aleg etichetele după lățime: le refacem la trecerea pragului
    if (ingust !== eraIngust) { eraIngust = ingust; incarcaIstoric(); incarcaComparatie(); if (stare.bt) afiseazaBacktest(); }
  }, 150); });
  $('#form-backtest').addEventListener('submit', ruleazaBacktest);
  $('#bt-strategie').addEventListener('change', e => { $('#bt-start').value = e.target.value === 'sdca' ? '2023-02-15' : '2018-08-17'; });
  $('#form-chat').addEventListener('submit', trimiteIntrebare);
  $('#btn-actualizeaza').addEventListener('click', actualizeazaDate);

  reincarcaTot();
  const ultima = mem.get('jarvis-pagina');
  if (ultima && ultima !== 'comanda' && $('#p-' + ultima)) arataPagina(ultima);

  setInterval(incarcaPiata, 15000);
  setInterval(() => { if (stare.pagina === 'comanda') incarcaCarduriBoti(); }, 30000);
  setInterval(async () => {
    if (stare.pagina !== 'boti') return;
    incarcaLoguri();
    try { actualizeazaStatusBoti(await api('/api/boti')); } catch (_) { /* reîncercăm */ }
  }, 4000);
  setInterval(() => { if (stare.pagina === 'boti') incarcaBoti(); }, 20000);
  setInterval(() => { if (stare.pagina === 'heatmap') incarcaHeatmap(); }, 60000);
  incarcaStiri();                                   // bara „ultima știre” de pe COMANDĂ are nevoie de date de la pornire
  setInterval(incarcaStiri, 300000);                // serverul le ține în cache 5 minute
  setInterval(afiseazaUltimaStire, 60000);          // actualizează „acum X min”
  $$('#seg-stiri button').forEach(b => b.addEventListener('click', () => {
    stare.stiri.cat = b.dataset.cat;
    $$('#seg-stiri button').forEach(x => x.classList.toggle('activ', x === b));
    afiseazaStiri();
  }));
  verificaStatus();
  setInterval(verificaStatus, 30000);
  pornesteWS();
  setInterval(pazaWS, 5000);
  setInterval(eticheteLiveHeatmap, 1000);
});
