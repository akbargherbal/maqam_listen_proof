r"""
Maqam Similarity Comparison App — backend (app.py)
====================================================
Serves templates/index.html + static/app.js, exposes a small JSON API,
and streams audio files for the reference track and ranked candidates
for each maqam.

PORTABILITY DESIGN
-------------------
1. All folder paths live in config.json, next to this script, and are
   resolved RELATIVE TO THIS SCRIPT'S LOCATION (not the current working
   directory) *unless* the configured path is already absolute (e.g. a
   full "D:\..." path), in which case it's used as-is. That means you
   can either keep data folders next to app.py, or point at folders
   anywhere else on disk (a different drive, a network share, etc.).

2. The CSVs record paths from a *different machine* (e.g. Colab's
   "/content/SUNO_BACKUP_11082026/..."). Rather than trust that path,
   this app builds an index of {filename -> real local path} by walking
   audio_root once, and resolves every track purely by filename. That
   means it doesn't matter whether the CSV path is a Colab path, a
   Windows path, or a Mac path -- only the filename has to match.

3. Every path can be changed three ways, in increasing priority:
       a) edited directly in config.json
       b) picked from the in-app Settings panel (gear icon, top-right)
          -- this writes back to config.json and takes effect
          immediately, no restart needed
       c) overridden with an environment variable (MAQAM_RESULTS_DIR /
          MAQAM_AUDIO_ROOT / MAQAM_REF_DIR) for one-off runs
   Env vars win if set; otherwise the last value saved (via file or
   Settings panel) is used.

SETUP
-----
    pip install flask pandas
    python app.py
Then open http://127.0.0.1:5000 and use the Settings panel to point
the app at your results/audio/reference folders if they aren't already
configured correctly.
"""

import os
import json
import string
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from flask import Flask, render_template, send_file, abort, request, jsonify

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# NOTE: this is THIS FILE's own folder (not its grandparent) -- config.json
# and relative data folders live alongside app.py.
BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "results_dir": "similarity_results",
    "audio_root": "UPLOAD_TO_GCP_11082026",
    "ref_dir": "REF",
    "maqam_arabic": {
        "hijaz": "حجاز",
        "ajam": "عجم",
        "kurd": "كرد",
        "nahawand": "نهاوند",
    },
    "audio_extensions": [".mp3", ".wav", ".flac", ".m4a"],
}

# Keys the Settings panel is allowed to change and persist.
EDITABLE_KEYS = ("results_dir", "audio_root", "ref_dir")

# In-memory config, loaded once at startup and mutated in place whenever
# the Settings panel (or an env var) changes a path.
CONFIG = dict(DEFAULT_CONFIG)


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"[config] Could not parse config.json ({e}); using defaults.")
    else:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            print(f"[config] Wrote default config.json at {CONFIG_PATH}")
        except Exception as e:
            print(f"[config] Could not write default config.json ({e}).")

    # Environment variables always win (useful for quick overrides).
    for key, env in [
        ("results_dir", "MAQAM_RESULTS_DIR"),
        ("audio_root", "MAQAM_AUDIO_ROOT"),
        ("ref_dir", "MAQAM_REF_DIR"),
    ]:
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    return cfg


