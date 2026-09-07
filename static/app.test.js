import { describe, it, expect, beforeEach, vi } from 'vitest';
import * as app from './app.js';

window.removeEventListener('hashchange', app.route);

const FIXTURE_HTML = `
  <header>
    <p id="pathInfo"></p>
    <button id="settingsBtn"></button>
    <a id="brandHome" href="#/"></a>
    <button id="homeBtn"></button>
  </header>
  <div id="setupNotice" class="hidden">
    <button id="setupOpenSettings"></button>
  </div>

  <div id="maqamCountTotal"></div>
  <nav id="maqamNav"></nav>

  <aside>
    <div id="filterPanelWrap" class="hidden">
      <button id="filterResetBtn"></button>
    </div>
  </aside>

  <div id="studyWorkspace">
    <div id="homeView" class="hidden"></div>
    <div id="activeWorkspace" class="hidden">
      <h2 id="maqamHeading"></h2>
      <p id="maqamSub"></p>
      <button id="allMaqamsBtn"></button>
      <button id="toggleFullBtn"></button>
      
      <span id="refBadge"></span>
      <p id="refName"></p>
      <div id="refPlayerWrap"></div>

      <span id="candScoreBadge"></span>
      <p id="candName"></p>
      <p id="candNote"></p>
      <div id="candPlayerWrap"></div>
      <div id="ratingRow" class="hidden">
        <div id="candStars">
          <span class="star" data-val="1"></span>
          <span class="star" data-val="2"></span>
          <span class="star" data-val="3"></span>
          <span class="star" data-val="4"></span>
          <span class="star" data-val="5"></span>
        </div>
        <span class="rating-chip"></span>
      </div>
      <button id="clearRatingBtn"></button>

      <input id="filterInput" type="text">
      <div id="ratingStatusSeg">
        <button class="seg-btn" data-v="any">Any</button>
        <button class="seg-btn" data-v="rated">Rated</button>
        <button class="seg-btn" data-v="unrated">Unrated</button>
      </div>
      <span id="minStarsLabel"></span>
      <div id="minStarsRow">
        <span class="star-min" data-n="1">★</span>
        <span class="star-min" data-n="2">★</span>
        <span class="star-min" data-n="3">★</span>
        <span class="star-min" data-n="4">★</span>
        <span class="star-min" data-n="5">★</span>
      </div>
      <div id="simBands"></div>
      <div id="availSeg">
        <button class="seg-btn" data-v="all">All</button>
        <button class="seg-btn" data-v="playable">Available</button>
        <button class="seg-btn" data-v="missing">Missing</button>
      </div>
      <div id="sortSeg">
        <button class="seg-btn" data-v="rank">Rank</button>
        <button class="seg-btn" data-v="sim">Score</button>
        <button class="seg-btn" data-v="stars">My ★</button>
        <button class="seg-btn" data-v="name">Name</button>
      </div>
      <button id="sortDirBtn">rank ▲ fixed</button>
      <button id="filterResetBtn">reset all</button>
      <div id="activeChips"></div>
      <span id="rowCount"></span>
      <ul id="entryList"></ul>
    </div>
  </div>

  <div id="settingsModal" class="hidden">
    <span id="statResults"></span>
    <span id="statAudio"></span>
    <span id="statRef"></span>
    <input id="inputResults">
    <input id="inputAudio">
    <input id="inputRef">
    <button data-target="results" class="browseBtn"></button>
    <button data-target="audio" class="browseBtn"></button>
    <button data-target="ref" class="browseBtn"></button>
    <span id="settingsSavedMsg"></span>
    <button id="settingsClose"></button>
    <button id="settingsCancel"></button>
    <button id="settingsSave"></button>
  </div>

  <div id="browseModal" class="hidden">
    <p id="browseCurrentPath"></p>
    <div id="browseDrives"></div>
    <div id="browseList"></div>
    <button id="browseClose"></button>
    <button id="browseCancel"></button>
    <button id="browseSelect"></button>
  </div>
`;

