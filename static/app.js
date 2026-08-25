const state = { current: null, rows: [], full: false, selectedCandidate: null };
const browseState = { target: null, path: null };

const cap = s => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '');

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

function qualitativeLabel(score) {
  if (score >= 0.87) return 'Very close resemblance';
  if (score >= 0.84) return 'Close resemblance';
  if (score >= 0.80) return 'Moderate resemblance';
  return 'Distant resemblance';
}

// --------------------------------------------------------------------------
// Audio Playback Delegation: Ensure only one audio element plays at a time
// --------------------------------------------------------------------------
document.addEventListener('play', e => {
  if (e.target.tagName !== 'AUDIO') return;
  document.querySelectorAll('audio').forEach(a => {
    if (a !== e.target && !a.paused) a.pause();
  });
}, true);

// --------------------------------------------------------------------------
// Status & Navigation
// --------------------------------------------------------------------------
function renderConfigStatus(c) {
  const info = document.getElementById('pathInfo');
  if (info) {
    info.textContent = `results: ${c.results_dir} | audio: ${c.audio_root} | ref: ${c.ref_dir} | indexed: ${c.indexed_files}`;
  }
  const notice = document.getElementById('setupNotice');
  if (notice) {
    notice.classList.toggle('hidden', Boolean(c.is_configured));
  }
}

async function loadCatalog() {
  const data = await fetchJSON('/api/maqams');
  renderConfigStatus(data.config);

  const nav = document.getElementById('maqamNav');
  const countEl = document.getElementById('maqamCountTotal');
  if (countEl) countEl.textContent = `${data.maqams.length} maqams`;

  if (!data.maqams || data.maqams.length === 0) {
    nav.innerHTML = `<p class="text-xs text-[#7A6F58] p-2">No ranking CSVs found in results folder.</p>`;
    return;
  }

  nav.innerHTML = data.maqams.map(m => {
    const active = m.name === state.current;
    return `
      <a href="#/maqam/${m.name}" data-maqam="${m.name}"
        class="maqam-nav-item block px-3 py-2 rounded-xl text-sm transition-colors paper-card ${active ? 'active' : 'hover:bg-[#EDE3CC]'}">
        <div class="flex items-center justify-between">
          <span class="font-semibold">${cap(m.name)}</span>
          <span class="arabic text-base">${m.arabic || ''}</span>
        </div>
        <div class="flex items-center justify-between text-xs text-[#7A6F58] mt-1">
          <span>${m.count} candidates</span>
          <span class="badge-ref text-[10px] px-1.5 py-0.2 rounded ${m.has_ref ? 'text-emerald-800' : 'text-red-800'}">
            ${m.has_ref ? '● ref' : '○ no ref'}
          </span>
        </div>
      </a>`;
  }).join('');
}

// --------------------------------------------------------------------------
// Maqam Workspace & Comparison Panel
// --------------------------------------------------------------------------
async function loadMaqam(name, full) {
  state.current = name;
  state.full = full;
  state.selectedCandidate = null;

  await loadCatalog();

  const emptyView = document.getElementById('emptyWorkspace');
  const activeView = document.getElementById('activeWorkspace');
  if (emptyView) emptyView.classList.add('hidden');
  if (activeView) activeView.classList.remove('hidden');

  const data = await fetchJSON(`/api/maqam/${name}?full=${full ? 1 : 0}`);
  state.rows = data.rows;

  document.getElementById('maqamHeading').innerHTML = `${cap(name)} <span class="arabic text-2xl">${data.arabic || ''}</span>`;
  document.getElementById('maqamSub').textContent = `${data.total} tracks catalogued (${full ? 'full ranking' : 'top 50'})`;

  // Reference Column
  document.getElementById('refName').textContent = data.has_ref ? `${data.arabic || name} Reference` : 'No reference audio located';
  document.getElementById('refBadge').textContent = data.has_ref ? 'Audio Found' : 'Missing File';
  document.getElementById('refPlayerWrap').innerHTML = data.has_ref
    ? `<audio controls src="/audio/ref/${name}"></audio>`
    : `<span class="text-xs px-2.5 py-1 rounded-full bg-red-100 text-red-800">Missing from reference folder</span>`;

  // Reset Candidate Column
  document.getElementById('candName').textContent = '— select an entry below —';
  document.getElementById('candNote').textContent = '';
  document.getElementById('candScoreBadge').textContent = '';
  document.getElementById('candPlayerWrap').innerHTML = `<audio controls disabled class="opacity-40"></audio>`;

  // Top50 vs Full Toggle
  const toggleBtn = document.getElementById('toggleFullBtn');
  toggleBtn.textContent = full ? 'Switch to Top 50' : 'Switch to Full Ranking';
  toggleBtn.onclick = () => {
    location.hash = `#/maqam/${name}${full ? '' : '/full'}`;
  };

  renderEntries(data.rows);

  // Auto-select #1 track if available
  if (data.rows.length > 0) {
    selectCandidate(data.rows[0].rank);
  }
}

