#!/usr/bin/env python3
"""Export rated candidate audio files that meet criteria to a folder.

Copies the actual audio files (from `audio_root`) for every take whose rating
passes the filters, organised by category. Takes are identified per-category
by their per-take id "<run folder>/<filename>" (the format the app now
writes), so two takes that share a basename across run folders are exported
independently.

Usage:
    python export_rated_music.py /path/to/ratings --min-stars 4 -o /out/folder
    python export_rated_music.py /path/to/results_dir -o /out/folder --category hijaz --category kurd
    python export_rated_music.py /path/to/ratings -a /data/audio -o /out/folder --flat --dry-run

`--maqam` is accepted as an alias for `--category`, and the CSV column names /
ranking-file suffixes come from the same experiment spec as app.py (inline
`experiment` in config.json and/or experiments/<id>.json via AB_EXPERIMENT).

`RATINGS` (first positional) may be either:
  * the ratings folder itself (contains <category>.json files), or
  * a results dir (contains the ranking CSVs *and* a `ratings/` subfolder).

The audio folder is resolved from, in order: `--audio-root`, the
AB_AUDIO_ROOT / MAQAM_AUDIO_ROOT env var, then `audio_root` in ./config.json
(paths in config.json are resolved relative to this script's folder when
relative).

Legacy (pre-migration) rating files keyed by bare basename are handled too:
the basename is resolved through that category's ranking CSV when one is
findable, otherwise by a unique basename match under audio_root. Basenames
that are still ambiguous are skipped and reported.

If a take's source folder (its run folder under `audio_root`) contains a
`workspace_manifest.json`, it is copied alongside the exported take(s) into
the same destination folder (once per destination folder, not once per
take). Pass `--no-manifest` to skip this. When `--flat` mixes takes from
different run folders into one destination folder, later manifests are
saved as `<run folder>__workspace_manifest.json` instead of overwriting the
first one.
"""

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
MANIFEST_NAME = "workspace_manifest.json"

DEFAULT_COLUMNS = {"rank": "rank", "name": "filename", "score": "similarity", "path": "file"}
DEFAULT_RANKING = {"full_suffix": "", "subset_suffix": "_top50"}


def _resolve_path(value, base=None):
    value = os.path.expandvars(os.path.expanduser(str(value)))
    p = Path(value)
    if not p.is_absolute() and base is not None:
        p = Path(base) / p
    return p