def save_config():
    """Persist the current in-memory CONFIG's editable keys back to disk."""
    try:
        on_disk = {}
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                on_disk = json.load(f)
        on_disk.update({k: CONFIG[k] for k in EDITABLE_KEYS})
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(on_disk, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[config] Could not save config.json ({e}).")
        return False


def resolve(p: str) -> Path:
    """Resolve a config path relative to THIS script's folder unless it's absolute."""
    path = Path(p)
    return path if path.is_absolute() else (BASE_DIR / path).resolve()


def results_dir() -> Path:
    return resolve(CONFIG["results_dir"])


def audio_root() -> Path:
    return resolve(CONFIG["audio_root"])


def ref_dir() -> Path:
    return resolve(CONFIG["ref_dir"])


CONFIG = load_config()
MAQAM_ARABIC = CONFIG.get("maqam_arabic", {})
AUDIO_EXTS = tuple(e.lower() for e in CONFIG.get("audio_extensions", [".mp3"]))

app = Flask(__name__)  # uses default templates/ and static/ folders

# --------------------------------------------------------------------------
# Per-take identity + audio index
# --------------------------------------------------------------------------
# A basename alone is NOT a unique identifier: the same generated take can
# exist in several run folders (e.g. majnoon_layla_18082026 vs _19082026),
# each a *different* audio file that is ranked independently. Everything in
# the app -- ratings, stats, playback resolution -- is therefore keyed by a
# composite identity "<run folder>/<filename>", derived from the CSV's own
# `file` column (whose last folder is the run folder). That identity is
# stable across the top50 and full CSVs (they carry the same `file` values)
# and, because the local audio_root mirrors the run-folder layout, it maps
# 1:1 onto a local relative path.


def _norm(p) -> str:
    """Normalize a path string to forward slashes."""
    return str(p).replace("\\", "/").strip()


def item_identity(filename=None, filepath=None) -> str:
    """Composite per-take id: '<last folder of filepath>/<filename>'.

    Falls back to the bare filename when the row carries no folder (either
    no `file` column, or the file sat at the top of its tree).
    """
    fn = ""
    if filename is not None:
        fn = str(filename).strip()
    fp = _norm(filepath) if filepath else ""
    if not fn or fn.lower() in ("nan", "none"):
        fn = fp.rstrip("/").rsplit("/", 1)[-1] if fp else ""
    if not fn:
        return ""
    if fp:
        tail = fp.rstrip("/")
        head = tail.rsplit("/", 1)[0] if "/" in tail else ""
        parent = head.rsplit("/", 1)[-1] if head else ""
        if parent and parent != fn:
            return f"{parent}/{fn}"
    return fn


# Index of local audio by relative path under audio_root (posix). Because
# identical basenames may live in different run folders, the *key* is the
# relative path -- never the bare basename.
_audio_rel = {}
_audio_rel_low = {}
_index_root_used = None


def build_audio_index(force=False):
    global _audio_rel, _audio_rel_low, _index_root_used
    root = audio_root()
    if _audio_rel and not force and _index_root_used == root:
        return _audio_rel
    rel_index = {}
    if root.exists():
        base = root.resolve()
        for r, _dirs, files in os.walk(base):
            for fn in files:
                if fn.lower().endswith(AUDIO_EXTS):
                    full = Path(r) / fn
                    rel = str(full.relative_to(base)).replace("\\", "/")
                    rel_index.setdefault(rel, str(full))
    _audio_rel = rel_index
    _audio_rel_low = {k.lower(): v for k, v in rel_index.items()}
    _index_root_used = root
    return _audio_rel


def resolve_audio(item_id: str):
    """Map a per-take identity ('<run folder>/<filename>') to the local file,
    falling back to a case-insensitive match (Windows trees)."""
    if not item_id:
        return None
    if item_id in _audio_rel:
        return _audio_rel[item_id]
    low = item_id.lower()
    if low in _audio_rel_low:
        return _audio_rel_low[low]
    return None


def resolve_ref_file(maqam: str):
    arabic = MAQAM_ARABIC.get(maqam, "")
    rdir = ref_dir()
    if not rdir.exists():
        return None
    candidates = [f for f in rdir.iterdir() if f.is_file()]
    if arabic:
        for f in candidates:
            if f.name.startswith(arabic):
                return f
    for f in candidates:
        if maqam.lower() in f.name.lower():
            return f
    return None


# --------------------------------------------------------------------------
# Ranking data
# --------------------------------------------------------------------------


def list_maqams():
    rdir = results_dir()
    if not rdir.exists():
        return []
    # Match both full ranking files and top50 files
    names = set()
    for f in rdir.glob("*_ranking*.csv"):
        name = f.stem.replace("_ranking_top50", "").replace("_ranking", "")
        if name:
            names.add(name)
    return sorted(names)


def load_ranking(maqam: str, full: bool = False):
    rdir = results_dir()
    top50 = rdir / f"{maqam}_ranking_top50.csv"
    full_csv = rdir / f"{maqam}_ranking.csv"
    target = full_csv if (full or not top50.exists()) else top50
    if not target.exists():
        return None
    df = pd.read_csv(target, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    return df


# --------------------------------------------------------------------------
# Ratings (human review verdicts) -- persisted as JSON, one file per maqam
# --------------------------------------------------------------------------
# Keyed by the per-take identity "<run folder>/<filename>", never by rank or
# bare filename (the same basename can name 2-3 *distinct* takes, and the
# same take has a different rank in top50 vs full CSVs). Legacy ratings that
# were saved under a bare basename are migrated automatically on load: a
# basename that names exactly one take is re-keyed to that take's identity;
# a basename shared by several takes is ambiguous, so it is excluded from
# the active view (left on disk untouched) and must be re-rated per take.


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ratings_path(maqam: str) -> Path:
    return results_dir() / "ratings" / f"{maqam}.json"


def _basename_to_ids(maqam: str) -> dict:
    """{basename: {per-take ids}} built from the FULL ranking CSV. Used to
    migrate legacy ratings and to accept `filename` in the rating API."""
    df = load_ranking(maqam, full=True)
    if df is None:
        return {}
    m = {}
    for _, r in df.iterrows():
        fn = _row_filename(r)
        if fn:
            m.setdefault(fn, set()).add(_row_id(r))
    return m


def _migrate_ratings(maqam: str, raw: dict) -> dict:
    """Re-key a stored ratings dict (legacy basename keys -> per-take ids).

    Bare-basename keys that resolve to exactly one take are carried over.
    Keys on colliding basenames (2+ takes) are ambiguous and dropped from the
    active view -- they stay in the file, but the rows they could belong to
    are shown unrated so they can be re-rated individually.
    """
    m = _basename_to_ids(maqam)
    if not m:
        return dict(raw)  # no full CSV available; keep everything as-is
    known = {i for ids in m.values() for i in ids}
    out = {}
    for key, val in raw.items():
        if key in known:
            out[key] = val  # already a per-take id
            continue
        ids = m.get(key)
        if ids and len(ids) == 1:
            out[next(iter(ids))] = val  # unambiguous legacy basename
        elif key not in m:
            out[key] = val  # not part of this ranking; preserve
        # else: ambiguous basename -> intentionally excluded
    return out


def load_ratings(maqam: str) -> dict:
    """Return {per-take id: {"stars": int, "rated_at": str}} for a maqam."""
    p = ratings_path(maqam)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f).get("ratings", {})
    except Exception as e:
        print(f"[ratings] Could not parse {p} ({e}); treating as empty.")
        return {}
    return _migrate_ratings(maqam, raw)


def save_rating(maqam: str, item_id: str, stars):
    """Set (1-5) or clear (None) a single per-take id's rating and write it."""
    p = ratings_path(maqam)
    p.parent.mkdir(parents=True, exist_ok=True)

    data = {"maqam": maqam, "ratings": {}}
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data.setdefault("ratings", {})

    if stars is None:
        data["ratings"].pop(item_id, None)
    else:
        data["ratings"][item_id] = {"stars": int(stars), "rated_at": _now_iso()}

    data["maqam"] = maqam
    data["updated"] = _now_iso()

    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Stats (per-maqam + overall review progress)
# --------------------------------------------------------------------------


def _row_filename(r) -> str:
    csv_path = str(r.get("file") or r.get("filename") or "")
    return str(r.get("filename") or Path(csv_path).name)


def _row_id(r) -> str:
    """Per-take identity for a ranking row (pandas Series / row dict)."""
    return item_identity(r.get("filename"), r.get("file"))


def maqam_stats(name: str):
    """Per-maqam rating stats over the FULL ranking (ratings are keyed by
    per-take id, so a rating given in top-50 mode is still counted here)."""
    df = load_ranking(name, full=True)
    if df is None or not len(df):
        return None
    ratings = load_ratings(name)
    hist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    rated = 0
    total = 0
    for _, r in df.iterrows():
        iid = _row_id(r)
        if not iid:
            continue
        total += 1
        stars = ratings.get(iid, {}).get("stars")
        if isinstance(stars, int) and stars in hist:
            rated += 1
            hist[stars] += 1
    avg = (sum(k * v for k, v in hist.items()) / rated) if rated else None
    return {
        "name": name,
        "arabic": MAQAM_ARABIC.get(name, ""),
        "has_ref": resolve_ref_file(name) is not None,
        "total": total,
        "rated": rated,
        "unrated": total - rated,
        "avg_stars": round(avg, 2) if avg is not None else None,
        "stars": hist,
    }


def collect_stats():
    maqams = [m for m in (maqam_stats(n) for n in list_maqams()) if m]
    cand = sum(m["total"] for m in maqams)
    rated = sum(m["rated"] for m in maqams)
    hist = {k: sum(m["stars"][k] for m in maqams) for k in range(1, 6)}
    rated_avg = (sum(k * v for k, v in hist.items()) / rated) if rated else None
    return {
        "totals": {
            "candidates": cand,
            "rated": rated,
            "unrated": cand - rated,
            "pct": round(rated * 100.0 / cand, 1) if cand else 0.0,
            "avg_stars": round(rated_avg, 2) if rated_avg is not None else None,
            "stars": hist,
        },
        "maqams": maqams,
    }


# --------------------------------------------------------------------------
# Page route
# --------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


# --------------------------------------------------------------------------
# JSON API
# --------------------------------------------------------------------------


def _config_payload():
    rdir, adir, refd = results_dir(), audio_root(), ref_dir()
    return {
        "results_dir": str(rdir),
        "audio_root": str(adir),
        "ref_dir": str(refd),
        "results_exists": rdir.exists(),
        "audio_root_exists": adir.exists(),
        "ref_dir_exists": refd.exists(),
        "indexed_files": len(build_audio_index()),
        "maqam_count": len(list_maqams()),
        "is_configured": rdir.exists() and adir.exists(),
    }


@app.route("/api/config")
def api_config():
    return jsonify(_config_payload())


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """Read or update the three data-folder paths from the Settings panel."""
    if request.method == "POST":
        data = request.get_json(force=True, silent=True) or {}
        changed = False
        for key in EDITABLE_KEYS:
            val = data.get(key)
            if val is not None and str(val).strip():
                CONFIG[key] = str(val).strip()
                changed = True
        if changed:
            save_config()
            build_audio_index(force=True)
    return jsonify(_config_payload())


@app.route("/api/browse")
def api_browse():
    """Minimal folder browser so the Settings panel can pick directories
    without the user having to type/paste an absolute path by hand."""
    raw = request.args.get("path", "")
    try:
        p = Path(raw).expanduser().resolve() if raw else Path.home()
    except Exception:
        p = Path.home()
    if not p.exists() or not p.is_dir():
        p = Path.home()

    try:
        entries = sorted(
            (c for c in p.iterdir() if c.is_dir() and not c.name.startswith(".")),
            key=lambda c: c.name.lower(),
        )
        dirs = [{"name": d.name, "path": str(d)} for d in entries]
    except PermissionError:
        dirs = []

    drives = None
    if os.name == "nt":
        drives = [
            f"{letter}:\\"
            for letter in string.ascii_uppercase
            if os.path.exists(f"{letter}:\\")
        ]

    return jsonify(
        {
            "path": str(p),
            "parent": str(p.parent) if p.parent != p else None,
            "dirs": dirs,
            "drives": drives,
        }
    )


@app.route("/api/maqams")
def api_maqams():
    maqams = []
    for m in list_maqams():
        df = load_ranking(m, full=False)
        maqams.append(
            {
                "name": m,
                "arabic": MAQAM_ARABIC.get(m, ""),
                "count": len(df) if df is not None else 0,
                "has_ref": resolve_ref_file(m) is not None,
            }
        )
    return jsonify({"maqams": maqams, "config": _config_payload()})


@app.route("/api/maqam/<maqam>")
def api_maqam(maqam):
    full = request.args.get("full") == "1"
    df = load_ranking(maqam, full=full)
    if df is None:
        abort(404, f"No ranking CSV found for maqam '{maqam}'")

    ratings = load_ratings(maqam)

    rows = []
    for _, r in df.iterrows():
        iid = _row_id(r)
        local = resolve_audio(iid)
        filename = _row_filename(r)
        rows.append(
            {
                "id": iid,
                "rank": int(r.get("rank")),
                "filename": filename,
                "similarity": float(r.get("similarity", 0.0)),
                "found": local is not None,
                "stars": ratings.get(iid, {}).get("stars"),
            }
        )

    return jsonify(
        {
            "maqam": maqam,
            "arabic": MAQAM_ARABIC.get(maqam, ""),
            "has_ref": resolve_ref_file(maqam) is not None,
            "total": len(rows),
            "rated_count": len(ratings),
            "rows": rows,
        }
    )


@app.route("/api/stats")
def api_stats():
    return jsonify(collect_stats())


@app.route("/api/maqam/<maqam>/rating", methods=["POST"])
def api_set_rating(maqam):
    """Set or clear a star rating (1-5, or null/0 to clear) for one take.

    The payload should carry the per-take `id` (e.g. 'majnoon_layla_18082026/
    song.mp3'). A legacy bare `filename` is also accepted when it uniquely
    identifies one take; ambiguous names are rejected so the caller must
    re-rate each take explicitly.
    """
    data = request.get_json(force=True, silent=True) or {}
    item_id = str(data.get("id") or "").strip()
    filename = str(data.get("filename") or "").strip()
    stars = data.get("stars")

    if not item_id:
        if not filename:
            abort(400, "id (or a unique filename) is required")
        ids = _basename_to_ids(maqam).get(filename)
        if not ids:
            abort(400, f"'{filename}' does not appear in the '{maqam}' ranking")
        if len(ids) > 1:
            abort(
                400,
                f"'{filename}' names multiple takes in '{maqam}'; "
                "resend with the per-take id "
                f"({', '.join(sorted(ids))})",
            )
        item_id = next(iter(ids))

    if stars is not None and stars != 0 and not (1 <= int(stars) <= 5):
        abort(400, "stars must be an integer 1-5, or null/0 to clear")

    stars = int(stars) if stars else None
    save_rating(maqam, item_id, stars)

    ratings = load_ratings(maqam)
    return jsonify({"id": item_id, "stars": stars, "rated_count": len(ratings)})


@app.route("/refresh-index")
def refresh_index():
    idx = build_audio_index(force=True)
    return jsonify({"indexed_files": len(idx), "audio_root": str(audio_root())})


# --------------------------------------------------------------------------
# Audio streaming
# --------------------------------------------------------------------------


@app.route("/audio/ref/<maqam>")
def audio_ref(maqam):
    f = resolve_ref_file(maqam)
    if not f or not f.exists():
        abort(404)
    return send_file(f)


@app.route("/audio/track/<maqam>/<int:rank>")
def audio_track(maqam, rank):
    full = request.args.get("full") == "1"
    df = load_ranking(maqam, full=full)
    if df is None:
        abort(404)
    match = df[df["rank"] == rank]
    if match.empty:
        abort(404)
    row = match.iloc[0]
    local = resolve_audio(_row_id(row))
    if not local or not Path(local).exists():
        abort(404, f"Local audio file not found for rank {rank} in '{maqam}'")
    return send_file(local)


if __name__ == "__main__":
    print(f"[startup] results_dir = {results_dir()}")
    print(f"[startup] audio_root  = {audio_root()}")
    print(f"[startup] ref_dir     = {ref_dir()}")
    build_audio_index()
    print(f"[startup] indexed {len(_audio_rel)} audio files under audio_root")
    app.run(debug=True, port=5000)
