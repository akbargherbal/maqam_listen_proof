# Reference vs. Candidate Listening & Rating Tool

A small local Flask app for A/B listening: play one **reference** audio clip
per category, browse a ranked list of **candidate** clips for that category,
and record a 1–5 star rating on each candidate as you listen. Ranking is
driven entirely by CSV files you provide, so the notion of "category" and
"similarity score" is whatever your own pipeline produced — the app itself
has no opinion about the domain.

It was originally built to review acoustic-similarity rankings between a
reference recording and many candidate recordings, but nothing about the
app is tied to that use case. Anything that can be expressed as *"one
reference item, many candidate items, a numeric score to rank them"* fits,
for example:

- Comparing multiple AI-generated takes on the same prompt against a
  reference track
- Comparing different masterings/mixes of the same song
- Comparing cover versions or re-recordings against an original
- Reviewing output from any audio-similarity or retrieval pipeline

## What it does

- Lists **categories** (each category = one reference clip + a CSV of
  ranked candidates).
- Plays the reference clip and the currently-selected candidate side by
  side.
- Shows each candidate's rank and similarity score, and lets you filter
  the candidate list by filename or by "unrated only."
- Lets you assign a 1–5 star rating to any candidate; ratings are saved
  immediately and persist per category.
- Treats every candidate row as one distinct **take** (see "Per-take
  identity" below), so two files that share a basename but live in different
  run folders are rated and played back independently.
- Resolves candidate audio files by their **run folder + filename** (it
  indexes your audio folder tree once), so it doesn't matter what machine or
  path format the CSV's file paths originally came from.
- Ships with a Settings panel (gear icon) to point the app at your data
  folders without editing files by hand.

## Requirements

- Python 3.9+
- `flask`, `pandas`
- Node.js + npm (only needed to run the frontend test suite)

## Setup

```bash
pip install flask pandas
python app.py
```

Then open `http://127.0.0.1:5000`. On first run, use the Settings panel
(gear icon, top-right) to point the app at your data folders if they
aren't already configured.

## Configuring your data

All folder locations live in `config.json`, next to `app.py`. Paths are
resolved **relative to `app.py`'s own location** (not your current working
directory) unless a path is already absolute, so you can either keep data
folders next to the app or point at folders anywhere else on disk.

| Config key    | What it should contain                                                                 |
|---------------|-------------------------------------------------------------------------------------------|
| `results_dir` | One ranking CSV per category: `<category>_ranking.csv` (and optionally a `<category>_ranking_top50.csv` for a shorter view). Ratings are also written here, under `ratings/<category>.json`. |
| `audio_root`  | Folder tree containing every candidate audio file. For per-take resolution, keep the layout `audio_root/<run folder>/<file>` mirroring the CSV `file` paths' run folders — subfolders below that don't matter. |
| `ref_dir`     | Folder containing one reference audio file per category.                                  |

