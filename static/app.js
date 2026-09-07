const state = { current: null, rows: [], full: false, selectedCandidate: null, ratedCount: 0 };
const browseState = { target: null, path: null };

// --------------------------------------------------------------------------
// Filter & Sort state
// --------------------------------------------------------------------------
const DEFAULT_FILTERS = {
  q: '',               // lowercase filename search
  ratingStatus: 'any', // any | rated | unrated
  minStars: 0,         // 0 = any
  simBands: [],        // selected resemblance band ids
  avail: 'all',        // all | playable | missing
  sortKey: 'rank',     // rank | sim | stars | name
  sortAsc: true,       // rank/name default asc; sim/stars default desc
};
state.filters = { ...DEFAULT_FILTERS };

const SIM_BANDS = [
  { id: 'vc', label: 'Very close', min: 0.870, max: 1.001 },
  { id: 'cl', label: 'Close', min: 0.840, max: 0.870 },
  { id: 'mo', label: 'Moderate', min: 0.800, max: 0.840 },
  { id: 'di', label: 'Distant', min: 0.000, max: 0.800 },
];
const NATURAL_SORT_ASC = { rank: true, sim: false, stars: false, name: true };

function simBandOf(score) {
  return SIM_BANDS.find(b => score >= b.min && score < b.max)?.id || 'di';
}
function bandCount(id) {
  return state.rows.filter(r => simBandOf(r.similarity) === id).length;
}

function matchesFilters(r) {
  const f = state.filters;
  if (f.q && !r.filename.toLowerCase().includes(f.q)) return false;
  if (f.ratingStatus === 'rated' && !r.stars) return false;
  if (f.ratingStatus === 'unrated' && r.stars) return false;
  if (f.minStars && (!r.stars || r.stars < f.minStars)) return false;
  if (f.simBands.length && !f.simBands.includes(simBandOf(r.similarity))) return false;
  if (f.avail === 'playable' && !r.found) return false;
  if (f.avail === 'missing' && r.found) return false;
  return true;
}

function compareRows(a, b) {
  const f = state.filters;
  const dir = f.sortAsc ? 1 : -1;
  switch (f.sortKey) {
    case 'rank': return a.rank - b.rank;
    case 'sim':  return (a.similarity - b.similarity) * dir;
    case 'stars': {
      if (a.stars && b.stars) return (a.stars - b.stars) * dir;
      if (a.stars) return -1; // rated rows always above unrated
      if (b.stars) return 1;
      return a.rank - b.rank;
    }
    case 'name': return a.filename.localeCompare(b.filename) * dir;
    default: return a.rank - b.rank;
  }
}

function getFilteredSortedRows() {
  return state.rows.filter(matchesFilters).sort(compareRows);
}

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
  state.ratedCount = data.rated_count || 0;

  document.getElementById('maqamHeading').innerHTML = `${cap(name)} <span class="arabic text-2xl">${data.arabic || ''}</span>`;
  document.getElementById('maqamSub').textContent =
    `${data.total} tracks catalogued (${full ? 'full ranking' : 'top 50'}) · ${state.ratedCount} rated`;

  // Mode indicator: quiet tonal shade shift, no new hues, same palette as
  // hover/active states elsewhere in the app.
  const modeTag = document.getElementById('modeTag');
  const comparePanel = document.getElementById('comparePanel');
  if (modeTag) {
    modeTag.classList.remove('hidden');
    modeTag.textContent = full ? 'ALL FILES' : 'TOP 50';
    modeTag.classList.toggle('full', full);
  }
  if (comparePanel) {
    comparePanel.style.backgroundColor = full ? '#FAF4E6' : '';
  }

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
  document.getElementById('ratingRow').classList.add('hidden');

  // Top50 vs Full Toggle
  const toggleBtn = document.getElementById('toggleFullBtn');
  toggleBtn.textContent = full ? 'Switch to Top 50' : 'Switch to Full Ranking';
  toggleBtn.onclick = () => {
    location.hash = `#/maqam/${name}${full ? '' : '/full'}`;
  };

  // Rebuild list from scratch with default filters, then auto-select the
  // top row of the (default-sorted) visible set.
  resetFilters();
  const first = getFilteredSortedRows()[0];
  if (first) selectCandidate(first.rank);
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

  // Star rating widget: reflect this candidate's saved rating (if any)
  const ratingRow = document.getElementById('ratingRow');
  ratingRow.classList.remove('hidden');
  paintStars(document.getElementById('candStars'), t.stars || 0);

  // Highlight selected row in list
  document.querySelectorAll('.entry-row').forEach(row => {
    row.classList.toggle('active', parseInt(row.dataset.rank, 10) === rank);
  });
}

