"""
review_html.py — Templates HTML pour la page de review des prompts Kling.
Servies par GET /review/{job_id} dans review.py.
Style : même charte que monitor_html.py (fond clair, typographie bold, accent violet).
"""

REVIEW_WAITING_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Review — Analyse en cours...</title>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    * {{ font-family: 'Plus Jakarta Sans', system-ui, sans-serif; }}
    body {{ background: #FAFAF9; color: #1A1A1A; }}
    @keyframes pulse-glow {{ 0%,100%{{opacity:1}} 50%{{opacity:.4}} }}
    .pulse {{ animation: pulse-glow 1.6s ease-in-out infinite; }}
  </style>
</head>
<body class="min-h-screen flex items-center justify-center">
  <div class="text-center p-8">
    <div class="pulse text-6xl mb-6">⏳</div>
    <h1 class="text-2xl font-bold mb-2">Analyse en cours...</h1>
    <p class="text-gray-500 mb-4">Job <code class="bg-gray-100 px-2 py-1 rounded text-sm">{job_id_short}</code></p>
    <p class="text-gray-400 text-sm">Les prompts seront disponibles dans quelques secondes.</p>
    <p class="text-gray-400 text-sm mt-1">Cette page se rafraîchit automatiquement.</p>
  </div>
  <script>
    setTimeout(() => window.location.reload(), 3000);
  </script>
</body>
</html>"""


REVIEW_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Review Prompts — {job_id_short}</title>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    :root {{
      --accent: #5B5BD6;
      --accent-hover: #4F4DC9;
      --accent-light: #EEF0FF;
      --bg: #FAFAF9;
      --surface: #FFFFFF;
      --border: #E8E8E6;
      --text: #1A1A1A;
      --text-2: #5A5A5A;
      --text-3: #9A9A9A;
    }}
    * {{ font-family: 'Plus Jakarta Sans', system-ui, sans-serif; }}
    body {{ background: var(--bg); color: var(--text); }}
    textarea {{ resize: vertical; }}
    .btn-primary {{
      display: inline-flex; align-items: center; gap: 6px;
      background: var(--accent); color: #fff; font-weight: 700;
      padding: 10px 20px; border-radius: 999px; border: none; cursor: pointer;
      transition: background .15s;
    }}
    .btn-primary:hover {{ background: var(--accent-hover); }}
    .btn-primary:disabled {{ opacity: .5; cursor: not-allowed; }}
    .badge {{
      display: inline-flex; align-items: center; gap: 4px;
      padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600;
    }}
    .badge-running {{ background: #FEF3C7; color: #92400E; }}
    .badge-completed {{ background: #D1FAE5; color: #065F46; }}
    .badge-failed {{ background: #FEE2E2; color: #991B1B; }}
    .badge-pending {{ background: #E0E7FF; color: #3730A3; }}
  </style>
</head>
<body class="pb-20">
  <!-- Header -->
  <div class="max-w-4xl mx-auto px-4 py-6">
    <div class="flex items-center justify-between mb-2">
      <h1 class="text-2xl font-extrabold">Review des prompts</h1>
      <span id="statusBadge" class="badge badge-pending">{status}</span>
    </div>
    <p class="text-sm text-gray-500">
      Job <code class="bg-gray-100 px-2 py-1 rounded">{job_id_short}</code>
      · Source : <strong>{source}</strong>
      · Durée totale : <strong>{total_duration}s</strong>
    </p>

    <!-- Script original (collapsible) -->
    <details class="mt-4 bg-white border border-gray-200 rounded-xl">
      <summary class="px-4 py-3 cursor-pointer font-semibold text-sm text-gray-600 hover:text-gray-900">
        📄 Script original (cliquer pour voir)
      </summary>
      <div class="px-4 pb-4 pt-1">
        <pre class="text-sm text-gray-700 whitespace-pre-wrap">{script_text}</pre>
      </div>
    </details>

    <!-- Drive URL if completed -->
    <div id="driveLink" class="mt-3 hidden">
      <a id="driveLinkUrl" href="#" target="_blank"
         class="text-sm font-semibold text-indigo-600 hover:text-indigo-800">
        🎬 Voir la vidéo finale →
      </a>
    </div>
  </div>

  <!-- Sections -->
  <div class="max-w-4xl mx-auto px-4 space-y-4" id="sectionsContainer"></div>

  <!-- Relaunch bar -->
  <div id="relaunchBar" class="hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg p-4">
    <div class="max-w-4xl mx-auto flex items-center justify-between">
      <div>
        <p class="text-sm font-semibold text-gray-700">Des modifications détectées</p>
        <p id="relaunchWarning" class="text-xs text-amber-600 hidden">
          ⚠️ Le pipeline original est encore en cours. Relancer crée un nouveau job parallèle.
        </p>
      </div>
      <button id="relaunchBtn" class="btn-primary" onclick="relaunch()">
        🚀 Relancer avec mes modifications
      </button>
    </div>
  </div>

  <script>
    const JOB_ID = "{job_id}";
    const TOKEN = "{token}";
    const API_BASE = "{api_base}";
    const DRIVE_URL = "{drive_url}";
    let sections = {sections_json};
    let originalSections = JSON.parse(JSON.stringify(sections));
    let currentStatus = "{status}";

    // Init drive link
    if (DRIVE_URL) {{
      document.getElementById('driveLink').classList.remove('hidden');
      document.getElementById('driveLinkUrl').href = DRIVE_URL;
    }}

    // Render sections
    function renderSections() {{
      const container = document.getElementById('sectionsContainer');
      container.innerHTML = '';
      sections.forEach((s, i) => {{
        const card = document.createElement('div');
        card.className = 'bg-white border border-gray-200 rounded-xl p-5';
        card.innerHTML = `
          <div class="flex items-center gap-3 mb-3">
            <span class="bg-indigo-100 text-indigo-700 text-xs font-bold px-2.5 py-1 rounded-full">
              Plan ${{s.id}}
            </span>
            <span class="text-xs text-gray-400">${{s.start}}s → ${{s.end}}s (${{s.duration}}s)</span>
            <select data-idx="${{i}}" data-field="scene_type"
                    class="ml-auto text-xs border border-gray-200 rounded-lg px-2 py-1 bg-gray-50"
                    onchange="onFieldChange(this)">
              ${{['emotion','product','testimonial','cta','ambient','tutorial'].map(t =>
                `<option value="${{t}}" ${{t===s.scene_type?'selected':''}}>` + t + `</option>`
              ).join('')}}
            </select>
          </div>
          <div class="mb-3 bg-gray-50 rounded-lg px-3 py-2">
            <p class="text-xs font-semibold text-gray-400 mb-1">Voix off</p>
            <p class="text-sm text-gray-700">${{s.text}}</p>
          </div>
          <div class="mb-3">
            <label class="text-xs font-semibold text-gray-500 mb-1 block">Prompt Kling</label>
            <textarea data-idx="${{i}}" data-field="broll_prompt"
                      class="w-full border border-gray-200 rounded-lg p-3 text-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-200 outline-none"
                      rows="3" oninput="onFieldChange(this)">${{s.broll_prompt}}</textarea>
          </div>
          <div>
            <label class="text-xs font-semibold text-gray-500 mb-1 block">Keywords (séparés par virgule)</label>
            <input data-idx="${{i}}" data-field="keywords" type="text"
                   class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:border-indigo-400 focus:ring-1 focus:ring-indigo-200 outline-none"
                   value="${{(s.keywords||[]).join(', ')}}" oninput="onFieldChange(this)">
          </div>
        `;
        container.appendChild(card);
      }});
    }}

    function onFieldChange(el) {{
      const idx = parseInt(el.dataset.idx);
      const field = el.dataset.field;
      if (field === 'keywords') {{
        sections[idx][field] = el.value.split(',').map(k => k.trim()).filter(Boolean);
      }} else {{
        sections[idx][field] = el.value;
      }}
      checkModified();
    }}

    function checkModified() {{
      const modified = JSON.stringify(sections) !== JSON.stringify(originalSections);
      const bar = document.getElementById('relaunchBar');
      bar.classList.toggle('hidden', !modified);
      // Show warning if pipeline still running
      const warn = document.getElementById('relaunchWarning');
      const isRunning = !['completed','failed'].includes(currentStatus);
      warn.classList.toggle('hidden', !isRunning);
    }}

    async function relaunch() {{
      const btn = document.getElementById('relaunchBtn');
      btn.disabled = true;
      btn.textContent = '⏳ Lancement...';

      try {{
        const body = {{
          sections: sections.map(s => ({{
            id: s.id,
            broll_prompt: s.broll_prompt,
            keywords: s.keywords || [],
            scene_type: s.scene_type,
          }}))
        }};

        const resp = await fetch(`${{API_BASE}}/review/${{JOB_ID}}/relaunch?token=${{TOKEN}}`, {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify(body),
        }});

        if (!resp.ok) {{
          const err = await resp.json();
          alert('Erreur: ' + (err.detail || 'Échec de la relance'));
          btn.disabled = false;
          btn.textContent = '🚀 Relancer avec mes modifications';
          return;
        }}

        const data = await resp.json();
        // Redirect to new review page
        window.location.href = `${{API_BASE}}/review/${{data.job_id}}`;
      }} catch (e) {{
        alert('Erreur réseau: ' + e.message);
        btn.disabled = false;
        btn.textContent = '🚀 Relancer avec mes modifications';
      }}
    }}

    // Status polling
    function updateStatusBadge(st) {{
      currentStatus = st;
      const badge = document.getElementById('statusBadge');
      const classes = {{
        completed: 'badge-completed',
        failed: 'badge-failed',
        pending: 'badge-pending',
      }};
      badge.className = 'badge ' + (classes[st] || 'badge-running');
      badge.textContent = st;
    }}

    async function pollStatus() {{
      try {{
        // Use query param auth since status endpoint requires it
        const resp = await fetch(`${{API_BASE}}/status/${{JOB_ID}}`);
        if (resp.ok) {{
          const data = await resp.json();
          updateStatusBadge(data.status);
          if (data.drive_url) {{
            document.getElementById('driveLink').classList.remove('hidden');
            document.getElementById('driveLinkUrl').href = data.drive_url;
          }}
        }}
      }} catch (e) {{
        // Silent fail — status polling is best-effort
      }}
    }}

    // Init
    renderSections();
    updateStatusBadge(currentStatus);
    // Poll status every 5s if not terminal
    setInterval(() => {{
      if (!['completed','failed'].includes(currentStatus)) pollStatus();
    }}, 5000);
  </script>
</body>
</html>"""
