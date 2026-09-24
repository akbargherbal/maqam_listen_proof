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
       c) overridden with an environment variable (AB_RESULTS_DIR /
          AB_AUDIO_ROOT / AB_REF_DIR, or the legacy MAQAM_* names) for
          one-off runs
   Env vars win if set; otherwise the last value saved (via file or
   Settings panel) is used.

4. Domain specifics are NOT hardcoded. An "experiment" spec (built-in
   defaults, optionally overridden by experiments/<id>.json selected with
   AB_EXPERIMENT, and/or an inline "experiment" block in config.json) defines
   the group noun/labels, the ranking CSV column names, the score direction,
   precision and filter bands, the ranking-file naming, and the reference
   strategy. The default spec reproduces the maqam setup exactly. See README
   "Adapting to a different A/B test".

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

# --------------------------------------------------------------------------
# Experiment spec (generic A/B testing)
# --------------------------------------------------------------------------
# Everything domain-specific -- the noun for a group ("maqam", "prompt",
# "model", ...), the ranking CSV column names, the score direction/bands, the
# ranking file naming, and how a reference item is located -- lives in one
# declarative spec. DEFAULT_EXPERIMENT below reproduces this app's original
# maqam behavior exactly, so an unconfigured run is unchanged. A spec can be
# supplied (in increasing priority) by:
#     a) an experiments/<id>.json file, selected with the AB_EXPERIMENT env
#        var or an "id" in the inline `experiment` config block, or
#        AB_EXPERIMENT_FILE=/abs/path.json
#     b) an inline "experiment" block in config.json
# so a new A/B test never requires editing Python.

DEFAULT_EXPERIMENT = {
    "id": "maqam",
    "title": "Maqam Study",
    "route_prefix": "maqam",
    "labels": {"singular": "maqam", "plural": "maqams"},
    "display": {},
    "rtl": True,
    "columns": {
        "rank": "rank",
        "name": "filename",
        "score": "similarity",
        "path": "file",
        "id": None,
    },
    "score": {
        "direction": "desc",
        "decimals": 4,
        "bands": [
            {"id": "vc", "label": "Very close", "qualitative": "Very close resemblance", "min": 0.870, "max": 1.001},
            {"id": "cl", "label": "Close", "qualitative": "Close resemblance", "min": 0.840, "max": 0.870},
            {"id": "mo", "label": "Moderate", "qualitative": "Moderate resemblance", "min": 0.800, "max": 0.840},
            {"id": "di", "label": "Distant", "qualitative": "Distant resemblance", "min": 0.000, "max": 0.800},
        ],
    },
    "ranking": {
        "glob": "*_ranking*.csv",
        "full_suffix": "",
        "subset_suffix": "_top50",
        "subset_label": "Top 50",
    },
    "reference": {"mode": "folder_match", "file": None},
}

EXPERIMENTS_DIRNAME = "experiments"

# Keys the Settings panel is allowed to change and persist.
EDITABLE_KEYS = ("results_dir", "audio_root", "ref_dir")


def _deep_merge(base, override):
    """Recursively merge `override` onto `base` (dicts only); returns a copy."""
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _deep_merge(out[k], v) if k in out else v
        return out
    return override