// --------------------------------------------------------------------------
// Star Ratings
// --------------------------------------------------------------------------
// `value` is the rating to *display*. `committed` (optional) is the actually
// saved rating; when it differs from `value` we're mid-hover-preview, so we
// paint with a distinct color instead of the "committed" gold.
function paintStars(container, value, committed) {
  if (!container) return;
  if (committed === undefined) committed = value;
  const isPreview = value !== committed;
  container.dataset.rating = committed;
  container.querySelectorAll('.star').forEach(s => {
    const on = parseInt(s.dataset.val, 10) <= value;
    s.textContent = on ? '★' : '☆';
    s.classList.toggle('filled', on && !isPreview);
    s.classList.toggle('preview', on && isPreview);
  });
  paintRatingChip(container, committed);
}

// Adds/updates a small "4/5" / "Not rated" chip next to a stars container,
// and toggles a rated-state background cue on the enclosing rating row.
function paintRatingChip(container, value) {
  let chip = container.parentElement?.querySelector('.rating-chip');
  if (!chip) return;
  const rated = value > 0;
  chip.textContent = rated ? `${value}/5` : 'Not rated';
  chip.classList.toggle('is-rated', rated);
  chip.classList.toggle('is-unrated', !rated);

  const ratingRow = document.getElementById('ratingRow');
  if (ratingRow && ratingRow.contains(container)) {
    ratingRow.classList.toggle('is-rated', rated);
  }
}

async function rateCandidate(rank, stars) {
  const t = state.rows.find(r => r.rank === rank);
  if (!t) return;

  const wasRated = t.stars != null;
  const prevStars = t.stars;

  // Optimistic UI update
  t.stars = stars || null;
  paintStars(document.getElementById('candStars'), t.stars || 0);
  updateListRowStars(rank, t.stars || 0);
  if (!wasRated && t.stars) state.ratedCount += 1;
  if (wasRated && !t.stars) state.ratedCount -= 1;
  updateRatedCountDisplay();
  // Re-apply the current filters to the LIST ONLY. This never touches
  // candPlayerWrap, so the currently-playing track in the Under Study
  // player is left completely untouched (no pause/reload/flicker), even if
  // this same track just got filtered out of the list below.
  applyRowFilters();
  reflowIfRatingSort();

  try {
    await fetchJSON(`/api/maqam/${state.current}/rating`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: t.filename, stars: t.stars }),
    });
  } catch (err) {
    // Revert optimistic update on failure
    t.stars = prevStars;
    paintStars(document.getElementById('candStars'), t.stars || 0);
    updateListRowStars(rank, t.stars || 0);
    if (!wasRated && stars) state.ratedCount -= 1;
    if (wasRated && !stars) state.ratedCount += 1;
    updateRatedCountDisplay();
    applyRowFilters();
    reflowIfRatingSort();
    alert('Could not save rating: ' + err.message);
  }
}

function updateListRowStars(rank, value) {
  const entryRow = document.querySelector(`.entry-row[data-rank="${rank}"]`);
  if (!entryRow) return;
  const starsEl = entryRow.querySelector('.rated-stars');
  if (starsEl) starsEl.innerHTML = starsGlyph(value);
  const chip = entryRow.querySelector('.rating-chip');
  if (chip) {
    const rated = value > 0;
    chip.textContent = rated ? `${value}/5` : '—';
    chip.classList.toggle('is-rated', rated);
    chip.classList.toggle('is-unrated', !rated);
  }
  entryRow.classList.toggle('is-rated', value > 0);
}

function starsGlyph(value) {
  let html = '';
  for (let i = 1; i <= 5; i++) {
    html += i <= value ? '<span class="on">★</span>' : '<span>☆</span>';
  }
  return html;
}

function updateRatedCountDisplay() {
  const sub = document.getElementById('maqamSub');
  if (!sub) return;
  const total = state.rows.length;
  sub.textContent = `${total} tracks catalogued (${state.full ? 'full ranking' : 'top 50'}) · ${state.ratedCount} rated`;
}

document.addEventListener('DOMContentLoaded', () => {
  const starsContainer = document.getElementById('candStars');
  if (starsContainer) {
    starsContainer.querySelectorAll('.star').forEach(s => {
      s.addEventListener('mouseenter', () => {
        const committed = parseInt(starsContainer.dataset.rating || '0', 10);
        paintStars(starsContainer, parseInt(s.dataset.val, 10), committed);
      });
      s.addEventListener('click', () => {
        const val = parseInt(s.dataset.val, 10);
        const current = parseInt(starsContainer.dataset.rating || '0', 10);
        const next = current === val ? 0 : val; // click same star again -> clear
        if (state.selectedCandidate != null) rateCandidate(state.selectedCandidate, next);
      });
    });
    starsContainer.addEventListener('mouseleave', () => {
      paintStars(starsContainer, parseInt(starsContainer.dataset.rating || '0', 10));
    });
  }

  const clearBtn = document.getElementById('clearRatingBtn');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (state.selectedCandidate != null) rateCandidate(state.selectedCandidate, 0);
    });
  }
});