Each ranking CSV needs at minimum these columns (the names below are the
defaults; the `experiment.columns` spec remaps them — see "Adapting to a
different A/B test"):

| Column       | Meaning                                                              |
|--------------|-----------------------------------------------------------------------|
| `rank`       | Integer rank within the category                                     |
| `filename`   | The candidate file's basename (shown in the UI)                      |
| `similarity` | Numeric score used for display/sorting (any scale you like)          |
| `file`       | Optional: an original path from wherever the CSV was generated. Its **last folder (the run folder) + filename** form the per-take identity used to resolve audio and to store ratings; the mount prefix is ignored. |

## Per-take identity

A bare filename is **not** a unique identifier: the same generated track can
exist in several run folders (`.../majnoon_layla_18082026/song.mp3` vs
`.../majnoon_layla_19082026/song.mp3`), each a *different* audio file that is
ranked independently. The app therefore keys everything — ratings, stats,
playback — by the composite identity `"<run folder>/<filename>"` taken from
the CSV's `file` column. That identity is shared between the full and top-N
views (they carry the same `file` values), so a rating given in one mode
appears in the other.

Rows whose take shares a basename with another take are shown with a small
run-folder tag so you can tell them apart while listening and rating.

Every path can also be overridden per-run with environment variables
(`AB_RESULTS_DIR`, `AB_AUDIO_ROOT`, `AB_REF_DIR`; the original
`MAQAM_RESULTS_DIR`, `MAQAM_AUDIO_ROOT`, `MAQAM_REF_DIR` still work).
Environment variables take priority over both the config file and the
Settings panel.

## Adapting to a different A/B test

Nothing about the app is tied to maqam: the domain vocabulary, the ranking
CSV column names, the score bands/precision, the ranking-file naming, and the
reference strategy all come from an **experiment spec**. The default spec
reproduces the maqam setup exactly, so an existing installation is unchanged.

A spec can live as an inline `"experiment"` block in `config.json`, or as a
named preset file `experiments/<id>.json` selected at run time:

```bash
AB_EXPERIMENT=example_models python app.py
# or point at any file directly:
AB_EXPERIMENT_FILE=/abs/path/to/spec.json python app.py
```

Precedence is: built-in defaults → `experiments/<id>.json` → inline
`experiment` block in `config.json`.

Spec fields (all optional; omitted fields fall back to the defaults):

| Field | Meaning |
|-------|---------|
| `id`, `title` | Identifier and the document/brand title shown in the UI. |
| `route_prefix` | URL hash prefix (`#/<prefix>/<category>`), default `maqam`. |
| `labels.singular` / `labels.plural` | What one group / many groups are called in the UI. |
| `display` | Optional per-category display text (e.g. script/RTL), replacing `maqam_arabic`. |
| `rtl` | Whether category labels are right-to-left. |
| `columns` | Maps the canonical `rank`, `name`, `score`, `path`, and optional `id`/explicit-id fields to your CSV's column names. Set a field to `null` to drop it (e.g. no `rank` column → ranks are inferred 1..N). |
| `score.direction` | `desc` (higher is better) or `asc`. |
| `score.decimals` | How many decimals to display for a score. |
| `score.bands` | Filter bands: `{id, label, qualitative, min, max}`. Drives the resemblance filter and the qualitative caption. |
| `ranking.glob` / `full_suffix` / `subset_suffix` / `subset_label` | How ranking CSVs are named and what the full-vs-subset toggle is called. |
| `reference.mode` | `folder_match` (default), `shared` (one `reference.file` for all), or `none` (candidate-only). |

A non-maqam example is included under `experiments/example_models.json` with
sample data in `examples/example_models/`. It ranks voice-model takes across
run folders, uses `variant`/`path`/`score` columns, a 0–100 score with custom
bands, and no reference:

```bash
AB_EXPERIMENT=example_models \
AB_RESULTS_DIR=examples/example_models/results \
AB_AUDIO_ROOT=examples/example_models/audio \
AB_REF_DIR=examples/example_models/ref \
python app.py
```

The generic API routes (`/api/categories`, `/api/category/<id>`,
`/api/category/<id>/rating`) mirror the original `/api/maqams`,
`/api/maqam/<id>`, and `/api/maqam/<id>/rating`, which remain available as
backward-compatible aliases.

## Ratings storage

Ratings are stored as plain JSON, one file per category, at
`results_dir/ratings/<category>.json`:

```json
{
  "category": "example",
  "updated": "2026-08-25T12:00:00Z",
  "ratings": {
    "run_folder/some_candidate_file.mp3": { "stars": 4, "rated_at": "2026-08-25T12:00:00Z" }
  }
}
```

Ratings are keyed by the per-take identity (never by rank or bare filename),
so a rating is preserved even if you switch between the full ranking and a
top-N view, and two takes that share a basename keep separate ratings.

**Migration from earlier basename-keyed files:** on load, any stored rating
whose key is a bare basename is migrated automatically. If that basename
names exactly one take, the rating carries over to it. If it names several
takes, the old rating is ambiguous, so it is left out of the active view
(kept on disk untouched) and those takes are shown unrated — re-rate each
one individually.

## Running tests

```bash
# Backend (pytest)
pip install pytest
pytest

# Frontend (vitest)
npm install
npm test
```

## Project layout

```
app.py                    Flask backend, API routes, audio streaming
config.json                Editable folder paths + app settings
templates/index.html       Single-page UI
static/app.js              Frontend logic (routing, rendering, ratings)
static/app.test.js         Frontend unit tests (vitest)
tests/                      Backend unit tests (pytest)
similarity_results/         Example ranking CSVs + embeddings cache (sample data)
```
