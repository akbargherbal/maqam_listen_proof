const state = { current: null, rows: [], full: false };
const browseState = { target: null, path: null };

const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

async function fetchJSON(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// --------------------------------------------------------------------------
// Exclusive audio playback: only one <audio> element plays at a time.
// Delegated on the document so it also covers rows added later.
// --------------------------------------------------------------------------
document.addEventListener('play', e => {
  if (e.target.tagName !== 'AUDIO') return;
  document.querySelectorAll('audio').forEach(a => {
    if (a !== e.target && !a.paused) a.pause();
  });
}, true);

// --------------------------------------------------------------------------
// Home view
// --------------------------------------------------------------------------

function renderConfigStatus(c) {
  document.getElementById('pathInfo').textContent =
    `results: ${c.results_dir}  |  audio root: ${c.audio_root}  |  ref: ${c.ref_dir}  |  indexed files: ${c.indexed_files}`;

  const notice = document.getElementById('setupNotice');
  notice.classList.toggle('hidden', c.is_configured);
}

async function loadHome() {
  const data = await fetchJSON('/api/maqams');
  renderConfigStatus(data.config);

  if (!data.config.is_configured || data.maqams.length === 0) {
    document.getElementById('maqamGrid').innerHTML = `
      <p class="text-gray-500 text-sm col-span-full">
        ${!data.config.is_configured
          ? 'No valid data folders configured yet. Click "Settings" above to point the app at your results, audio, and reference folders.'
          : 'Folders are configured but no *_ranking.csv files were found in the results folder.'}
      </p>`;
    return;
  }

  document.getElementById('maqamGrid').innerHTML = data.maqams.map(m => `
    <a href="#/maqam/${m.name}" class="block bg-gray-900 border border-gray-800 hover:border-sky-600 rounded-xl p-4 transition-colors">
      <h3 class="text-lg font-semibold">${cap(m.name)} <span class="text-purple-300">${m.arabic || ''}</span></h3>
      <p class="text-sm text-gray-400 mt-1">${m.count} ranked tracks</p>
      <span class="inline-block mt-2 text-xs px-2 py-0.5 rounded-full ${m.has_ref ? 'bg-gray-800 text-gray-300' : 'bg-red-950 text-red-300'}">
        ${m.has_ref ? 'reference found' : 'no reference found'}
      </span>
    </a>`).join('');
}

async function loadMaqam(name, full) {
  const data = await fetchJSON(`/api/maqam/${name}?full=${full ? 1 : 0}`);
  state.current = name; state.rows = data.rows; state.full = full;

  document.getElementById('maqamTitle').innerHTML = `${cap(name)} <span class="text-purple-300">${data.arabic || ''}</span>`;
  document.getElementById('maqamSub').textContent = `${data.total} tracks shown (${full ? 'full list' : 'top 50'})`;

  document.getElementById('refPlayerWrap').innerHTML = data.has_ref
    ? `<audio controls src="/audio/ref/${name}"></audio>`
    : `<span class="text-xs px-2 py-0.5 rounded-full bg-red-950 text-red-300">not found in REF folder</span>`;

  const toggleBtn = document.getElementById('toggleFullBtn');
  toggleBtn.textContent = full ? 'Show top 50 only' : 'Show full list';
  toggleBtn.onclick = () => { location.hash = `#/maqam/${name}${full ? '' : '/full'}`; };

  renderRows(data.rows);
}

function renderRows(rows) {
  document.getElementById('rowCount').textContent = `${rows.length} rows`;
  document.getElementById('tableBody').innerHTML = rows.map(r => `
    <tr class="border-t border-gray-800 ${r.found ? 'hover:bg-gray-800/60' : 'opacity-40'}" data-name="${r.filename.toLowerCase()}">
      <td class="px-3 py-2">${r.rank}</td>
      <td class="px-3 py-2 fname-rtl">${r.filename}</td>
      <td class="px-3 py-2 text-emerald-400 tabular-nums">${r.similarity.toFixed(4)}</td>
      <td class="px-3 py-2">
        ${r.found
          ? `<audio controls preload="none" class="w-56" src="/audio/track/${state.current}/${r.rank}?full=${state.full ? 1 : 0}"></audio>`
          : `<span class="text-xs px-2 py-0.5 rounded-full bg-red-950 text-red-300">file not found</span>`}
      </td>
    </tr>`).join('');
}

document.addEventListener('input', e => {
  if (e.target.id !== 'filterInput') return;
  const q = e.target.value.toLowerCase();
  document.querySelectorAll('#tableBody tr').forEach(tr => {
    tr.style.display = tr.dataset.name.includes(q) ? '' : 'none';
  });
});

async function route() {
  const hash = location.hash.replace(/^#\//, '');
  const home = document.getElementById('view-home');
  const detail = document.getElementById('view-maqam');
  if (!hash) {
    home.classList.remove('hidden'); detail.classList.add('hidden');
    await loadHome();
  } else {
    const [, name, mode] = hash.split('/');
    home.classList.add('hidden'); detail.classList.remove('hidden');
    document.getElementById('filterInput').value = '';
    await loadMaqam(name, mode === 'full');
  }
}

window.addEventListener('hashchange', route);
window.addEventListener('DOMContentLoaded', () => {
  route();
  initSettings();
});

// --------------------------------------------------------------------------
// Settings panel
// --------------------------------------------------------------------------

function statusBadge(exists) {
  return exists
    ? '<span class="text-emerald-400">found</span>'
    : '<span class="text-red-400">not found</span>';
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

  // Refresh whichever view is currently showing.
  if (!location.hash || location.hash === '#/') {
    await loadHome();
  } else {
    renderConfigStatus(c);
  }
}

function initSettings() {
  document.getElementById('settingsBtn').onclick = openSettings;
  document.getElementById('setupOpenSettings').onclick = openSettings;
  document.getElementById('settingsClose').onclick = closeSettings;
  document.getElementById('settingsCancel').onclick = closeSettings;
  document.getElementById('settingsSave').onclick = () => saveSettings().catch(err => {
    document.getElementById('settingsSavedMsg').textContent = 'Save failed: ' + err.message;
    document.getElementById('settingsSavedMsg').className = 'text-xs text-red-400';
  });

  document.querySelectorAll('.browseBtn').forEach(btn => {
    btn.onclick = () => {
      browseState.target = btn.dataset.target;
      const inputId = { results: 'inputResults', audio: 'inputAudio', ref: 'inputRef' }[browseState.target];
      openBrowse(document.getElementById(inputId).value);
    };
  });

  document.getElementById('browseClose').onclick = closeBrowse;
  document.getElementById('browseCancel').onclick = closeBrowse;
  document.getElementById('browseSelect').onclick = () => {
    const inputId = { results: 'inputResults', audio: 'inputAudio', ref: 'inputRef' }[browseState.target];
    document.getElementById(inputId).value = browseState.path;
    closeBrowse();
  };
}

// --------------------------------------------------------------------------
// Folder browser modal
// --------------------------------------------------------------------------

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
    data = await fetchJSON('/api/browse'); // fall back to home dir
  }
  browseState.path = data.path;
  document.getElementById('browseCurrentPath').textContent = data.path;

  const drives = document.getElementById('browseDrives');
  drives.innerHTML = (data.drives || []).map(d =>
    `<button class="drive-btn text-xs px-2 py-1 rounded bg-gray-800 hover:bg-gray-700" data-path="${d}">${d}</button>`
  ).join('');
  drives.querySelectorAll('.drive-btn').forEach(b => {
    b.onclick = () => navigateBrowse(b.dataset.path);
  });

  const rows = [];
  if (data.parent) {
    rows.push(`<button class="nav-row w-full text-left px-3 py-2 text-sm hover:bg-gray-800 flex items-center gap-2" data-path="${data.parent}">⬆️ <span class="text-gray-400">..</span></button>`);
  }
  data.dirs.forEach(d => {
    rows.push(`<button class="nav-row w-full text-left px-3 py-2 text-sm hover:bg-gray-800 flex items-center gap-2" data-path="${d.path}">📁 ${d.name}</button>`);
  });
  const list = document.getElementById('browseList');
  list.innerHTML = rows.join('') || '<p class="text-xs text-gray-500 p-3">No subfolders here.</p>';
  list.querySelectorAll('.nav-row').forEach(b => {
    b.onclick = () => navigateBrowse(b.dataset.path);
  });
}