def load_experiment(cfg):
    """Resolve the effective experiment spec from defaults + preset + config."""
    exp = json.loads(json.dumps(DEFAULT_EXPERIMENT))  # deep copy
    inline = cfg.get("experiment") if isinstance(cfg.get("experiment"), dict) else {}

    exp_id = os.environ.get("AB_EXPERIMENT") or inline.get("id")
    preset_path = None
    if os.environ.get("AB_EXPERIMENT_FILE"):
        preset_path = resolve(os.environ["AB_EXPERIMENT_FILE"])
    elif exp_id:
        base = resolve(cfg.get("experiments_dir", EXPERIMENTS_DIRNAME))
        cand = base / f"{exp_id}.json"
        if cand.exists():
            preset_path = cand

    if preset_path and preset_path.exists():
        try:
            exp = _deep_merge(exp, json.loads(preset_path.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[experiment] Could not parse {preset_path} ({e}); using defaults.")

    exp = _deep_merge(exp, inline)
    if exp_id:
        exp["id"] = exp_id
    # The original `maqam_arabic` map seeds the per-category display text only
    # for the built-in maqam preset, so other experiments don't inherit it.
    if exp.get("id") == DEFAULT_EXPERIMENT["id"] and not exp.get("display") \
            and isinstance(cfg.get("maqam_arabic"), dict):
        exp["display"] = dict(cfg["maqam_arabic"])
    return exp

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

    # Environment variables always win (useful for quick overrides). Generic
    # AB_* names are preferred; the original MAQAM_* names still work.
    for key, envs in [
        ("results_dir", ("AB_RESULTS_DIR", "MAQAM_RESULTS_DIR")),
        ("audio_root", ("AB_AUDIO_ROOT", "MAQAM_AUDIO_ROOT")),
        ("ref_dir", ("AB_REF_DIR", "MAQAM_REF_DIR")),
    ]:
        for env in envs:
            if os.environ.get(env):
                cfg[key] = os.environ[env]
                break
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
EXPERIMENT = load_experiment(CONFIG)
# Per-category display text (e.g. Arabic script). Kept under the historical
# name for callers that still use it; sourced from the experiment spec now.
MAQAM_ARABIC = EXPERIMENT.get("display") or CONFIG.get("maqam_arabic", {})
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


def _columns():
    return EXPERIMENT.get("columns") or {}


def _ranking_cfg():
    return EXPERIMENT.get("ranking") or {}


def _as_int(v, default=None):
    """Best-effort int coercion; NaN/missing/garbage -> default (never raises)."""
    try:
        if v is None:
            return default
        f = float(v)
        if f != f:  # NaN
            return default
        return int(f)
    except (TypeError, ValueError):
        return default


def _as_float(v, default=0.0):
    """Best-effort float coercion; NaN/missing/garbage -> default."""
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


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


def resolve_ref_file(category: str):
    """Locate the reference item for a category, per the experiment spec.

    Modes:
      * folder_match (default): match a file in ref_dir by the category's
        display text prefix, else by a substring of the category name.
      * shared: one reference file shared by every category
        (`reference.file`, resolved under ref_dir when relative).
      * none: no reference (candidate-only A/B tests).
    """
    ref = EXPERIMENT.get("reference") or {}
    mode = ref.get("mode", "folder_match")
    if mode == "none":
        return None
    rdir = ref_dir()
    if mode == "shared":
        fn = ref.get("file")
        if not fn:
            return None
        p = Path(fn) if Path(fn).is_absolute() else (rdir / fn)
        return p if p.exists() else None
    if not rdir.exists():
        return None
    display = MAQAM_ARABIC.get(category, "")
    candidates = [f for f in rdir.iterdir() if f.is_file()]
    if display:
        for f in candidates:
            if f.name.startswith(display):
                return f
    for f in candidates:
        if category.lower() in f.name.lower():
            return f
    return None


# --------------------------------------------------------------------------
# Ranking data
# --------------------------------------------------------------------------


def _canonicalize(df):
    """Add canonical columns (`rank`, `filename`, `file`, `similarity`, and an
    optional `item_id`) sourced from the experiment's configured column names,
    so downstream code is independent of the CSV's own headers."""
    cols = _columns()

    def col(key):
        v = cols.get(key)
        return v.strip().lower() if isinstance(v, str) and v.strip() else None

    name_c, path_c, rank_c, score_c, id_c = (
        col("name"), col("path"), col("rank"), col("score"), col("id")
    )

    if name_c and name_c in df.columns:
        df = df.copy()
        df["filename"] = df[name_c].astype("string").fillna("")
    elif path_c and path_c in df.columns:
        df = df.copy()
        df["filename"] = df[path_c].astype("string").fillna("").map(
            lambda p: str(p).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        )
    elif "filename" not in df.columns:
        df = df.copy()
        df["filename"] = ""

    if path_c and path_c in df.columns:
        df = df.copy()
        df["file"] = df[path_c]
    elif "file" not in df.columns:
        df = df.copy()
        df["file"] = ""

    if rank_c and rank_c in df.columns:
        df = df.copy()
        df["rank"] = pd.to_numeric(df[rank_c], errors="coerce")
    elif "rank" not in df.columns:
        df = df.copy()
        df["rank"] = range(1, len(df) + 1)

    if score_c and score_c in df.columns:
        df = df.copy()
        df["similarity"] = pd.to_numeric(df[score_c], errors="coerce")
    elif "similarity" not in df.columns:
        df = df.copy()
        df["similarity"] = 0.0

    if id_c and id_c in df.columns:
        df = df.copy()
        df["item_id"] = df[id_c].astype("string").fillna("")
    return df


def _ranking_path(category: str, suffix: str) -> Path:
    return results_dir() / f"{category}_ranking{suffix}.csv"


def list_categories():
    rdir = results_dir()
    if not rdir.exists():
        return []
    rk = _ranking_cfg()
    marker_full = f"_ranking{rk.get('full_suffix', '')}"
    marker_sub = f"_ranking{rk.get('subset_suffix', '_top50')}"
    names = set()
    for f in rdir.glob(rk.get("glob", "*_ranking*.csv")):
        stem = f.stem
        for marker in (marker_sub, marker_full, "_ranking"):
            if marker and stem.endswith(marker):
                stem = stem[: -len(marker)]
                break
        if stem:
            names.add(stem)
    return sorted(names)


# Historical alias: a "maqam" is just the default experiment's category noun.
list_maqams = list_categories


def load_ranking(category: str, full: bool = False):
    rk = _ranking_cfg()
    subset = _ranking_path(category, rk.get("subset_suffix", "_top50"))
    full_csv = _ranking_path(category, rk.get("full_suffix", ""))
    target = full_csv if (full or not subset.exists()) else subset
    if not target.exists():
        return None
    df = pd.read_csv(target, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    return _canonicalize(df)


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

    # `maqam` kept for backward compatibility; `category` is the generic name.
    data["maqam"] = maqam
    data["category"] = maqam
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
    explicit = r.get("item_id") if hasattr(r, "get") else None
    if explicit is not None:
        s = str(explicit).strip()
        if s and s.lower() not in ("nan", "none"):
            return s
    return item_identity(r.get("filename"), r.get("file"))


def category_stats(name: str):
    """Per-category rating stats over the FULL ranking (ratings are keyed by
    per-take id, so a rating given in subset mode is still counted here)."""
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


# Historical alias.
maqam_stats = category_stats


def collect_stats():
    categories = [m for m in (category_stats(n) for n in list_categories()) if m]
    cand = sum(m["total"] for m in categories)
    rated = sum(m["rated"] for m in categories)
    hist = {k: sum(m["stars"][k] for m in categories) for k in range(1, 6)}
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
        "maqams": categories,
        "categories": categories,
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
    n = len(list_categories())
    return {
        "results_dir": str(rdir),
        "audio_root": str(adir),
        "ref_dir": str(refd),
        "results_exists": rdir.exists(),
        "audio_root_exists": adir.exists(),
        "ref_dir_exists": refd.exists(),
        "indexed_files": len(build_audio_index()),
        # `maqam_count` kept for backward compatibility.
        "maqam_count": n,
        "category_count": n,
        "experiment": EXPERIMENT,
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
@app.route("/api/categories")
def api_categories():
    categories = []
    for m in list_categories():
        df = load_ranking(m, full=False)
        categories.append(
            {
                "name": m,
                "arabic": MAQAM_ARABIC.get(m, ""),
                "count": len(df) if df is not None else 0,
                "has_ref": resolve_ref_file(m) is not None,
            }
        )
    return jsonify(
        {
            "maqams": categories,       # backward-compatible key
            "categories": categories,
            "experiment": EXPERIMENT,
            "config": _config_payload(),
        }
    )


@app.route("/api/maqam/<category>")
@app.route("/api/category/<category>")
def api_category(category):
    full = request.args.get("full") == "1"
    df = load_ranking(category, full=full)
    if df is None:
        abort(404, f"No ranking CSV found for category '{category}'")

    ratings = load_ratings(category)

    rows = []
    for _, r in df.iterrows():
        iid = _row_id(r)
        rank = _as_int(r.get("rank"))
        if not iid or rank is None:
            continue  # cannot present an unranked/unidentifiable row
        local = resolve_audio(iid)
        filename = _row_filename(r)
        rows.append(
            {
                "id": iid,
                "rank": rank,
                "filename": filename,
                "similarity": _as_float(r.get("similarity"), 0.0),
                "found": local is not None,
                "stars": ratings.get(iid, {}).get("stars"),
            }
        )

    return jsonify(
        {
            "maqam": category,          # backward-compatible key
            "category": category,
            "arabic": MAQAM_ARABIC.get(category, ""),
            "has_ref": resolve_ref_file(category) is not None,
            "total": len(rows),
            "rated_count": len(ratings),
            "rows": rows,
        }
    )


@app.route("/api/stats")
def api_stats():
    return jsonify(collect_stats())


@app.route("/api/maqam/<category>/rating", methods=["POST"])
@app.route("/api/category/<category>/rating", methods=["POST"])
def api_set_rating(category):
    """Set or clear a star rating (1-5, or null/0 to clear) for one take.

    The payload should carry the per-take `id` (e.g. 'majnoon_layla_18082026/
    song.mp3'). A legacy bare `filename` is also accepted when it uniquely
    identifies one take; ambiguous names are rejected so the caller must
    re-rate each take explicitly.
    """
    data = request.get_json(force=True, silent=True) or {}
    item_id = str(data.get("id") or "").strip()
    filename = str(data.get("filename") or "").strip()
    stars_raw = data.get("stars")

    if not item_id:
        if not filename:
            abort(400, "id (or a unique filename) is required")
        ids = _basename_to_ids(category).get(filename)
        if not ids:
            abort(400, f"'{filename}' does not appear in the '{category}' ranking")
        if len(ids) > 1:
            abort(
                400,
                f"'{filename}' names multiple takes in '{category}'; "
                "resend with the per-take id "
                f"({', '.join(sorted(ids))})",
            )
        item_id = next(iter(ids))

    stars = _as_int(stars_raw)
    if stars is not None and stars != 0 and not (1 <= stars <= 5):
        abort(400, "stars must be an integer 1-5, or null/0 to clear")

    stars = stars if stars else None
    save_rating(category, item_id, stars)

    ratings = load_ratings(category)
    return jsonify({"id": item_id, "stars": stars, "rated_count": len(ratings)})


@app.route("/refresh-index")
def refresh_index():
    idx = build_audio_index(force=True)
    return jsonify({"indexed_files": len(idx), "audio_root": str(audio_root())})


# --------------------------------------------------------------------------
# Audio streaming
# --------------------------------------------------------------------------


@app.route("/audio/ref/<category>")
def audio_ref(category):
    f = resolve_ref_file(category)
    if not f or not f.exists():
        abort(404)
    return send_file(f)


@app.route("/audio/track/<category>/<int:rank>")
def audio_track(category, rank):
    full = request.args.get("full") == "1"
    df = load_ranking(category, full=full)
    if df is None:
        abort(404)
    match = df[df["rank"] == rank]
    if match.empty:
        abort(404)
    row = match.iloc[0]
    local = resolve_audio(_row_id(row))
    if not local or not Path(local).exists():
        abort(404, f"Local audio file not found for rank {rank} in '{category}'")
    return send_file(local)


if __name__ == "__main__":
    print(f"[startup] results_dir = {results_dir()}")
    print(f"[startup] audio_root  = {audio_root()}")
    print(f"[startup] ref_dir     = {ref_dir()}")
    build_audio_index()
    print(f"[startup] indexed {len(_audio_rel)} audio files under audio_root")
    app.run(debug=True, port=5000)