function selectCandidate(rank) {
  state.selectedCandidate = rank;
  const t = state.rows.find(r => r.rank === rank);
  if (!t) return;

  document.getElementById('candName').textContent = t.filename;
  document.getElementById('candNote').textContent = `Rank #${t.rank} · ${qualitativeLabel(t.similarity)}`;
  document.getElementById('candScoreBadge').textContent = t.similarity.toFixed(4);

  const wrap = document.getElementById('candPlayerWrap');
  if (t.found) {
    wrap.innerHTML = `<audio controls autoplay src="/audio/track/${state.current}/${t.rank}?full=${state.full ? 1 : 0}"></audio>`;
  } else {
    wrap.innerHTML = `<span class="text-xs px-2.5 py-1 rounded-full bg-red-100 text-red-800">File not found in local audio root</span>`;
  }

  // Highlight selected row in list
  document.querySelectorAll('.entry-row').forEach(row => {
    row.classList.toggle('active', parseInt(row.dataset.rank, 10) === rank);
  });
}

function renderEntries(rows) {
  const rowCount = document.getElementById('rowCount');
  if (rowCount) rowCount.textContent = `${rows.length} rows`;

  const list = document.getElementById('entryList');
  if (!list) return;

  list.innerHTML = rows.map(r => `
    <li class="entry-row cursor-pointer px-4 py-3 hover:bg-[#EDE3CC]/60 transition-colors ${r.found ? '' : 'opacity-50'} ${r.rank === state.selectedCandidate ? 'active' : ''}" data-rank="${r.rank}">
      <div class="flex items-center gap-3">
        <span class="mono text-xs font-bold text-[#7A6F58] w-7 shrink-0">#${r.rank}</span>
        <div class="flex-1 min-w-0">
          <p class="arabic text-sm font-medium truncate">${r.filename}</p>
          <p class="text-[11px] italic text-[#7A6F58]">${qualitativeLabel(r.similarity)}</p>
        </div>
        <span class="mono text-xs font-bold text-[#2B3A55] w-16 text-right shrink-0">${r.similarity.toFixed(4)}</span>
        <span class="text-xs px-2 py-0.5 rounded-full ${r.found ? 'bg-[#EDE3CC] text-[#2B3A55]' : 'bg-red-100 text-red-800'} text-[10px]">
          ${r.found ? 'Play' : 'Missing'}
        </span>
      </div>
    </li>`).join('');

  list.querySelectorAll('.entry-row').forEach(row => {
    row.onclick = () => selectCandidate(parseInt(row.dataset.rank, 10));
  });
}

document.addEventListener('input', e => {
  if (e.target.id !== 'filterInput') return;
  const q = e.target.value.toLowerCase();
  document.querySelectorAll('#entryList li').forEach(li => {
    const filename = li.querySelector('.arabic')?.textContent.toLowerCase() || '';
    li.style.display = filename.includes(q) ? '' : 'none';
  });
});

// --------------------------------------------------------------------------
// Routing
// --------------------------------------------------------------------------
async function route() {
  const hash = location.hash.replace(/^#\//, '');
  if (!hash) {
    state.current = null;
    await loadCatalog();
    const activeView = document.getElementById('activeWorkspace');
    const emptyView = document.getElementById('emptyWorkspace');
    if (activeView) activeView.classList.add('hidden');
    if (emptyView) emptyView.classList.remove('hidden');
  } else {
    const [, name, mode] = hash.split('/');
    const filterInput = document.getElementById('filterInput');
    if (filterInput) filterInput.value = '';
    await loadMaqam(name, mode === 'full');
  }
}

window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', () => {
  route();
  initSettings();
});

// --------------------------------------------------------------------------
// Settings & Folder Browser Modals
// --------------------------------------------------------------------------
function statusBadge(exists) {
  return exists
    ? '<span class="text-emerald-700 font-semibold">● found</span>'
    : '<span class="text-red-700 font-semibold">○ not found</span>';
}

async function openSettings() {
  document.getElementById('settingsSavedMsg').textContent = '';
  const c = await fetchJSON('/api/config');
  document.getElementById('inputResults').value = c.results_dir;
  document.getElementById('inputAudio').value = c.audio_root;
  document.getElementById('inputRef').value = c.ref_dir;
  document.getElementById('statResults').innerHTML = statusBadge(c.results_exists);
  document.getElementById('statAudio').innerHTML = statusBadge(c.audio_root_exists);
  document.getElementById('statRef').innerHTML = statusBadge(c.ref_dir_exists);
  document.getElementById('settingsModal').classList.remove('hidden');
}