function freshApp() {
  document.body.innerHTML = FIXTURE_HTML;
  return app;
}

function mockFetchOnce(payload, ok = true) {
  global.fetch = vi.fn().mockResolvedValue({
    ok,
    json: () => Promise.resolve(payload),
    text: () => Promise.resolve(JSON.stringify(payload)),
  });
}

beforeEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, '', '#/');
});

describe('cap & qualitativeLabel', () => {
  it('uppercases first letter', () => {
    const { cap } = freshApp();
    expect(cap('hijaz')).toBe('Hijaz');
  });

  it('categorizes similarity scores accurately', () => {
    const { qualitativeLabel } = freshApp();
    expect(qualitativeLabel(0.91)).toBe('Very close resemblance');
    expect(qualitativeLabel(0.85)).toBe('Close resemblance');
    expect(qualitativeLabel(0.81)).toBe('Moderate resemblance');
    expect(qualitativeLabel(0.72)).toBe('Distant resemblance');
  });
});

describe('statusBadge', () => {
  it('renders a green found badge when true', () => {
    const { statusBadge } = freshApp();
    expect(statusBadge(true)).toContain('found');
  });

  it('renders a red not found badge when false', () => {
    const { statusBadge } = freshApp();
    expect(statusBadge(false)).toContain('not found');
  });
});

describe('renderConfigStatus', () => {
  it('toggles setup notice based on configuration status', () => {
    const { renderConfigStatus } = freshApp();
    renderConfigStatus({ results_dir: '/r', audio_root: '/a', ref_dir: '/f', is_configured: false });
    expect(document.getElementById('setupNotice').classList.contains('hidden')).toBe(false);

    renderConfigStatus({ results_dir: '/r', audio_root: '/a', ref_dir: '/f', is_configured: true });
    expect(document.getElementById('setupNotice').classList.contains('hidden')).toBe(true);
  });
});

describe('renderEntries', () => {
  it('renders list items with rank, filename, and score', () => {
    const { renderEntries } = freshApp();
    renderEntries([
      { rank: 1, filename: 'track_one.mp3', similarity: 0.91, found: true },
      { rank: 2, filename: 'track_two.mp3', similarity: 0.82, found: false }
    ]);
    const items = document.querySelectorAll('#entryList li');
    expect(items.length).toBe(2);
    expect(items[0].textContent).toContain('track_one.mp3');
    expect(items[0].textContent).toContain('0.9100');
  });
});

describe('loadCatalog', () => {
  it('renders list of maqams in navigation sidebar', async () => {
    const { loadCatalog } = freshApp();
    mockFetchOnce({
      maqams: [{ name: 'hijaz', arabic: 'حجاز', count: 144, has_ref: true }],
      config: { results_dir: '/r', audio_root: '/a', ref_dir: '/f', is_configured: true }
    });
    await loadCatalog();
    const navItems = document.querySelectorAll('#maqamNav a');
    expect(navItems.length).toBe(1);
    expect(navItems[0].textContent).toContain('Hijaz');
    expect(navItems[0].textContent).toContain('حجاز');
  });
});

