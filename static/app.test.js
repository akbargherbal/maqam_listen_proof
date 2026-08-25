import { describe, it, expect, beforeEach, vi } from 'vitest';
import * as app from './app.js';

window.removeEventListener('hashchange', app.route);

const FIXTURE_HTML = `
  <header>
    <p id="pathInfo"></p>
    <button id="settingsBtn"></button>
  </header>
  <div id="setupNotice" class="hidden">
    <button id="setupOpenSettings"></button>
  </div>

  <div id="maqamCountTotal"></div>
  <nav id="maqamNav"></nav>

  <div id="studyWorkspace">
    <div id="emptyWorkspace" class="hidden"></div>
    <div id="activeWorkspace" class="hidden">
      <h2 id="maqamHeading"></h2>
      <p id="maqamSub"></p>
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
      <input id="unratedOnlyCheckbox" type="checkbox">
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

describe('rateCandidate + "unrated only" filter interaction', () => {
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

  it('removes a newly-rated track from the list instantly when "unrated only" is on', async () => {
    await setupLoadedMaqam();
    const { rateCandidate } = app;
    document.getElementById('unratedOnlyCheckbox').checked = true;

    // rateCandidate posts to the rating endpoint; mock that call too.
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
      text: () => Promise.resolve('{}'),
    });

    const row1 = document.querySelector('.entry-row[data-rank="1"]');
    expect(row1.style.display).not.toBe('none');

    await rateCandidate(1, 4);

    expect(row1.style.display).toBe('none');
  });

  it('never touches the candidate player when a track is rated', async () => {
    await setupLoadedMaqam();
    const { rateCandidate } = app;
    document.getElementById('unratedOnlyCheckbox').checked = true;

    const playerWrap = document.getElementById('candPlayerWrap');
    const playerHtmlBefore = playerWrap.innerHTML;

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
      text: () => Promise.resolve('{}'),
    });

    await rateCandidate(1, 5);

    expect(playerWrap.innerHTML).toBe(playerHtmlBefore);
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