def _read_experiment():
    """Resolve the experiment spec the same way app.py does (defaults < preset
    file < inline config), so column/ranking names stay in sync. Never raises."""
    exp = {}
    exp_id = os.environ.get("AB_EXPERIMENT")
    exp_file = os.environ.get("AB_EXPERIMENT_FILE")
    preset = None
    if exp_file:
        preset = _resolve_path(exp_file)
    elif exp_id:
        preset = APP_DIR / "experiments" / f"{exp_id}.json"
    if preset is not None and preset.exists():
        try:
            exp = json.loads(preset.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            exp = {}
    cfg = APP_DIR / "config.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            inline = data.get("experiment") if isinstance(data.get("experiment"), dict) else {}
            merged = dict(exp)
            merged.update(inline)
            exp = merged
        except (OSError, ValueError):
            pass
    return exp


def experiment_columns():
    exp = _read_experiment()
    cols = dict(DEFAULT_COLUMNS)
    if isinstance(exp.get("columns"), dict):
        for k, v in exp["columns"].items():
            if isinstance(v, str) and v.strip():
                cols[k] = v.strip().lower()
    return cols


def experiment_ranking():
    exp = _read_experiment()
    rk = dict(DEFAULT_RANKING)
    if isinstance(exp.get("ranking"), dict):
        for k in ("full_suffix", "subset_suffix"):
            if isinstance(exp["ranking"].get(k), str):
                rk[k] = exp["ranking"][k]
    return rk


def audio_root_default():
    for env in ("AB_AUDIO_ROOT", "MAQAM_AUDIO_ROOT"):
        if os.environ.get(env):
            return _resolve_path(os.environ[env])
    cfg = APP_DIR / "config.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if data.get("audio_root"):
                return _resolve_path(data["audio_root"], base=APP_DIR)
        except (OSError, ValueError):
            pass
    return None


def discover(data_dir):
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        sys.exit(f"error: not a directory: {data_dir}")
    ratings_dir = data_dir / "ratings"
    if ratings_dir.is_dir():
        return ratings_dir, data_dir
    if any(p.suffix.lower() == ".json" for p in data_dir.iterdir()):
        return data_dir, data_dir.parent
    sys.exit("error: no <category>.json rating files found at the given path")


def rating_files(ratings_dir):
    files = []
    for p in sorted(ratings_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ratings = data.get("ratings") if isinstance(data, dict) else None
        if isinstance(ratings, dict) and ratings:
            files.append((p.stem, ratings))
    return files


def find_ranking_csv(category, candidates, rk=None):
    rk = rk or experiment_ranking()
    suffixes = list(dict.fromkeys([rk["full_suffix"], rk["subset_suffix"], "_full"]))
    names = [f"{category}_ranking{s}.csv" for s in suffixes]
    for cand in candidates:
        if cand is None:
            continue
        base = Path(cand)
        for name in names:
            p = base / name
            if p.exists():
                return p
    return None


def load_ranking_index(csv_path, cols=None):
    """Return (ids, basename->set(ids)) from a ranking CSV."""
    cols = cols or experiment_columns()
    name_col = cols.get("name", "filename")
    path_col = cols.get("path", "file")
    ids = set()
    base_to_ids = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return ids, base_to_ids
        fields = [f.strip().lower() for f in reader.fieldnames]
        for row in reader:
            rec = {fields[i]: (list(row.values())[i] or "").strip() for i in range(len(fields))}
            fname = rec.get(name_col, "").strip()
            fpath = rec.get(path_col, "").strip()
            if fname:
                folder = os.path.basename(os.path.dirname(fpath)) if fpath else ""
                take_id = f"{folder}/{fname}" if folder else fname
                ids.add(take_id)
                base_to_ids.setdefault(fname, set()).add(take_id)
    return ids, base_to_ids


class AudioRoot:
    def __init__(self, root):
        self.root = Path(root)
        self.rels = []
        if self.root.is_dir():
            for dirpath, _dirnames, filenames in os.walk(self.root):
                for name in filenames:
                    full = Path(dirpath) / name
                    self.rels.append(full.relative_to(self.root).as_posix())

    def resolve_id(self, take_id):
        """take_id is '<run>/<file>' (or a bare name) -> absolute path or None."""
        cand = self.root / take_id.replace("/", os.sep)
        if cand.is_file():
            return cand
        low = take_id.lower()
        for rel in self.rels:
            if rel.lower() == low:
                return self.root / rel.replace("/", os.sep)
        return None

    def resolve_basename(self, name):
        matches = [rel for rel in self.rels if os.path.basename(rel).lower() == name.lower()]
        if len(matches) == 1:
            return self.root / matches[0].replace("/", os.sep)
        return None  # None if zero or >1 (ambiguous)


def stars_of(val):
    if isinstance(val, dict):
        s = val.get("stars")
    else:
        s = val
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="export_rated_music",
        description="Copy rated candidate audio files that meet criteria to a folder.",
    )
    ap.add_argument("ratings", help="ratings folder or results dir (with ratings/ + ranking CSVs)")
    ap.add_argument("-o", "--out", required=True, help="destination folder (created if needed)")
    ap.add_argument("-a", "--audio-root", default=None,
                    help="folder tree containing the takes (default: config.json / env MAQAM_AUDIO_ROOT)")
    ap.add_argument("--min-stars", type=int, default=None, help="only export ratings >= N stars")
    ap.add_argument("--max-stars", type=int, default=None, help="only export ratings <= N stars")
    ap.add_argument("--category", "--maqam", dest="categories", action="append", default=None,
                    help="restrict to a category (repeatable; --maqam is an alias)")
    ap.add_argument("--ranking-dir", default=None, help="folder with <category>_ranking CSVs (default: auto)")
    ap.add_argument("--flat", action="store_true", help="drop run-folder level (out/<category>/<file>)")
    ap.add_argument("--no-category-folders", "--no-maqam-folders", dest="no_category_folders",
                    action="store_true", help="drop per-category level in the output")
    ap.add_argument("--dry-run", action="store_true", help="only print what would be copied")
    ap.add_argument("--no-manifest", action="store_true",
                    help="don't copy each take's workspace_manifest.json alongside it")
    args = ap.parse_args(argv)

    ratings_dir, ranking_hint = discover(args.ratings)

    audio_root = _resolve_path(args.audio_root) if args.audio_root else audio_root_default()
    if audio_root is None:
        sys.exit("error: could not determine audio_root; pass --audio-root or set AB_AUDIO_ROOT / MAQAM_AUDIO_ROOT")
    audio = AudioRoot(audio_root)
    out_root = _resolve_path(args.out)

    cols = experiment_columns()
    rk = experiment_ranking()

    csv_candidates = [Path(args.ranking_dir)] if args.ranking_dir else []
    if ranking_hint is not None:
        csv_candidates.append(ranking_hint)
    csv_candidates.append(ratings_dir)
    default_results = audio_root_default_cfg_results()
    if default_results is not None:
        csv_candidates.append(default_results)

    plan = []
    skipped = []
    for category, ratings in rating_files(ratings_dir):
        if args.categories and category not in args.categories:
            continue
        csv_path = find_ranking_csv(category, csv_candidates, rk)
        _, base_to_ids = load_ranking_index(csv_path, cols) if csv_path else (None, None)
        for key, val in sorted(ratings.items()):
            stars = stars_of(val)
            if stars is None or (args.min_stars is not None and stars < args.min_stars) \
                    or (args.max_stars is not None and stars > args.max_stars):
                continue
            if "/" in key:
                plan.append((category, key, key, stars, audio.resolve_id(key)))
                continue
            if base_to_ids is not None and key not in base_to_ids:
                skipped.append((category, key, "not in that category's ranking"))
                continue
            if base_to_ids is not None:
                ids = sorted(base_to_ids[key])
                if len(ids) > 1:
                    skipped.append((category, key, f"ambiguous ({len(ids)} takes share this basename); re-rate by take id first"))
                    continue
                plan.append((category, ids[0], key, stars, audio.resolve_id(ids[0])))
                continue
            src = audio.resolve_basename(key)
            if src is None:
                matches = [r for r in audio.rels if os.path.basename(r).lower() == key.lower()]
                reason = "no audio file found" if not matches else f"ambiguous: {len(matches)} matching files under audio_root"
                skipped.append((category, key, reason))
                continue
            plan.append((category, key, key, stars, src))

    seen_names = {}
    manifest_dest_source = {}  # dest folder -> run folder whose manifest is already there
    manifest_handled = set()   # dest manifest paths already copied/announced
    copied = 0
    manifests_copied = 0
    for category, take_id, key, stars, src in plan:
        category_dir = None if args.no_category_folders else category
        if args.flat:
            rel = os.path.basename(take_id.replace("/", os.sep))
        else:
            rel = take_id.replace("/", os.sep)
        dest = out_root
        if category_dir:
            dest = dest / category_dir
        dest = dest / rel
        if args.flat:
            bucket = seen_names.setdefault(category_dir or "", set())
            if dest.name in bucket:
                run = os.path.dirname(take_id.replace("/", os.sep))
                dest = dest.with_name(f"{run}__{dest.name}")
            bucket.add(dest.name)
        if src is None or not src.is_file():
            skipped.append((category, key, f"audio missing at {src or '?'}"))
            continue
        if dest.exists() and dest.resolve() == src.resolve():
            skipped.append((category, key, "source is already at destination"))
            continue

        manifest_dest = None
        if not args.no_manifest:
            manifest_src = src.parent / MANIFEST_NAME
            if manifest_src.is_file():
                dest_dir = dest.parent
                # First take exported into a given destination folder decides
                # whose manifest lives there. If a later take in the same
                # folder comes from a different run (only possible with
                # --flat), give its manifest a prefixed name instead of
                # silently overwriting the first one.
                owner = manifest_dest_source.setdefault(dest_dir, src.parent)
                if owner == src.parent:
                    manifest_dest = dest_dir / MANIFEST_NAME
                else:
                    manifest_dest = dest_dir / f"{src.parent.name}__{MANIFEST_NAME}"

        if args.dry_run:
            print(f"would copy  {src}  ->  {dest}")
            if manifest_dest is not None and manifest_dest not in manifest_handled:
                print(f"would copy  {manifest_src}  ->  {manifest_dest}")
                manifest_handled.add(manifest_dest)
                manifests_copied += 1
            copied += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        copied += 1
        print(f"copied {stars}*  {category}: {take_id}  ->  {dest.relative_to(out_root)}")

        if manifest_dest is not None and manifest_dest not in manifest_handled:
            shutil.copy2(str(manifest_src), str(manifest_dest))
            manifest_handled.add(manifest_dest)
            manifests_copied += 1
            print(f"copied manifest         ->  {manifest_dest.relative_to(out_root)}")

    summary = f"\n{copied} file(s) exported to {out_root}"
    if manifests_copied:
        summary += f" ({manifests_copied} workspace_manifest.json also copied)"
    print(summary)
    for category, key, reason in skipped:
        print(f"  skipped [{category}] {key}: {reason}")
    if skipped:
        print(f"\n{len(skipped)} rating(s) were skipped (see above).")
    return 0 if copied or args.dry_run else 1


def audio_root_default_cfg_results():
    cfg = APP_DIR / "config.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            if data.get("results_dir"):
                return _resolve_path(data["results_dir"], base=APP_DIR)
        except (OSError, ValueError):
            pass
    return None


if __name__ == "__main__":
    sys.exit(main())