describe('rateCandidate + rating filters interaction', () => {
  function mockSequentialFetch(responses) {
    let call = 0;
    global.fetch = vi.fn().mockImplementation(() => {
      const payload = responses[Math.min(call, responses.length - 1)];
      call += 1;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(payload),
        text: () => Promise.resolve(JSON.stringify(payload)),
      });
    });
  }

  async function setupLoadedMaqam() {
    const { loadMaqam } = freshApp();
    mockSequentialFetch([
      { maqams: [{ name: 'hijaz', arabic: 'حجاز', count: 2, has_ref: true }],
        config: { results_dir: '/r', audio_root: '/a', ref_dir: '/f', is_configured: true } },
      { arabic: 'حجاز', total: 2, has_ref: true, rated_count: 0,
        rows: [
          { rank: 1, filename: 'track_one.mp3', similarity: 0.91, found: true, stars: null },
          { rank: 2, filename: 'track_two.mp3', similarity: 0.85, found: true, stars: null },
        ] },
    ]);
    await loadMaqam('hijaz', false);
  }

  function mockRatingPost() {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
      text: () => Promise.resolve('{}'),
    });
  }

  it('removes a newly-rated track from the list instantly when rating status is Unrated', async () => {
    await setupLoadedMaqam();
    const { rateCandidate } = app;
    app.applyFilters({ ratingStatus: 'unrated' });

    const row1 = document.querySelector('.entry-row[data-rank="1"]');
    expect(row1.style.display).not.toBe('none');

    mockRatingPost();
    await rateCandidate(1, 4);

    expect(row1.style.display).toBe('none');
  });

  it('never touches the candidate player when a track is rated', async () => {
    await setupLoadedMaqam();
    const { rateCandidate } = app;
    app.applyFilters({ ratingStatus: 'unrated' });

    const playerWrap = document.getElementById('candPlayerWrap');
    const playerHtmlBefore = playerWrap.innerHTML;

    mockRatingPost();
    await rateCandidate(1, 5);

    expect(playerWrap.innerHTML).toBe(playerHtmlBefore);
  });
});

describe('Filter & Sort controls', () => {
  const CATALOG_PAYLOAD = {
    maqams: [{ name: 'hijaz', arabic: 'حجاز', count: 3, has_ref: true }],
    config: { results_dir: '/r', audio_root: '/a', ref_dir: '/f', is_configured: true },
  };
  // rank 1: 5★, found, very close (0.91)
  // rank 2: unrated, found, close (0.85)
  // rank 3: 3★, missing, distant (0.78)
  const VARIED_ROWS = [
    { rank: 1, filename: 'alpha.mp3', similarity: 0.91, found: true, stars: 5 },
    { rank: 2, filename: 'beta.mp3', similarity: 0.85, found: true, stars: null },
    { rank: 3, filename: 'gamma.mp3', similarity: 0.78, found: false, stars: 3 },
  ];

  async function loadVariedMaqam() {
    const { loadMaqam } = freshApp();
    let call = 0;
    global.fetch = vi.fn().mockImplementation(() => {
      const payload = call === 0 ? CATALOG_PAYLOAD
        : { arabic: 'حجاز', total: VARIED_ROWS.length, has_ref: true, rated_count: 2, rows: VARIED_ROWS };
      call += 1;
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(payload),
        text: () => Promise.resolve(JSON.stringify(payload)),
      });
    });
    await loadMaqam('hijaz', false);
  }

  function visibleRanks() {
    return [...document.querySelectorAll('#entryList li')].map(li => parseInt(li.dataset.rank, 10));
  }

  it('defaults to showing every row in rank order', async () => {
    await loadVariedMaqam();
    expect(visibleRanks()).toEqual([1, 2, 3]);
    expect(document.getElementById('rowCount').textContent).toBe('Showing 3 of 3');
  });

  it('filters by rating status (Rated / Unrated)', async () => {
    await loadVariedMaqam();
    app.applyFilters({ ratingStatus: 'rated' });
    expect(visibleRanks()).toEqual([1, 3]);
    expect(document.getElementById('ratingStatusSeg').querySelector('.seg-btn[data-v="rated"]').classList.contains('on')).toBe(true);

    app.applyFilters({ ratingStatus: 'unrated' });
    expect(visibleRanks()).toEqual([2]);
  });

  it('filters by minimum star rating', async () => {
    await loadVariedMaqam();
    app.applyFilters({ minStars: 4 });
    expect(visibleRanks()).toEqual([1]);

    app.applyFilters({ minStars: 3 });
    expect(visibleRanks()).toEqual([1, 3]);
  });

  it('filters by resemblance band', async () => {
    await loadVariedMaqam();
    app.applyFilters({ simBands: ['vc'] });
    expect(visibleRanks()).toEqual([1]);

    app.applyFilters({ simBands: ['cl'] });
    expect(visibleRanks()).toEqual([2]);

    app.applyFilters({ simBands: ['di'] });
    expect(visibleRanks()).toEqual([3]);
  });

  it('filters by audio availability', async () => {
    await loadVariedMaqam();
    app.applyFilters({ avail: 'playable' });
    expect(visibleRanks()).toEqual([1, 2]);

    app.applyFilters({ avail: 'missing' });
    expect(visibleRanks()).toEqual([3]);
  });

  it('filters by filename search text', async () => {
    await loadVariedMaqam();
    app.applyFilters({ q: 'gamma' });
    expect(visibleRanks()).toEqual([3]);
    expect(document.getElementById('activeChips').textContent).toContain('gamma');
  });

  it('sorts by my rating (desc default, rated first)', async () => {
    await loadVariedMaqam();
    app.applyFilters({ sortKey: 'stars' });
    expect(visibleRanks()).toEqual([1, 3, 2]);

    app.applyFilters({ sortAsc: true });
    expect(visibleRanks()).toEqual([3, 1, 2]);
  });

  it('sorts by similarity score', async () => {
    await loadVariedMaqam();
    app.applyFilters({ sortKey: 'sim' });
    expect(visibleRanks()).toEqual([1, 2, 3]); // desc: high first

    app.applyFilters({ sortKey: 'sim', sortAsc: true });
    expect(visibleRanks()).toEqual([3, 2, 1]);
  });

  it('sorts by filename', async () => {
    await loadVariedMaqam();
    app.applyFilters({ sortKey: 'name' });
    expect(visibleRanks()).toEqual([1, 2, 3]);

    app.applyFilters({ sortAsc: false });
    expect(visibleRanks()).toEqual([3, 2, 1]);
  });

  it('resetFilters restores defaults (all rows, rank order, no chips)', async () => {
    await loadVariedMaqam();
    app.applyFilters({ q: 'beta', ratingStatus: 'rated', simBands: ['vc'] });
    expect(visibleRanks().length).toBe(0);

    app.resetFilters();
    expect(visibleRanks()).toEqual([1, 2, 3]);
    expect(document.getElementById('rowCount').textContent).toBe('Showing 3 of 3');
  });
});