function closeSettings() {
  document.getElementById('settingsModal').classList.add('hidden');
}

async function saveSettings() {
  const payload = {
    results_dir: document.getElementById('inputResults').value,
    audio_root: document.getElementById('inputAudio').value,
    ref_dir: document.getElementById('inputRef').value,
  };
  const c = await fetchJSON('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  document.getElementById('statResults').innerHTML = statusBadge(c.results_exists);
  document.getElementById('statAudio').innerHTML = statusBadge(c.audio_root_exists);
  document.getElementById('statRef').innerHTML = statusBadge(c.ref_dir_exists);
  document.getElementById('settingsSavedMsg').textContent =
    c.is_configured ? `Saved — ${c.indexed_files} audio files indexed.` : 'Saved, but some folders were not found.';

  if (!location.hash || location.hash === '#/') {
    await loadCatalog();
  } else {
    renderConfigStatus(c);
  }
}

function initSettings() {
  const sBtn = document.getElementById('settingsBtn');
  if (sBtn) sBtn.onclick = openSettings;
  const setupBtn = document.getElementById('setupOpenSettings');
  if (setupBtn) setupBtn.onclick = openSettings;
  const sClose = document.getElementById('settingsClose');
  if (sClose) sClose.onclick = closeSettings;
  const sCancel = document.getElementById('settingsCancel');
  if (sCancel) sCancel.onclick = closeSettings;
  const sSave = document.getElementById('settingsSave');
  if (sSave) {
    sSave.onclick = () => saveSettings().catch(err => {
      const msg = document.getElementById('settingsSavedMsg');
      msg.textContent = 'Save failed: ' + err.message;
      msg.className = 'text-xs font-medium text-red-700';
    });
  }

  document.querySelectorAll('.browseBtn').forEach(btn => {
    btn.onclick = () => {
      browseState.target = btn.dataset.target;
      const inputId = { results: 'inputResults', audio: 'inputAudio', ref: 'inputRef' }[browseState.target];
      openBrowse(document.getElementById(inputId).value);
    };
  });

  const bClose = document.getElementById('browseClose');
  if (bClose) bClose.onclick = closeBrowse;
  const bCancel = document.getElementById('browseCancel');
  if (bCancel) bCancel.onclick = closeBrowse;
  const bSelect = document.getElementById('browseSelect');
  if (bSelect) {
    bSelect.onclick = () => {
      const inputId = { results: 'inputResults', audio: 'inputAudio', ref: 'inputRef' }[browseState.target];
      document.getElementById(inputId).value = browseState.path;
      closeBrowse();
    };
  }
}

async function openBrowse(startPath) {
  document.getElementById('browseModal').classList.remove('hidden');
  await navigateBrowse(startPath || '');
}

function closeBrowse() {
  document.getElementById('browseModal').classList.add('hidden');
}

async function navigateBrowse(path) {
  let data;
  try {
    data = await fetchJSON(`/api/browse?path=${encodeURIComponent(path || '')}`);
  } catch (err) {
    data = await fetchJSON('/api/browse');
  }
  browseState.path = data.path;
  document.getElementById('browseCurrentPath').textContent = data.path;

  const drives = document.getElementById('browseDrives');
  drives.innerHTML = (data.drives || []).map(d =>
    `<button class="drive-btn text-xs px-2 py-1 rounded paper-card hover:bg-[#EDE3CC] mono" data-path="${d}">${d}</button>`
  ).join('');
  drives.querySelectorAll('.drive-btn').forEach(b => {
    b.onclick = () => navigateBrowse(b.dataset.path);
  });

  const rows = [];
  if (data.parent) {
    rows.push(`<button class="nav-row w-full text-left px-3 py-2 text-xs hover:bg-[#EDE3CC] flex items-center gap-2 font-semibold" data-path="${data.parent}">⬆️ .. (Parent Directory)</button>`);
  }
  data.dirs.forEach(d => {
    rows.push(`<button class="nav-row w-full text-left px-3 py-2 text-xs hover:bg-[#EDE3CC] flex items-center gap-2" data-path="${d.path}">📁 ${d.name}</button>`);
  });
  const list = document.getElementById('browseList');
  list.innerHTML = rows.join('') || '<p class="text-xs text-[#7A6F58] p-3">No subfolders here.</p>';
  list.querySelectorAll('.nav-row').forEach(b => {
    b.onclick = () => navigateBrowse(b.dataset.path);
  });
}

// --------------------------------------------------------------------------
// Exports for Vitest
// --------------------------------------------------------------------------
export {
  cap, fetchJSON, qualitativeLabel, renderConfigStatus, loadCatalog, loadMaqam,
  selectCandidate, renderEntries, route, statusBadge, openSettings,
  closeSettings, saveSettings, initSettings, openBrowse, closeBrowse, navigateBrowse
};