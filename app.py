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
# Filename index (the real fix for "links break when paths change")
# --------------------------------------------------------------------------

_audio_index = {}
_index_root_used = None


def build_audio_index(force=False):
    global _audio_index, _index_root_used
    root = audio_root()
    if _audio_index and not force and _index_root_used == root:
        return _audio_index
    index = {}
    if root.exists():
        for r, _dirs, files in os.walk(root):
            for fn in files:
                if fn.lower().endswith(AUDIO_EXTS):
                    index.setdefault(fn, str(Path(r) / fn))  # first match wins
    _audio_index = index
    _index_root_used = root
    return index


def resolve_audio_file(csv_path_value: str):
    """Map a (possibly foreign-machine) CSV path to a real local file by filename."""
    if not csv_path_value:
        return None
    filename = Path(str(csv_path_value).replace("\\", "/")).name
    return build_audio_index().get(filename)


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
    return sorted(
        f.stem.replace("_ranking", "") for f in rdir.glob("*_ranking.csv")
    )


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
            f"{letter}:\\" for letter in string.ascii_uppercase
            if os.path.exists(f"{letter}:\\")
        ]

    return jsonify({
        "path": str(p),
        "parent": str(p.parent) if p.parent != p else None,
        "dirs": dirs,
        "drives": drives,
    })


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

    rows = []
    for _, r in df.iterrows():
        csv_path = str(r.get("file") or r.get("filename") or "")
        local = resolve_audio_file(csv_path)
        rows.append(
            {
                "rank": int(r.get("rank")),
                "filename": str(r.get("filename", Path(csv_path).name)),
                "similarity": float(r.get("similarity", 0.0)),
                "found": local is not None,
            }
        )

    return jsonify(
        {
            "maqam": maqam,
            "arabic": MAQAM_ARABIC.get(maqam, ""),
            "has_ref": resolve_ref_file(maqam) is not None,
            "total": len(rows),
            "rows": rows,
        }
    )


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
    csv_path = str(match.iloc[0].get("file") or match.iloc[0].get("filename") or "")
    local = resolve_audio_file(csv_path)
    if not local or not Path(local).exists():
        abort(404, f"Local audio file not found for rank {rank} in '{maqam}'")
    return send_file(local)


if __name__ == "__main__":
    print(f"[startup] results_dir = {results_dir()}")
    print(f"[startup] audio_root  = {audio_root()}")
    print(f"[startup] ref_dir     = {ref_dir()}")
    build_audio_index()
    print(f"[startup] indexed {len(_audio_index)} audio files under audio_root")
    app.run(debug=True, port=5000)