describe('navigation & study-mode chrome', () => {
  const CONFIG = { results_dir: '/r', audio_root: '/a', ref_dir: '/f', is_configured: true };
  const CATALOG = { maqams: [{ name: 'hijaz', arabic: 'حجاز', count: 2, has_ref: true }], config: CONFIG };
  const DETAIL = { arabic: 'حجاز', total: 2, has_ref: true, rated_count: 0, rows: [
    { rank: 1, filename: 'a.mp3', similarity: 0.9, found: true, stars: null },
    { rank: 2, filename: 'b.mp3', similarity: 0.8, found: true, stars: null },
  ] };
  const STATS = {
    totals: { candidates: 2, rated: 1, unrated: 1, pct: 50, avg_stars: 4, stars: { 1: 0, 2: 0, 3: 0, 4: 1, 5: 0 } },
    maqams: [{ name: 'hijaz', arabic: 'حجاز', has_ref: true, total: 2, rated: 1, unrated: 1, avg_stars: 4, stars: { 1: 0, 2: 0, 3: 0, 4: 1, 5: 0 } }],
  };

  function mockRouteFetch(payloads) {
    let call = 0;
    global.fetch = vi.fn().mockImplementation(() => {
      const p = payloads[Math.min(call, payloads.length - 1)];
      call += 1;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(p), text: () => Promise.resolve(JSON.stringify(p)) });
    });
  }

  it('hides Filter & Sort and Home chrome on the home page', async () => {
    const { route } = freshApp();
    window.history.replaceState(null, '', '#/');
    mockRouteFetch([CATALOG, STATS]);
    await route();
    expect(document.getElementById('filterPanelWrap').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('homeBtn').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('activeWorkspace').classList.contains('hidden')).toBe(true);
    expect(document.getElementById('homeView').classList.contains('hidden')).toBe(false);
  });

  it('shows Filter & Sort and Home chrome inside a maqam', async () => {
    const { route } = freshApp();
    window.history.replaceState(null, '', '#/maqam/hijaz');
    mockRouteFetch([CATALOG, DETAIL]);
    await route();
    expect(document.getElementById('filterPanelWrap').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('homeBtn').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('activeWorkspace').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('homeView').classList.contains('hidden')).toBe(true);
  });
});

