"""
monitor_html.py — HTML du dashboard de monitoring VideoGen
Servi par GET /monitor dans main.py
Onglets : Jobs (pipeline) | Voix (catalogue ElevenLabs)
Design : inspiré de veed.io — fond clair, typographie bold, accent violet
"""

MONITOR_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VideoGen Monitor</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    :root {
      --accent: #5B5BD6;
      --accent-hover: #4F4DC9;
      --accent-light: #EEF0FF;
      --bg: #FAFAF9;
      --surface: #FFFFFF;
      --border: #E8E8E6;
      --border-hover: #C8C8C6;
      --text: #1A1A1A;
      --text-2: #5A5A5A;
      --text-3: #9A9A9A;
    }
    * { font-family: 'Plus Jakarta Sans', system-ui, sans-serif; }
    body { background-color: var(--bg); color: var(--text); }

    @keyframes pulse-glow { 0%,100%{opacity:1} 50%{opacity:.45} }
    .pulse { animation: pulse-glow 1.6s ease-in-out infinite; }

    @keyframes stripe {
      0%{background-position:0 0} 100%{background-position:40px 0}
    }
    .bar-animated {
      background-image: linear-gradient(
        45deg,
        rgba(255,255,255,.25) 25%, transparent 25%,
        transparent 50%, rgba(255,255,255,.25) 50%,
        rgba(255,255,255,.25) 75%, transparent 75%
      );
      background-size:40px 40px;
      animation: stripe 1s linear infinite;
    }

    ::-webkit-scrollbar { width:5px; height:5px; }
    ::-webkit-scrollbar-track { background: var(--bg); }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius:10px; }

    audio { width:100%; height:34px; }

    /* Bouton principal — style pill veed.io */
    .btn-primary {
      display: inline-flex; align-items: center; gap: 6px;
      background: var(--accent); color: #fff; font-weight: 700;
      padding: 8px 18px; border-radius: 100px; font-size: 13px;
      border: none; cursor: pointer; transition: background .15s, transform .1s;
      white-space: nowrap;
    }
    .btn-primary:hover { background: var(--accent-hover); transform: translateY(-1px); }
    .btn-primary:active { transform: translateY(0); }

    /* Bouton secondaire */
    .btn-secondary {
      display: inline-flex; align-items: center; gap: 6px;
      background: var(--surface); color: var(--text-2); font-weight: 600;
      padding: 7px 16px; border-radius: 100px; font-size: 13px;
      border: 1.5px solid var(--border); cursor: pointer;
      transition: border-color .15s, color .15s, background .15s;
      white-space: nowrap;
    }
    .btn-secondary:hover { border-color: var(--border-hover); color: var(--text); background: #F5F5F3; }

    /* Card job */
    .job-card {
      background: var(--surface);
      border: 1.5px solid var(--border);
      border-radius: 16px;
      padding: 20px;
      margin-bottom: 12px;
      transition: border-color .2s, box-shadow .2s;
      box-shadow: 0 1px 4px rgba(0,0,0,.04);
    }
    .job-card:hover {
      border-color: var(--border-hover);
      box-shadow: 0 4px 16px rgba(0,0,0,.07);
    }

    /* Tabs */
    .tab-btn {
      padding: 7px 18px; border-radius: 100px; font-size: 13px; font-weight: 700;
      border: 1.5px solid transparent; cursor: pointer; transition: all .15s;
      color: var(--text-3);
    }
    .tab-btn:hover { color: var(--text); border-color: var(--border); }
    .tab-btn.active {
      background: var(--accent-light); color: var(--accent);
      border-color: #C5C5F0;
    }

    /* Step pill */
    .step-pill {
      border: 1.5px solid;
      border-radius: 12px;
      padding: 8px 12px;
      text-align: center;
      min-width: 80px;
      transition: all .25s;
    }
    .step-done    { border-color: #86EFAC; background: #F0FDF4; }
    .step-running { border-color: var(--accent); background: var(--accent-light); box-shadow: 0 0 0 3px rgba(91,91,214,.12); }
    .step-failed  { border-color: #FCA5A5; background: #FFF1F2; }
    .step-pending { border-color: var(--border); background: #FAFAFA; }

    /* Input */
    .input-field {
      flex: 1; background: var(--bg); border: 1.5px solid var(--border);
      border-radius: 10px; padding: 9px 14px; font-size: 13px;
      color: var(--text); outline: none; transition: border-color .15s;
    }
    .input-field:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(91,91,214,.12); }
    .input-field::placeholder { color: var(--text-3); }

    /* Stat card */
    .stat-card {
      background: var(--surface); border: 1.5px solid var(--border);
      border-radius: 14px; padding: 16px 12px; text-align: center;
      box-shadow: 0 1px 3px rgba(0,0,0,.04);
    }

    /* Badge inline */
    .badge {
      display: inline-flex; align-items: center; gap: 4px;
      font-size: 11px; font-weight: 700; padding: 3px 10px;
      border-radius: 100px; border: 1.5px solid;
    }

    /* Toast notification */
    #toast {
      position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(8px);
      background: #1A1A1A; color: #fff; font-size: 13px; font-weight: 600;
      padding: 10px 20px; border-radius: 100px; opacity: 0;
      transition: opacity .2s, transform .2s; pointer-events: none; z-index: 999;
      white-space: nowrap;
    }
    #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  </style>
</head>
<body class="min-h-screen">

<!-- TOAST -->
<div id="toast">✓ Copié !</div>

<!-- HEADER -->
<header style="background:var(--surface); border-bottom: 1.5px solid var(--border);" class="sticky top-0 z-20">
  <div class="max-w-5xl mx-auto px-5 py-3 flex items-center justify-between gap-4">

    <!-- Logo -->
    <div class="flex items-center gap-2.5 shrink-0">
      <div style="background:var(--accent);" class="w-8 h-8 rounded-xl flex items-center justify-center">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
        </svg>
      </div>
      <div>
        <div style="font-size:14px; font-weight:800; color:var(--text); letter-spacing:-.3px;">VideoGen</div>
        <div style="font-size:10px; color:var(--text-3); font-weight:500; margin-top:-1px;">Monitor</div>
      </div>
    </div>

    <!-- Status + actions -->
    <div class="flex items-center gap-2.5">
      <div id="api-status" class="flex items-center gap-1.5" style="font-size:12px; color:var(--text-3);">
        <span id="status-dot" class="w-1.5 h-1.5 rounded-full inline-block" style="background:#D1D5DB;"></span>
        <span id="status-text">Connexion…</span>
      </div>
      <span id="last-refresh" class="hidden" style="font-size:11px; color:var(--text-3);">—</span>

      <!-- Lien direct (visible après auth) -->
      <button id="btn-share-link" onclick="copyDirectLink()" class="btn-secondary hidden" title="Copier le lien direct sans saisie de clé">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
          <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
        </svg>
        Lien direct
      </button>

      <button onclick="loadJobs()" class="btn-secondary">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
          <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
        </svg>
        Actualiser
      </button>
    </div>
  </div>

  <!-- TABS NAV -->
  <div class="max-w-5xl mx-auto px-5 pb-2.5 pt-1 flex gap-1">
    <button id="tab-btn-jobs" onclick="switchTab('jobs')" class="tab-btn active">
      Pipelines
    </button>
    <button id="tab-btn-voix" onclick="switchTab('voix')" class="tab-btn">
      Voix
    </button>
  </div>
</header>


<!-- ══════════════════ TAB : JOBS ══════════════════ -->
<div id="tab-jobs">

  <!-- AUTH BANNER -->
  <div id="auth-banner" class="hidden max-w-5xl mx-auto px-5 mt-8">
    <div style="background:var(--surface); border:1.5px solid var(--border); border-radius:16px; padding:24px;">
      <div style="font-size:15px; font-weight:800; color:var(--text); margin-bottom:4px;">Connexion requise</div>
      <p style="font-size:13px; color:var(--text-2); margin-bottom:16px;">
        Entrez votre clé API, ou accédez directement via
        <code style="background:var(--bg); padding:2px 6px; border-radius:6px; border:1px solid var(--border); font-size:11px;">/monitor?key=VOTRE_CLE</code>
      </p>
      <div class="flex gap-2">
        <input id="api-key-input" type="password" placeholder="Clé API secrète…" class="input-field">
        <button onclick="saveKey()" class="btn-primary">Se connecter</button>
      </div>
    </div>
  </div>

  <!-- MAIN JOBS -->
  <main class="max-w-5xl mx-auto px-5 py-6">

    <!-- Stats -->
    <div id="stats-bar" class="hidden grid grid-cols-4 gap-3 mb-6">
      <div class="stat-card">
        <div id="stat-total" style="font-size:28px; font-weight:800; color:var(--text);">—</div>
        <div style="font-size:11px; color:var(--text-3); margin-top:2px; font-weight:600;">Total</div>
      </div>
      <div class="stat-card" style="border-color:#86EFAC;">
        <div id="stat-done" style="font-size:28px; font-weight:800; color:#16A34A;">—</div>
        <div style="font-size:11px; color:var(--text-3); margin-top:2px; font-weight:600;">Terminés</div>
      </div>
      <div class="stat-card" style="border-color:#C5C5F0;">
        <div id="stat-running" style="font-size:28px; font-weight:800; color:var(--accent);">—</div>
        <div style="font-size:11px; color:var(--text-3); margin-top:2px; font-weight:600;">En cours</div>
      </div>
      <div class="stat-card" style="border-color:#FCA5A5;">
        <div id="stat-failed" style="font-size:28px; font-weight:800; color:#DC2626;">—</div>
        <div style="font-size:11px; color:var(--text-3); margin-top:2px; font-weight:600;">Échoués</div>
      </div>
    </div>

    <!-- Loading -->
    <div id="loading-state" class="text-center py-20" style="color:var(--text-3);">
      <div style="font-size:36px; margin-bottom:12px;" class="pulse">
        <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#C5C5F0" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin:0 auto;">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
      </div>
      <p style="font-size:14px; font-weight:600; color:var(--text-3);">Chargement des jobs…</p>
    </div>

    <!-- No jobs -->
    <div id="no-jobs" class="hidden text-center py-20" style="color:var(--text-3);">
      <div style="font-size:40px; margin-bottom:12px;">
        <svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="#D1D5DB" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin:0 auto;">
          <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
        </svg>
      </div>
      <p style="font-size:15px; font-weight:700; color:var(--text-2);">Aucun job pour l'instant</p>
      <p style="font-size:13px; color:var(--text-3); margin-top:6px;">Lance une génération depuis Google Sheets (Statut = ok)</p>
    </div>

    <!-- Jobs list -->
    <div id="jobs-container"></div>

  </main>

</div><!-- /tab-jobs -->


<!-- ══════════════════ TAB : VOIX ══════════════════ -->
<div id="tab-voix" class="hidden max-w-5xl mx-auto px-5 py-6">

  <!-- Instructions -->
  <div style="background:var(--accent-light); border:1.5px solid #C5C5F0; border-radius:14px; padding:18px; margin-bottom:20px;">
    <p style="font-size:13px; font-weight:700; color:var(--accent); margin-bottom:8px;">Comment utiliser ce catalogue</p>
    <ol style="font-size:13px; color:var(--text-2); padding-left:20px; line-height:1.8; margin:0;">
      <li>Écoute chaque voix avec le lecteur audio ▶</li>
      <li>Clique <strong>Copier ID</strong> sur la voix choisie</li>
      <li>Colle l'ID dans la colonne <strong>Voix (col F)</strong> du Google Sheet</li>
    </ol>
  </div>

  <!-- Loading state -->
  <div id="voices-loading" class="text-center py-20" style="color:var(--text-3);">
    <div class="pulse" style="margin-bottom:12px;">
      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#C5C5F0" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin:0 auto;">
        <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
      </svg>
    </div>
    <p style="font-size:14px; font-weight:600; color:var(--text-3);">Chargement des voix…</p>
  </div>

  <!-- Auth required for voices -->
  <div id="voices-auth" class="hidden text-center py-20" style="color:var(--text-3);">
    <div style="margin-bottom:12px;">
      <svg xmlns="http://www.w3.org/2000/svg" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#D1D5DB" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="margin:0 auto;">
        <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
      </svg>
    </div>
    <p style="font-size:15px; font-weight:700; color:var(--text-2);">Connecte-toi d'abord</p>
    <p style="font-size:13px; color:var(--text-3); margin-top:6px;">Utilise l'onglet <strong>Pipelines</strong> pour t'authentifier</p>
  </div>

  <!-- Voices grid -->
  <div id="voices-grid" class="hidden grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"></div>

  <!-- Add voice info -->
  <div id="voices-add" class="hidden mt-6 text-center" style="font-size:12px; color:var(--text-3);">
    Pour ajouter une voix : ajouter son ID dans
    <code style="background:var(--bg); padding:1px 5px; border-radius:5px; border:1px solid var(--border);">app/voices_catalog.json</code>
    puis redéployer.
  </div>

</div><!-- /tab-voix -->


<script>
// ── Config ──────────────────────────────────────────────────────────────────
const API_URL = window.location.origin;
let apiKey = localStorage.getItem('videogen_api_key') || '';

// Lire la clé depuis ?key=
const urlKey = new URLSearchParams(window.location.search).get('key');
if (urlKey) { apiKey = urlKey; localStorage.setItem('videogen_api_key', apiKey); }

// ── Toast ────────────────────────────────────────────────────────────────────
function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}

// ── Lien direct ──────────────────────────────────────────────────────────────
function copyDirectLink() {
  if (!apiKey) return;
  const url = `${window.location.origin}/monitor?key=${encodeURIComponent(apiKey)}`;
  const el = document.createElement('textarea');
  el.value = url;
  el.style.cssText = 'position:absolute;left:-9999px;top:0;opacity:0;';
  document.body.appendChild(el);
  el.select();
  document.execCommand('copy');
  document.body.removeChild(el);
  showToast('✓ Lien direct copié — partage-le à ton client !');
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function switchTab(tab) {
  document.getElementById('tab-jobs').classList.toggle('hidden', tab !== 'jobs');
  document.getElementById('tab-voix').classList.toggle('hidden', tab !== 'voix');
  document.getElementById('tab-btn-jobs').className = 'tab-btn' + (tab === 'jobs' ? ' active' : '');
  document.getElementById('tab-btn-voix').className = 'tab-btn' + (tab === 'voix' ? ' active' : '');
  if (tab === 'voix') loadVoices();
}

// ── Étapes du pipeline ───────────────────────────────────────────────────────
const STEPS = [
  { id:'claude',      label:'Claude',      icon:'🤖', api:'Anthropic',   runStatus:['running_claude'],                  minPct:10,  maxPct:25  },
  { id:'elevenlabs',  label:'ElevenLabs',  icon:'🎙️', api:'ElevenLabs',  runStatus:['running_elevenlabs'],              minPct:25,  maxPct:40  },
  { id:'clips',       label:'B-roll',      icon:'🎬', api:'Kling/Pexels',runStatus:['running_clips'],                   minPct:40,  maxPct:75  },
  { id:'creatomate',  label:'Rendu',       icon:'⚙️', api:'Creatomate',  runStatus:['running_creatomate','uploading'],  minPct:75,  maxPct:99  },
  { id:'done',        label:'Livré',       icon:'✅', api:'Drive',       runStatus:['completed'],                       minPct:100, maxPct:100 },
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
    done:    { cls:'step-done',    labelColor:'#16A34A', sym:'✓',  symBg:'#DCFCE7', symColor:'#15803D' },
    running: { cls:'step-running', labelColor:'#5B5BD6', sym:'…',  symBg:'#EEF0FF', symColor:'#5B5BD6' },
    failed:  { cls:'step-failed',  labelColor:'#DC2626', sym:'✗',  symBg:'#FEE2E2', symColor:'#DC2626' },
    pending: { cls:'step-pending', labelColor:'#9CA3AF', sym:'·',  symBg:'#F3F4F6', symColor:'#9CA3AF' },
  }[state];

  const clsExtra = state === 'running' ? ' pulse' : '';

  let extra = '';
  if (step.id === 'clips' && state === 'running' && job.progress?.clips_done != null) {
    extra = `<div style="font-size:10px;color:#5B5BD6;margin-top:2px;">${job.progress.clips_done}/${job.progress.clips_total}</div>`;
  }

  return `
    <div class="flex flex-col items-center gap-1">
      <div class="step-pill ${cfg.cls}${clsExtra}" style="min-width:78px;">
        <div style="font-size:18px; line-height:1;">${step.icon}</div>
        <div style="font-size:10px; font-weight:700; color:${cfg.labelColor}; margin-top:3px; white-space:nowrap;">${step.label}</div>
        <div style="font-size:9px; color:#9CA3AF; margin-top:1px;">${step.api}</div>
        ${extra}
        <div style="margin-top:4px; display:inline-block; font-size:10px; font-weight:700;
                    background:${cfg.symBg}; color:${cfg.symColor};
                    border-radius:100px; padding:1px 7px;">${cfg.sym}</div>
      </div>
    </div>`;
}

// ── Badge statut ──────────────────────────────────────────────────────────────
function statusBadge(s) {
  const map = {
    pending:            { t:'En attente',      border:'#E5E7EB', bg:'#F9FAFB', color:'#6B7280' },
    queued:             { t:'File d\'attente', border:'#FCD34D', bg:'#FFFBEB', color:'#92400E', pulse:true },
    running_claude:     { t:'Claude…',         border:'#C5C5F0', bg:'#EEF0FF', color:'#5B5BD6', pulse:true },
    running_elevenlabs: { t:'Voix off…',       border:'#D8B4FE', bg:'#F5F3FF', color:'#7C3AED', pulse:true },
    running_clips:      { t:'Clips…',          border:'#A5B4FC', bg:'#EEF2FF', color:'#4338CA', pulse:true },
    running_creatomate: { t:'Rendu…',          border:'#6EE7B7', bg:'#ECFDF5', color:'#065F46', pulse:true },
    uploading:          { t:'Envoi Drive…',    border:'#6EE7B7', bg:'#ECFDF5', color:'#065F46', pulse:true },
    completed:          { t:'Terminé',         border:'#86EFAC', bg:'#F0FDF4', color:'#16A34A' },
    failed:             { t:'Échoué',          border:'#FCA5A5', bg:'#FFF1F2', color:'#DC2626' },
  };
  const m = map[s] || { t:s, border:'#E5E7EB', bg:'#F9FAFB', color:'#6B7280' };
  return `<span class="badge${m.pulse?' pulse':''}"
    style="border-color:${m.border};background:${m.bg};color:${m.color};">${m.t}</span>`;
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
  const stepStates = STEPS.map(s => ({ step:s, state:getStepState(s, job) }));
  const pct = job.progress?.percentage ?? 0;
  const isRunning = !['completed','failed','pending','queued'].includes(job.status);

  const barColor = job.status === 'completed' ? '#16A34A'
                 : job.status === 'failed'    ? '#DC2626'
                 : '#5B5BD6';
  const barCls   = isRunning ? 'bar-animated' : '';

  const pctColor = job.status === 'completed' ? '#16A34A'
                 : job.status === 'failed'    ? '#DC2626'
                 : '#5B5BD6';

  const stepsHtml = stepStates.map(({ step, state }, i) => {
    const arrow = i < stepStates.length - 1
      ? `<div style="color:#D1D5DB; font-size:16px; padding-top:14px; flex-shrink:0;">›</div>`
      : '';
    return renderStep(step, state, job) + arrow;
  }).join('');

  const videoHtml = job.drive_url
    ? `<a href="${job.drive_url}" target="_blank"
          style="display:inline-flex;align-items:center;gap:8px;
                 background:#F0FDF4;border:1.5px solid #86EFAC;color:#16A34A;
                 font-size:13px;font-weight:700;padding:9px 18px;border-radius:100px;
                 text-decoration:none;transition:background .15s;"
          onmouseover="this.style.background='#DCFCE7'"
          onmouseout="this.style.background='#F0FDF4'">
         <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
           <polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/>
         </svg>
         Voir la vidéo générée
         <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
           <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
         </svg>
       </a>` : '';

  const errHtml = job.error
    ? `<div style="margin-top:12px;background:#FFF1F2;border:1.5px solid #FCA5A5;border-radius:12px;
                   padding:12px 14px;font-size:12px;color:#DC2626;font-family:monospace;
                   line-height:1.5;word-break:break-all;">
         ⚠️ ${job.error}
       </div>` : '';

  const detailHtml = (job.progress?.detail && !job.error && job.progress.detail !== job.progress.step)
    ? `<div style="font-size:11px;color:#9CA3AF;margin-top:3px;font-style:italic;">${job.progress.detail}</div>` : '';

  const dur = fmtDuration(job.created_at, job.updated_at);

  return `
    <div class="job-card">
      <!-- En-tête -->
      <div class="flex items-start justify-between gap-4 mb-5">
        <div style="min-width:0;flex:1;">
          <div class="flex items-center gap-2 flex-wrap">
            ${statusBadge(job.status)}
            <code style="font-size:10px;color:#9CA3AF;background:#F5F5F3;padding:2px 8px;
                         border-radius:6px;border:1px solid #E8E8E6;font-family:monospace;">
              ${job.job_id.substring(0,8)}…
            </code>
            ${dur ? `<span style="font-size:11px;color:#9CA3AF;display:inline-flex;align-items:center;gap:3px;">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
              ${dur}
            </span>` : ''}
          </div>
          <div style="font-size:11px;color:#9CA3AF;margin-top:6px;">
            Campagne
            <code style="background:#F5F5F3;padding:1px 6px;border-radius:5px;border:1px solid #E8E8E6;">${job.row_id}</code>
            · ${fmtDate(job.created_at)}
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0;">
          <div style="font-size:30px;font-weight:800;color:${pctColor};line-height:1;">${pct}%</div>
        </div>
      </div>

      <!-- Pipeline steps -->
      <div class="flex items-start gap-2 overflow-x-auto pb-2 mb-5" style="scrollbar-width:thin;">
        ${stepsHtml}
      </div>

      <!-- Barre de progression -->
      <div style="background:#F0F0EE;border-radius:100px;height:5px;overflow:hidden;margin-bottom:6px;">
        <div style="height:5px;border-radius:100px;width:${pct}%;background:${barColor};transition:width .7s ease;"
             class="${barCls}"></div>
      </div>

      <!-- Étape actuelle -->
      <div style="font-size:12px;color:#9CA3AF;font-weight:600;">${job.progress?.step ?? '—'}</div>
      ${detailHtml}
      ${errHtml}
      ${videoHtml ? `<div style="margin-top:16px;">${videoHtml}</div>` : ''}
    </div>`;
}

// ── Chargement des jobs ───────────────────────────────────────────────────────
function showAuthBanner() {
  document.getElementById('auth-banner').classList.remove('hidden');
  document.getElementById('loading-state').classList.add('hidden');
  document.getElementById('stats-bar').classList.add('hidden');
  document.getElementById('btn-share-link').classList.add('hidden');
  document.getElementById('jobs-container').innerHTML = '';
  document.getElementById('no-jobs').classList.add('hidden');
}

async function loadJobs() {
  if (!apiKey) { showAuthBanner(); return; }

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);

    const r = await fetch(`${API_URL}/jobs?key=${encodeURIComponent(apiKey)}`, {
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (r.status === 401) {
      apiKey = '';
      localStorage.removeItem('videogen_api_key');
      showAuthBanner();
      setStatus('red', 'Clé invalide');
      return;
    }

    const jobs = await r.json();

    setStatus('green', 'API en ligne');
    document.getElementById('btn-share-link').classList.remove('hidden');
    document.getElementById('last-refresh').classList.remove('hidden');
    document.getElementById('last-refresh').textContent =
      new Date().toLocaleTimeString('fr-FR');
    document.getElementById('loading-state').classList.add('hidden');
    document.getElementById('auth-banner').classList.add('hidden');

    // Stats
    document.getElementById('stats-bar').classList.remove('hidden');
    document.getElementById('stat-total').textContent   = jobs.length;
    document.getElementById('stat-done').textContent    = jobs.filter(j=>j.status==='completed').length;
    document.getElementById('stat-running').textContent = jobs.filter(j=>!['completed','failed','pending','queued'].includes(j.status)).length;
    document.getElementById('stat-failed').textContent  = jobs.filter(j=>j.status==='failed').length;

    if (jobs.length === 0) {
      document.getElementById('no-jobs').classList.remove('hidden');
      document.getElementById('jobs-container').innerHTML = '';
    } else {
      document.getElementById('no-jobs').classList.add('hidden');
      document.getElementById('jobs-container').innerHTML = jobs.map(renderJob).join('');
    }

  } catch (e) {
    document.getElementById('loading-state').classList.add('hidden');
    if (e.name === 'AbortError') {
      setStatus('red', 'Timeout — serveur lent');
    } else {
      setStatus('red', 'Hors ligne');
    }
    // Si on n'a jamais été authentifié, montrer le formulaire
    if (!document.getElementById('stats-bar').classList.contains('hidden') === false) {
      showAuthBanner();
    }
    console.error(e);
  }
}

function setStatus(color, text) {
  const dotColors  = { green:'#22C55E', red:'#EF4444', gray:'#D1D5DB' };
  const textColors = { green:'#16A34A', red:'#DC2626', gray:'#6B7280' };
  const dot  = document.getElementById('status-dot');
  const span = document.getElementById('status-text');
  dot.style.background = dotColors[color];
  span.style.color     = textColors[color];
  span.textContent     = text;
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
    const r = await fetch(`${API_URL}/voices?key=${encodeURIComponent(apiKey)}`);
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
         <p style="color:#DC2626;font-size:14px;font-weight:700;margin-bottom:6px;">Erreur de chargement</p>
         <p style="color:#9CA3AF;font-size:12px;margin-bottom:16px;">${e.message}</p>
         <button onclick="voicesLoaded=false; loadVoices()" class="btn-secondary">Réessayer</button>
       </div>`;
  }
}

// ── VOIX — Rendu d'une carte ──────────────────────────────────────────────────
function renderVoice(v) {
  const genderBadge = v.gender === 'female'
    ? '<span class="badge" style="border-color:#F9A8D4;background:#FDF2F8;color:#BE185D;">Femme</span>'
    : v.gender === 'male'
    ? '<span class="badge" style="border-color:#93C5FD;background:#EFF6FF;color:#1D4ED8;">Homme</span>'
    : '<span class="badge" style="border-color:#E5E7EB;background:#F9FAFB;color:#6B7280;">—</span>';

  const unavailableBanner = !v.available
    ? `<div style="margin-bottom:12px;background:#FFF1F2;border:1.5px solid #FCA5A5;border-radius:10px;padding:8px 12px;font-size:12px;color:#DC2626;">
         ⚠️ Voix inaccessible avec la clé API actuelle
       </div>` : '';

  const audioPlayer = v.preview_url
    ? `<div style="margin-top:12px;">
         <p style="font-size:10px;color:#9CA3AF;text-transform:uppercase;letter-spacing:.06em;font-weight:700;margin-bottom:4px;">Aperçu</p>
         <audio controls preload="none" style="width:100%;height:34px;border-radius:8px;overflow:hidden;">
           <source src="${v.preview_url}" type="audio/mpeg">
         </audio>
       </div>`
    : `<div style="margin-top:12px;font-size:11px;color:#9CA3AF;font-style:italic;">Pas d'aperçu disponible</div>`;

  const metaParts = [];
  if (v.accent)      metaParts.push(`🌍 ${v.accent}`);
  if (v.age)         metaParts.push(`🗓️ ${v.age}`);
  if (v.use_case)    metaParts.push(`💼 ${v.use_case}`);
  if (v.description) metaParts.push(`💬 ${v.description}`);
  const metaHtml = metaParts.length
    ? `<div style="margin-top:8px;margin-bottom:4px;">
         ${metaParts.map(p => `<div style="font-size:11px;color:#6B7280;line-height:1.7;">${p}</div>`).join('')}
       </div>`
    : '';

  const cardBorder = v.available ? 'var(--border)' : '#FCA5A5';

  return `
    <div style="background:var(--surface);border:1.5px solid ${cardBorder};border-radius:14px;padding:16px;
                display:flex;flex-direction:column;transition:border-color .15s,box-shadow .15s;box-shadow:0 1px 3px rgba(0,0,0,.04);"
         onmouseover="this.style.borderColor='${v.available ? 'var(--border-hover)' : '#F87171'}';this.style.boxShadow='0 4px 12px rgba(0,0,0,.07)';"
         onmouseout="this.style.borderColor='${cardBorder}';this.style.boxShadow='0 1px 3px rgba(0,0,0,.04)';">

      <!-- Nom + genre -->
      <div class="flex items-start justify-between gap-2 mb-1">
        <div style="font-weight:800;color:var(--text);font-size:14px;line-height:1.3;">${v.name || '—'}</div>
        ${genderBadge}
      </div>

      ${unavailableBanner}
      ${metaHtml}
      ${audioPlayer}

      <!-- ID + Copier -->
      <div style="margin-top:12px;padding-top:12px;border-top:1.5px solid var(--border);display:flex;align-items:center;gap:8px;">
        <code style="font-size:10px;color:#9CA3AF;font-family:monospace;flex:1;overflow:hidden;text-overflow:ellipsis;
                     white-space:nowrap;background:var(--bg);padding:4px 8px;border-radius:6px;border:1px solid var(--border);"
              title="${v.voice_id}">${v.voice_id}</code>
        <button onclick="copyId('${v.voice_id}', this)"
          style="flex-shrink:0;font-size:11px;font-weight:700;background:var(--accent-light);
                 color:var(--accent);border:1.5px solid #C5C5F0;border-radius:100px;
                 padding:4px 12px;cursor:pointer;transition:all .15s;white-space:nowrap;"
          onmouseover="this.style.background='var(--accent)';this.style.color='#fff';"
          onmouseout="this.style.background='var(--accent-light)';this.style.color='var(--accent)';">
          Copier ID
        </button>
      </div>
    </div>`;
}

// ── Copier dans le presse-papier (compatible HTTP) ────────────────────────────
function copyId(id, btn) {
  const el = document.createElement('textarea');
  el.value = id;
  el.style.cssText = 'position:absolute;left:-9999px;top:0;opacity:0;';
  document.body.appendChild(el);
  el.select();
  const ok = document.execCommand('copy');
  document.body.removeChild(el);

  if (ok) {
    showToast('✓ ID copié dans le presse-papier');
  } else {
    prompt('Copie manuellement cet ID :', id);
  }
}

// Actualisation auto toutes les 5s
setInterval(loadJobs, 5000);
loadJobs();
</script>
</body>
</html>"""