// --------------------------------------------------------------------------
// Filter & Sort pipeline
// --------------------------------------------------------------------------
// Hide/show existing list rows based on current filters. Unlike a full
// re-render, this never touches candPlayerWrap, so the currently-playing
// "under study" track is not paused/reloaded even if it gets filtered out.
function applyRowFilters() {
  document.querySelectorAll('#entryList li').forEach(li => {
    const rank = parseInt(li.dataset.rank, 10);
    const row = state.rows.find(r => r.rank === rank);
    const show = row ? matchesFilters(row) : false;
    li.style.display = show ? '' : 'none';
  });
  refreshSummary();
}

// When the list is being reviewed "by my rating", a just-saved rating should
// reorder the list live; for other sort keys the row is merely hidden/shown.
function reflowIfRatingSort() {
  if (state.filters.sortKey === 'stars') renderFilteredList();
}

// Full rebuild of the list in sorted order (used on sort change, search,
// control changes, and maqam load). Selection is preserved by rank.
function renderFilteredList() {
  renderEntries(getFilteredSortedRows());
  refreshSummary();
}

function refreshSummary() {
  const total = state.rows.length;
  const shown = state.rows.filter(matchesFilters).length;
  const rowCount = document.getElementById('rowCount');
  if (rowCount) rowCount.textContent = `Showing ${shown} of ${total}`;
  renderActiveChips();
}

function renderActiveChips() {
  const box = document.getElementById('activeChips');
  if (!box) return;
  const f = state.filters;
  const chips = [];
  if (f.q) chips.push(removeChip('search', `“${f.q}”`));
  if (f.ratingStatus === 'rated') chips.push(removeChip('ratingStatus', 'Rated'));
  if (f.ratingStatus === 'unrated') chips.push(removeChip('ratingStatus', 'Unrated'));
  if (f.minStars) chips.push(removeChip('minStars', `★${f.minStars}+`));
  f.simBands.forEach(id => {
    const b = SIM_BANDS.find(x => x.id === id);
    if (b) chips.push(removeChip('simBands', b.label));
  });
  if (f.avail === 'playable') chips.push(removeChip('avail', 'Available'));
  if (f.avail === 'missing') chips.push(removeChip('avail', 'Missing'));
  const dirGlyph = f.sortAsc ? '▲ asc' : '▼ desc';
  chips.push(`<span class="text-[11px] mono text-[#B4A98F]">sorted by ${f.sortKey}${f.sortKey === 'rank' ? '' : ' ' + dirGlyph}</span>`);
  box.innerHTML = chips.length ? chips.join('') : '';
}

function removeChip(key, label) {
  return `<button class="chip on" data-remove="${key}" title="Remove filter">✕ ${label}</button>`;
}

// Apply a patch to state.filters, sync the control widgets, rebuild the list.
function applyFilters(patch) {
  Object.assign(state.filters, patch);
  // Switching sort key adopts that key's natural direction unless the caller
  // explicitly provides one (rank asc; score & rating desc; name asc).
  if (patch.sortKey && patch.sortAsc === undefined) {
    state.filters.sortAsc = NATURAL_SORT_ASC[patch.sortKey];
  }
  syncFilterControls();
  renderFilteredList();
}

function resetFilters() {
  state.filters = { ...DEFAULT_FILTERS };
  const input = document.getElementById('filterInput');
  if (input) input.value = '';
  syncFilterControls();
  renderFilteredList();
}

// Reflect state.filters back onto the sidebar controls (segmented buttons,
// star row, band checkboxes, direction label, min-star label).
function syncFilterControls() {
  const f = state.filters;
  setSeg('ratingStatusSeg', f.ratingStatus);
  setSeg('availSeg', f.avail);
  setSeg('sortSeg', f.sortKey);

  const minLabel = document.getElementById('minStarsLabel');
  if (minLabel) minLabel.textContent = f.minStars ? `★${f.minStars}` : 'any';
  document.querySelectorAll('#minStarsRow .star-min').forEach(s =>
    s.classList.toggle('on', parseInt(s.dataset.n, 10) <= f.minStars));

  renderBandButtons();
  syncDirBtn();
}

function setSeg(segId, val) {
  const seg = document.getElementById(segId);
  if (!seg) return;
  seg.querySelectorAll('.seg-btn').forEach(b =>
    b.classList.toggle('on', b.dataset.v === val));
}

function syncDirBtn() {
  const btn = document.getElementById('sortDirBtn');
  if (!btn) return;
  const f = state.filters;
  if (f.sortKey === 'rank') {
    btn.textContent = 'rank ▲ fixed';
    btn.style.opacity = '.5';
    btn.title = 'Rank is always ascending';
    return;
  }
  btn.style.opacity = '1';
  btn.textContent = f.sortAsc ? '▲ asc' : '▼ desc';
  btn.title = 'Toggle direction';
}