describe('home stats dashboard', () => {
  const CONFIG = { results_dir: '/r', audio_root: '/a', ref_dir: '/f', is_configured: true };
  const STATS = {
    totals: { candidates: 600, rated: 279, unrated: 321, pct: 46.5, avg_stars: 3.76, stars: { 1: 18, 2: 29, 3: 55, 4: 78, 5: 99 } },
    maqams: [
      { name: 'hijaz', arabic: 'حجاز', has_ref: true, total: 144, rated: 96, unrated: 48, avg_stars: 3.9, stars: { 1: 6, 2: 9, 3: 22, 4: 28, 5: 31 } },
      { name: 'nahawand', arabic: 'نهاوند', has_ref: false, total: 140, rated: 0, unrated: 140, avg_stars: null, stars: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 } },
    ],
  };

  it('builds KPI cards, overall histogram and per-maqam rows', () => {
    const { buildHomeDashboard } = freshApp();
    document.getElementById('homeView').innerHTML = buildHomeDashboard(STATS);
    const html = document.getElementById('homeView').textContent;
    expect(html).toContain('600');
    expect(html).toContain('279');
    expect(html).toContain('46.5%');
    expect(html).toContain('3.8');   // avg 3.76 -> toFixed(1)
    expect(html).toContain('STAR DISTRIBUTION');
    const links = [...document.querySelectorAll('#homeView a[href]')];
    expect(links.some(a => a.getAttribute('href') === '#/maqam/hijaz')).toBe(true);
    expect(links.some(a => a.getAttribute('href') === '#/maqam/nahawand')).toBe(true);
    // unrated maqam shows a dash for avg
    expect(html).toContain('No reference audio yet');
  });

  it('renders stats into the home view on route to the catalog', async () => {
    const { route } = freshApp();
    window.history.replaceState(null, '', '#/');
    let call = 0;
    global.fetch = vi.fn().mockImplementation(() => {
      const payload = call++ === 0
        ? { maqams: [{ name: 'hijaz', arabic: 'حجاز', count: 144, has_ref: true }], config: { results_dir: '/r', audio_root: '/a', ref_dir: '/f', is_configured: true } }
        : STATS;
      return Promise.resolve({ ok: true, json: () => Promise.resolve(payload), text: () => Promise.resolve(JSON.stringify(payload)) });
    });
    await route();
    const view = document.getElementById('homeView');
    expect(view.classList.contains('hidden')).toBe(false);
    expect(view.textContent).toContain('Review Progress');
    expect(view.textContent).toContain('PER MAQAM');
    expect(view.querySelector('a[href="#/maqam/hijaz"]')).toBeTruthy();
  });
});

describe('exclusive audio playback', () => {
  it('pauses all other audio elements when one plays', () => {
    freshApp();
    document.body.innerHTML += `
      <audio id="a1"></audio>
      <audio id="a2"></audio>
    `;
    const a1 = document.getElementById('a1');
    const a2 = document.getElementById('a2');
    const pauseSpy = vi.spyOn(a2, 'pause').mockImplementation(() => {});
    Object.defineProperty(a2, 'paused', { value: false, configurable: true });

    a1.dispatchEvent(new Event('play', { bubbles: true }));
    expect(pauseSpy).toHaveBeenCalled();
  });
});