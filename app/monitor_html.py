"""
monitor_html.py — HTML du dashboard de monitoring VideoGen
Servi par GET /monitor dans main.py
Onglets : Jobs (pipeline) | Voix (catalogue ElevenLabs)
"""

MONITOR_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VideoGen Monitor</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    @keyframes pulse-glow { 0%,100%{opacity:1} 50%{opacity:.4} }
    .pulse { animation: pulse-glow 1.5s ease-in-out infinite; }
    @keyframes stripe {
      0%{background-position:0 0} 100%{background-position:40px 0}
    }
    .bar-animated {
      background-image: linear-gradient(
        45deg,
        rgba(255,255,255,.15) 25%, transparent 25%,
        transparent 50%, rgba(255,255,255,.15) 50%,
        rgba(255,255,255,.15) 75%, transparent 75%
      );
      background-size:40px 40px;
      animation: stripe 1s linear infinite;
    }
    body { background-color:#030712; }
    ::-webkit-scrollbar { width:6px; height:6px; }
    ::-webkit-scrollbar-track { background:#111827; }
    ::-webkit-scrollbar-thumb { background:#374151; border-radius:3px; }
    audio { width:100%; height:32px; }
  </style>
</head>
<body class="text-gray-100 min-h-screen font-sans">

<!-- HEADER -->
<header class="bg-gray-900 border-b border-gray-800 sticky top-0 z-20 shadow-xl">
  <div class="max-w-5xl mx-auto px-4 py-3 flex items-center justify-between">
    <div class="flex items-center gap-3">
      <span class="text-3xl">🎬</span>
      <div>
        <h1 class="text-base font-bold text-white tracking-tight">VideoGen Monitor</h1>
        <p class="text-[11px] text-gray-500">Pipeline de génération publicitaire automatisée</p>
      </div>
    </div>
    <div class="flex items-center gap-3">
      <div id="api-status" class="flex items-center gap-1.5 text-xs text-gray-500">
        <span id="status-dot" class="w-2 h-2 rounded-full bg-gray-600 inline-block"></span>
        <span id="status-text">Connexion…</span>
      </div>
      <span id="last-refresh" class="text-[11px] text-gray-600 hidden">—</span>
      <button onclick="loadJobs()"
        class="text-xs bg-gray-700 hover:bg-gray-600 active:bg-gray-500 text-gray-200
               px-3 py-1.5 rounded-md transition-colors border border-gray-600">
        ↺ Actualiser
      </button>
    </div>
  </div>

  <!-- TABS NAV -->
  <div class="max-w-5xl mx-auto px-4 pb-2 pt-1 flex gap-1">
    <button id="tab-btn-jobs" onclick="switchTab('jobs')"
      class="px-5 py-1.5 rounded-lg text-sm font-semibold transition-all bg-gray-700 text-white border border-gray-600">
      🎬 Jobs
    </button>
    <button id="tab-btn-voix" onclick="switchTab('voix')"
      class="px-5 py-1.5 rounded-lg text-sm font-semibold transition-all text-gray-500 hover:text-gray-200 border border-transparent">
      🎙️ Voix
    </button>
  </div>
</header>

<!-- ══════════════════ TAB : JOBS ══════════════════ -->
<div id="tab-jobs">

  <!-- AUTH BANNER -->
  <div id="auth-banner" class="hidden max-w-5xl mx-auto px-4 mt-6">
    <div class="bg-amber-950/50 border border-amber-800 rounded-xl p-5">
      <p class="text-amber-300 font-semibold mb-1">🔑 Authentification requise</p>
      <p class="text-amber-400/70 text-sm mb-3">
        Entrez votre clé API (valeur de <code class="bg-amber-900/50 px-1 rounded">API_SECRET_KEY</code>)
        ou accédez via <code class="bg-amber-900/50 px-1 rounded">/monitor?key=VOTRE_CLE</code>
      </p>
      <div class="flex gap-2">
        <input id="api-key-input" type="password" placeholder="Clé API secrète…"
          class="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-sm
                 text-white placeholder-gray-600 focus:outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/30">
        <button onclick="saveKey()"
          class="bg-amber-600 hover:bg-amber-500 text-white px-5 py-2 rounded-lg text-sm font-semibold transition-colors">
          Connexion
        </button>
      </div>
    </div>
  </div>

  <!-- MAIN JOBS -->
  <main class="max-w-5xl mx-auto px-4 py-6">

    <!-- Stats -->
    <div id="stats-bar" class="hidden grid grid-cols-4 gap-3 mb-6">
      <div class="bg-gray-800/80 border border-gray-700 rounded-xl p-4 text-center">
        <div id="stat-total" class="text-3xl font-bold text-white">—</div>
        <div class="text-xs text-gray-500 mt-1">Total</div>
      </div>
      <div class="bg-green-950/50 border border-green-800/60 rounded-xl p-4 text-center">
        <div id="stat-done" class="text-3xl font-bold text-green-400">—</div>
        <div class="text-xs text-gray-500 mt-1">Terminés</div>
      </div>
      <div class="bg-blue-950/50 border border-blue-800/60 rounded-xl p-4 text-center">
        <div id="stat-running" class="text-3xl font-bold text-blue-400">—</div>
        <div class="text-xs text-gray-500 mt-1">En cours</div>
      </div>
      <div class="bg-red-950/50 border border-red-800/60 rounded-xl p-4 text-center">
        <div id="stat-failed" class="text-3xl font-bold text-red-400">—</div>
        <div class="text-xs text-gray-500 mt-1">Échoués</div>
      </div>
    </div>

    <!-- Loading -->
    <div id="loading-state" class="text-center py-20 text-gray-600">
      <div class="text-5xl mb-4 pulse">⏳</div>
      <p class="text-lg">Chargement des jobs…</p>
    </div>

    <!-- No jobs -->
    <div id="no-jobs" class="hidden text-center py-20 text-gray-600">
      <div class="text-5xl mb-4">📭</div>
      <p class="text-lg font-medium text-gray-500">Aucun job pour l'instant</p>
      <p class="text-sm mt-2">Lance une génération depuis Google Sheets (Statut = ok)</p>
    </div>

    <!-- Jobs list -->
    <div id="jobs-container"></div>

  </main>

</div><!-- /tab-jobs -->

<!-- ══════════════════ TAB : VOIX ══════════════════ -->
<div id="tab-voix" class="hidden max-w-5xl mx-auto px-4 py-6">

  <!-- Instructions -->
  <div class="bg-gray-800/40 border border-gray-700 rounded-2xl p-5 mb-6 text-sm text-gray-400 leading-relaxed">
    <p class="font-semibold text-gray-200 mb-2">📋 Comment utiliser ce catalogue</p>
    <ol class="list-decimal list-inside space-y-1">
      <li>Écoute chaque voix avec le lecteur audio ▶</li>
      <li>Clique <strong class="text-gray-200">Copier ID</strong> sur la voix choisie</li>
      <li>Colle l'ID dans la colonne <strong class="text-gray-200">Voix (col F)</strong> du Google Sheet</li>
    </ol>
  </div>

  <!-- Loading state -->
  <div id="voices-loading" class="text-center py-20 text-gray-600">
    <div class="text-5xl mb-4 pulse">⏳</div>
    <p class="text-lg">Chargement des voix…</p>
  </div>

  <!-- Auth required for voices -->
  <div id="voices-auth" class="hidden text-center py-20 text-gray-600">
    <div class="text-5xl mb-4">🔑</div>
    <p class="text-lg">Connecte-toi d'abord depuis l'onglet <strong>Jobs</strong></p>
  </div>

  <!-- Voices grid -->
  <div id="voices-grid" class="hidden grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"></div>

  <!-- Add voice info -->
  <div id="voices-add" class="hidden mt-6 bg-gray-800/40 border border-gray-700/60 border-dashed rounded-2xl p-5 text-sm text-gray-500 text-center">
    Pour ajouter une voix : mettre son ID dans
    <code class="bg-gray-800 px-1.5 py-0.5 rounded text-gray-400">app/voices_catalog.json</code>
    puis redéployer.
  </div>

</div><!-- /tab-voix -->

<script>
// ── Config ──────────────────────────────────────────────────────────────────
const API_URL = window.location.origin;
let apiKey = localStorage.getItem('videogen_api_key') || '';
let refreshTimer = null;

// Lire la clé depuis ?key=
const urlKey = new URLSearchParams(window.location.search).get('key');
if (urlKey) { apiKey = urlKey; localStorage.setItem('videogen_api_key', apiKey); }

// ── Tabs ─────────────────────────────────────────────────────────────────────
const TAB_ACTIVE   = 'px-5 py-1.5 rounded-lg text-sm font-semibold transition-all bg-gray-700 text-white border border-gray-600';
const TAB_INACTIVE = 'px-5 py-1.5 rounded-lg text-sm font-semibold transition-all text-gray-500 hover:text-gray-200 border border-transparent';

function switchTab(tab) {
  document.getElementById('tab-jobs').classList.toggle('hidden', tab !== 'jobs');
  document.getElementById('tab-voix').classList.toggle('hidden', tab !== 'voix');
  document.getElementById('tab-btn-jobs').className = tab === 'jobs' ? TAB_ACTIVE : TAB_INACTIVE;
  document.getElementById('tab-btn-voix').className = tab === 'voix' ? TAB_ACTIVE : TAB_INACTIVE;
  if (tab === 'voix') loadVoices();
}

// ── Étapes du pipeline ──────────────────────────────────────────────────────
const STEPS = [
  {
    id: 'claude', label: 'Claude', icon: '🤖',
    api: 'Anthropic',
    runStatus: ['running_claude'],
    minPct: 10, maxPct: 25,
  },
  {
    id: 'elevenlabs', label: 'ElevenLabs', icon: '🎙️',
    api: 'ElevenLabs',
    runStatus: ['running_elevenlabs'],
    minPct: 25, maxPct: 40,
  },
  {
    id: 'clips', label: 'Clips B-roll', icon: '🎬',
    api: 'Pexels / Kling',
    runStatus: ['running_clips'],
    minPct: 40, maxPct: 75,
  },
  {
    id: 'creatomate', label: 'Creatomate', icon: '⚙️',
    api: 'Creatomate',
    runStatus: ['running_creatomate', 'uploading'],
    minPct: 75, maxPct: 99,
  },
  {
    id: 'done', label: 'Livré', icon: '✅',
    api: 'Google Drive',
    runStatus: ['completed'],
    minPct: 100, maxPct: 100,
  },
];

function getStepState(step, job) {
  const s = job.status;
  const pct = job.progress?.percentage ?? 0;

  if (s === 'completed') return 'done';

  if (s === 'failed') {
    if (pct >= step.maxPct) return 'done';
    if (pct >= step.minPct) return 'failed';
    return 'pending';
  }

  if (step.runStatus.includes(s)) return 'running';

  const curIdx = STEPS.findIndex(st => st.runStatus.includes(s));
  const myIdx  = STEPS.findIndex(st => st.id === step.id);
  return curIdx > myIdx ? 'done' : 'pending';
}

// ── Rendu d'une étape ────────────────────────────────────────────────────────
function renderStep(step, state, job) {
  const cfg = {
    done:    { wrap: 'border-green-700/60 bg-green-900/30',  label: 'text-green-300', badge: 'bg-green-700 text-green-100', sym: '✓' },
    running: { wrap: 'border-blue-500 bg-blue-900/40 shadow-blue-900/50 shadow-md', label: 'text-blue-200', badge: 'bg-blue-500 text-white pulse', sym: '…' },
    failed:  { wrap: 'border-red-700/60 bg-red-900/30',      label: 'text-red-300',   badge: 'bg-red-700 text-red-100',   sym: '✗' },
    pending: { wrap: 'border-gray-700/40 bg-gray-800/30',    label: 'text-gray-600',  badge: 'bg-gray-700 text-gray-500', sym: '·' },
  }[state];

  let extra = '';
  if (step.id === 'clips' && state === 'running' && job.progress?.clips_done != null) {
    extra = `<div class="text-[10px] text-blue-300/70 mt-0.5">${job.progress.clips_done}/${job.progress.clips_total} clips</div>`;
  }

  return `
    <div class="flex flex-col items-center gap-1">
      <div class="border ${cfg.wrap} rounded-xl px-3 py-2.5 text-center min-w-[80px] transition-all duration-300">
        <div class="text-xl">${step.icon}</div>
        <div class="text-[11px] font-semibold ${cfg.label} mt-0.5 whitespace-nowrap">${step.label}</div>
        <div class="text-[9px] text-gray-600 mt-0.5">${step.api}</div>
        ${extra}
        <span class="mt-1 inline-block text-[10px] px-1.5 py-0.5 rounded ${cfg.badge}">${cfg.sym}</span>
      </div>
    </div>`;
}

// ── Badge statut ─────────────────────────────────────────────────────────────
function statusBadge(s) {
  const map = {
    pending:            { t: 'En attente',    c: 'bg-gray-700/80 text-gray-400 border-gray-600' },
    running_claude:     { t: '🤖 Claude…',     c: 'bg-violet-800 text-violet-100 border-violet-700 pulse' },
    running_elevenlabs: { t: '🎙️ Voix off…',   c: 'bg-purple-800 text-purple-100 border-purple-700 pulse' },
    running_clips:      { t: '🎬 Clips…',      c: 'bg-indigo-800 text-indigo-100 border-indigo-700 pulse' },
    running_creatomate: { t: '⚙️ Rendu…',      c: 'bg-cyan-800 text-cyan-100 border-cyan-700 pulse' },
    uploading:          { t: '☁️ Envoi…',       c: 'bg-teal-800 text-teal-100 border-teal-700 pulse' },
    completed:          { t: '✅ Terminé',      c: 'bg-green-800 text-green-100 border-green-700' },
    failed:             { t: '❌ Échoué',       c: 'bg-red-800 text-red-100 border-red-700' },
  };
  const { t, c } = map[s] || { t: s, c: 'bg-gray-700 text-gray-300 border-gray-600' };
  return `<span class="text-xs px-2.5 py-1 rounded-full font-bold border ${c}">${t}</span>`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('fr-FR', {
    day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit'
  });
}

function fmtDuration(a, b) {
  if (!a || !b) return '';
  const s = Math.floor((new Date(b) - new Date(a)) / 1000);
  if (s < 60) return s + 's';
  return Math.floor(s/60) + 'm ' + (s%60) + 's';
}

// ── Rendu d'un job ────────────────────────────────────────────────────────────
function renderJob(job) {
  const stepStates = STEPS.map(s => ({ step: s, state: getStepState(s, job) }));
  const pct = job.progress?.percentage ?? 0;
  const isRunning = !['completed','failed','pending'].includes(job.status);

  const barCls = job.status === 'completed' ? 'bg-green-500'
               : job.status === 'failed'    ? 'bg-red-600'
               : `bg-blue-500${isRunning ? ' bar-animated' : ''}`;

  const pctCls = job.status === 'completed' ? 'text-green-400'
               : job.status === 'failed'    ? 'text-red-400'
               : 'text-blue-400';

  const stepsHtml = stepStates.map(({ step, state }, i) => {
    const arrow = i < stepStates.length - 1
      ? `<div class="flex items-center pt-3 text-gray-600 text-lg font-light">→</div>`
      : '';
    return renderStep(step, state, job) + arrow;
  }).join('');

  const videoHtml = job.drive_url
    ? `<a href="${job.drive_url}" target="_blank"
          class="inline-flex items-center gap-2 bg-green-900/40 hover:bg-green-800/60
                 border border-green-700 text-green-300 hover:text-green-100
                 text-sm px-4 py-2.5 rounded-xl transition-all font-semibold group">
         🎥 <span>Voir la vidéo générée</span>
         <span class="group-hover:translate-x-1 transition-transform">→</span>
       </a>` : '';

  const errHtml = job.error
    ? `<div class="mt-3 bg-red-950/60 border border-red-800/60 rounded-xl p-3.5
                  text-sm text-red-300 font-mono break-all leading-relaxed">
         ⚠️ ${job.error}
       </div>` : '';

  const detailHtml = (job.progress?.detail && !job.error && job.progress.detail !== job.progress.step)
    ? `<div class="text-[11px] text-gray-500 mt-0.5 italic">${job.progress.detail}</div>` : '';

  const dur = fmtDuration(job.created_at, job.updated_at);

  return `
    <div class="bg-gray-900/80 border border-gray-700/60 hover:border-gray-600
                rounded-2xl p-5 mb-4 transition-colors shadow-xl shadow-black/20">

      <!-- En-tête -->
      <div class="flex items-start justify-between gap-4 mb-4">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            ${statusBadge(job.status)}
            <code class="text-[11px] text-gray-500 bg-gray-800 px-2 py-0.5 rounded-md font-mono border border-gray-700">
              ${job.job_id.substring(0,8)}…
            </code>
            ${dur ? `<span class="text-[11px] text-gray-600">⏱ ${dur}</span>` : ''}
          </div>
          <div class="text-xs text-gray-600 mt-1.5 leading-relaxed">
            Campagne <code class="text-gray-500 bg-gray-800/60 px-1 rounded">${job.row_id}</code>
            · Créé le <span class="text-gray-500">${fmtDate(job.created_at)}</span>
          </div>
        </div>
        <div class="text-right shrink-0">
          <div class="text-3xl font-black ${pctCls}">${pct}%</div>
        </div>
      </div>

      <!-- Pipeline -->
      <div class="flex items-start gap-2 overflow-x-auto pb-2 mb-4 scrollbar-thin">
        ${stepsHtml}
      </div>

      <!-- Barre de progression -->
      <div class="bg-gray-800 rounded-full h-1.5 overflow-hidden mb-2">
        <div class="h-1.5 rounded-full transition-all duration-700 ${barCls}"
             style="width:${pct}%"></div>
      </div>

      <!-- Étape actuelle -->
      <div class="text-xs text-gray-500 font-medium">${job.progress?.step ?? '—'}</div>
      ${detailHtml}

      <!-- Erreur -->
      ${errHtml}

      <!-- Lien vidéo -->
      ${videoHtml ? `<div class="mt-4">${videoHtml}</div>` : ''}
    </div>`;
}

// ── Chargement des jobs ───────────────────────────────────────────────────────
async function loadJobs() {
  if (!apiKey) {
    document.getElementById('auth-banner').classList.remove('hidden');
    document.getElementById('loading-state').classList.add('hidden');
    return;
  }

  try {
    const r = await fetch(`${API_URL}/jobs`, {
      headers: { 'Authorization': `Bearer ${apiKey}` }
    });

    if (r.status === 401) {
      apiKey = '';
      localStorage.removeItem('videogen_api_key');
      document.getElementById('auth-banner').classList.remove('hidden');
      setStatus('red', 'Clé invalide');
      return;
    }

    const jobs = await r.json();

    setStatus('green', 'API en ligne');
    document.getElementById('last-refresh').classList.remove('hidden');
    document.getElementById('last-refresh').textContent =
      'Mis à jour à ' + new Date().toLocaleTimeString('fr-FR');
    document.getElementById('loading-state').classList.add('hidden');
    document.getElementById('auth-banner').classList.add('hidden');

    // Stats
    document.getElementById('stats-bar').classList.remove('hidden');
    document.getElementById('stat-total').textContent   = jobs.length;
    document.getElementById('stat-done').textContent    = jobs.filter(j=>j.status==='completed').length;
    document.getElementById('stat-running').textContent = jobs.filter(j=>!['completed','failed','pending'].includes(j.status)).length;
    document.getElementById('stat-failed').textContent  = jobs.filter(j=>j.status==='failed').length;

    if (jobs.length === 0) {
      document.getElementById('no-jobs').classList.remove('hidden');
      document.getElementById('jobs-container').innerHTML = '';
    } else {
      document.getElementById('no-jobs').classList.add('hidden');
      document.getElementById('jobs-container').innerHTML = jobs.map(renderJob).join('');
    }

  } catch (e) {
    setStatus('red', 'Hors ligne');
    console.error(e);
  }
}

function setStatus(color, text) {
  const colors = { green: 'bg-green-500', red: 'bg-red-500', gray: 'bg-gray-500' };
  const texts  = { green: 'text-green-400', red: 'text-red-400', gray: 'text-gray-400' };
  document.getElementById('status-dot').className = `w-2 h-2 rounded-full ${colors[color]} inline-block`;
  document.getElementById('status-text').className = `text-xs ${texts[color]}`;
  document.getElementById('status-text').textContent = text;
}

function saveKey() {
  apiKey = document.getElementById('api-key-input').value.trim();
  localStorage.setItem('videogen_api_key', apiKey);
  loadJobs();
}

// ── VOIX — Chargement ────────────────────────────────────────────────────────
let voicesLoaded = false;

async function loadVoices() {
  if (voicesLoaded) return;

  if (!apiKey) {
    document.getElementById('voices-loading').classList.add('hidden');
    document.getElementById('voices-auth').classList.remove('hidden');
    return;
  }

  try {
    const r = await fetch(`${API_URL}/voices`, {
      headers: { 'Authorization': `Bearer ${apiKey}` }
    });
    if (r.status === 401) {
      document.getElementById('voices-loading').classList.add('hidden');
      document.getElementById('voices-auth').classList.remove('hidden');
      return;
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);

    const voices = await r.json();
    voicesLoaded = true;
    document.getElementById('voices-loading').classList.add('hidden');
    const grid = document.getElementById('voices-grid');
    grid.classList.remove('hidden');
    grid.innerHTML = voices.map(renderVoice).join('');
    document.getElementById('voices-add').classList.remove('hidden');
  } catch(e) {
    document.getElementById('voices-loading').innerHTML =
      `<div class="text-center py-20">
         <div class="text-5xl mb-4">⚠️</div>
         <p class="text-red-400 text-lg">Erreur de chargement</p>
         <p class="text-gray-600 text-sm mt-2">${e.message}</p>
         <button onclick="voicesLoaded=false; loadVoices()"
           class="mt-4 text-sm bg-gray-700 hover:bg-gray-600 text-gray-300 px-4 py-2 rounded-lg border border-gray-600">
           Réessayer
         </button>
       </div>`;
  }
}

// ── VOIX — Rendu d'une carte ──────────────────────────────────────────────────
function renderVoice(v) {
  const genderBadge = v.gender === 'female'
    ? '<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-pink-900/60 text-pink-300 border border-pink-700/60">🚺 Femme</span>'
    : v.gender === 'male'
    ? '<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-900/60 text-blue-300 border border-blue-700/60">🚹 Homme</span>'
    : '<span class="px-2 py-0.5 rounded-full text-[11px] font-bold bg-gray-700 text-gray-400 border border-gray-600">❓ Inconnu</span>';

  const unavailableBanner = !v.available
    ? `<div class="mb-3 bg-red-950/60 border border-red-800/50 rounded-xl px-3 py-2 text-xs text-red-400">
         ⚠️ Voix inaccessible avec la clé API actuelle
       </div>` : '';

  const audioPlayer = v.preview_url
    ? `<div class="mt-3">
         <p class="text-[10px] text-gray-600 mb-1 uppercase tracking-wide font-semibold">Aperçu</p>
         <audio controls preload="none"
           class="w-full rounded-lg overflow-hidden"
           style="height:36px; filter:brightness(0.8) contrast(1.2);">
           <source src="${v.preview_url}" type="audio/mpeg">
         </audio>
       </div>`
    : `<div class="mt-3 text-[11px] text-gray-600 italic">Pas d'aperçu disponible</div>`;

  const metaParts = [];
  if (v.accent)      metaParts.push(`🌍 ${v.accent}`);
  if (v.age)         metaParts.push(`🗓️ ${v.age}`);
  if (v.use_case)    metaParts.push(`💼 ${v.use_case}`);
  if (v.description) metaParts.push(`💬 ${v.description}`);
  const metaHtml = metaParts.length
    ? `<div class="space-y-0.5 mt-2 mb-1">
         ${metaParts.map(p => `<div class="text-[11px] text-gray-500">${p}</div>`).join('')}
       </div>`
    : '';

  return `
    <div class="bg-gray-900/80 border ${v.available ? 'border-gray-700/60 hover:border-gray-500' : 'border-red-900/60'} rounded-2xl p-4 transition-colors flex flex-col">
      <!-- Nom + genre -->
      <div class="flex items-start justify-between gap-2 mb-1">
        <div class="font-bold text-white text-base leading-tight">${v.name || '—'}</div>
        ${genderBadge}
      </div>

      ${unavailableBanner}
      ${metaHtml}
      ${audioPlayer}

      <!-- ID + Copier -->
      <div class="mt-3 pt-3 border-t border-gray-800 flex items-center gap-2">
        <code class="text-[10px] text-gray-600 font-mono flex-1 truncate bg-gray-800/80 px-2 py-1 rounded-md border border-gray-700/60"
              title="${v.voice_id}">${v.voice_id}</code>
        <button onclick="copyId('${v.voice_id}', this)"
          class="shrink-0 text-[11px] bg-gray-700 hover:bg-indigo-600 text-gray-300 hover:text-white
                 px-2.5 py-1 rounded-md border border-gray-600 hover:border-indigo-500
                 transition-all whitespace-nowrap font-semibold">
          Copier ID
        </button>
      </div>
    </div>`;
}

// ── VOIX — Copier dans le presse-papier ──────────────────────────────────────
function copyId(id, btn) {
  navigator.clipboard.writeText(id).then(() => {
    const orig = btn.textContent;
    btn.textContent = '✓ Copié !';
    btn.classList.add('bg-green-700', 'border-green-600', 'text-green-100');
    btn.classList.remove('bg-gray-700', 'border-gray-600', 'text-gray-300');
    setTimeout(() => {
      btn.textContent = orig;
      btn.classList.remove('bg-green-700', 'border-green-600', 'text-green-100');
      btn.classList.add('bg-gray-700', 'border-gray-600', 'text-gray-300');
    }, 2000);
  }).catch(() => {
    // Fallback si clipboard API non disponible
    prompt('Copie manuellement cet ID :', id);
  });
}

// Actualisation auto jobs toutes les 5s
setInterval(loadJobs, 5000);
loadJobs();
</script>
</body>
</html>"""