function renderBandButtons() {
  const box = document.getElementById('simBands');
  if (!box) return;
  box.innerHTML = SIM_BANDS.map(b => `
    <label class="band-row">
      <input type="checkbox" data-band="${b.id}" class="band-cb" ${state.filters.simBands.includes(b.id) ? 'checked' : ''}>
      <span>${b.label}</span>
      <span class="band-count">${bandCount(b.id)} · ≥${b.min.toFixed(3)}</span>
    </label>`).join('');
}

function bindFilterControls() {
  const on = (id, fn) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', fn);
  };

  const input = document.getElementById('filterInput');
  if (input) {
    input.addEventListener('input', e => applyFilters({ q: e.target.value.trim().toLowerCase() }));
  }

  on('filterResetBtn', () => resetFilters());

  on('ratingStatusSeg', e => {
    const b = e.target.closest('.seg-btn');
    if (b) applyFilters({ ratingStatus: b.dataset.v });
  });

  on('availSeg', e => {
    const b = e.target.closest('.seg-btn');
    if (b) applyFilters({ avail: b.dataset.v });
  });

  on('sortSeg', e => {
    const b = e.target.closest('.seg-btn');
    if (!b) return;
    const key = b.dataset.v;
    if (key === 'rank') {
      applyFilters({ sortKey: 'rank', sortAsc: true });
    } else if (state.filters.sortKey === key) {
      applyFilters({ sortAsc: !state.filters.sortAsc });
    } else {
      applyFilters({ sortKey: key, sortAsc: NATURAL_SORT_ASC[key] });
    }
  });

  on('sortDirBtn', () => {
    if (state.filters.sortKey === 'rank') return;
    applyFilters({ sortAsc: !state.filters.sortAsc });
  });

  const starsRow = document.getElementById('minStarsRow');
  if (starsRow) {
    starsRow.addEventListener('click', e => {
      const n = parseInt(e.target.dataset.n, 10);
      if (!n) return;
      const next = state.filters.minStars === n ? 0 : n; // click again to clear
      applyFilters({ minStars: next });
    });
    starsRow.addEventListener('mouseover', e => {
      const n = parseInt(e.target.dataset.n, 10);
      if (!n) return;
      starsRow.querySelectorAll('.star-min').forEach(s =>
        s.classList.toggle('hovering', parseInt(s.dataset.n, 10) <= n));
    });
    starsRow.addEventListener('mouseleave', () => {
      starsRow.querySelectorAll('.star-min').forEach(s => s.classList.remove('hovering'));
    });
  }

  const bands = document.getElementById('simBands');
  if (bands) {
    bands.addEventListener('change', e => {
      const cb = e.target.closest('.band-cb');
      if (!cb) return;
      const set = new Set(state.filters.simBands);
      if (cb.checked) set.add(cb.dataset.band);
      else set.delete(cb.dataset.band);
      applyFilters({ simBands: [...set] });
    });
  }

  const chipsBox = document.getElementById('activeChips');
  if (chipsBox) {
    chipsBox.addEventListener('click', e => {
      const key = e.target.closest('[data-remove]')?.dataset.remove;
      if (!key) return;
      if (key === 'search') { state.filters.q = ''; const i = document.getElementById('filterInput'); if (i) i.value = ''; }
      if (key === 'ratingStatus') state.filters.ratingStatus = 'any';
      if (key === 'minStars') state.filters.minStars = 0;
      if (key === 'simBands') state.filters.simBands = [];
      if (key === 'avail') state.filters.avail = 'all';
      syncFilterControls();
      renderFilteredList();
    });
  }
}

bindFilterControls();

function renderEntries(rows) {
  const list = document.getElementById('entryList');
  if (!list) return;

  list.innerHTML = rows.map(r => `
    <li class="entry-row cursor-pointer px-4 py-3 hover:bg-[#EDE3CC]/60 transition-colors ${r.found ? '' : 'opacity-50'} ${r.rank === state.selectedCandidate ? 'active' : ''} ${r.stars ? 'is-rated' : ''}" data-rank="${r.rank}">
      <div class="flex items-center gap-3">
        <span class="rated-stars w-14 shrink-0">${starsGlyph(r.stars || 0)}</span>
        <span class="rating-chip w-14 text-center shrink-0 ${r.stars ? 'is-rated' : 'is-unrated'}">${r.stars ? `${r.stars}/5` : '—'}</span>
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
  closeSettings, saveSettings, initSettings, openBrowse, closeBrowse, navigateBrowse,
  paintStars, rateCandidate, starsGlyph, applyRowFilters, applyFilters, resetFilters,
  getFilteredSortedRows, matchesFilters, simBandOf
};