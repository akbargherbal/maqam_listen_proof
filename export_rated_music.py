#!/usr/bin/env python3
"""Export rated candidate audio files that meet criteria to a folder.

Copies the actual audio files (from `audio_root`) for every take whose rating
passes the filters, organised by category. Takes are identified per-category
by their per-take id "<run folder>/<filename>" (the format the app now
writes), so two takes that share a basename across run folders are exported
independently.

Usage:
    python export_rated_music.py /path/to/ratings --min-stars 4 -o /out/folder
    python export_rated_music.py /path/to/results_dir -o /out/folder --maqam hijaz --maqam kurd
    python export_rated_music.py /path/to/ratings -a /data/audio -o /out/folder --flat --dry-run

`RATINGS` (first positional) may be either:
  * the ratings folder itself (contains <category>.json files), or
  * a results dir (contains the ranking CSVs *and* a `ratings/` subfolder).

The audio folder is resolved from, in order: `--audio-root`, the
MAQAM_AUDIO_ROOT env var, then `audio_root` in ./config.json (paths in
config.json are resolved relative to this script's folder when relative).

Legacy (pre-migration) rating files keyed by bare basename are handled too:
the basename is resolved through that category's ranking CSV when one is
findable, otherwise by a unique basename match under audio_root. Basenames
that are still ambiguous are skipped and reported.
"""

import argparse
import csv
import json
import os
import shutil
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def _resolve_path(value, base=None):
    value = os.path.expandvars(os.path.expanduser(str(value)))
    p = Path(value)
    if not p.is_absolute() and base is not None:
        p = Path(base) / p
    return p


def audio_root_default():
    if os.environ.get("MAQAM_AUDIO_ROOT"):
        return _resolve_path(os.environ["MAQAM_AUDIO_ROOT"])
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


def find_ranking_csv(maqam, candidates):
    names = (
        f"{maqam}_ranking.csv",
        f"{maqam}_ranking_full.csv",
        f"{maqam}_ranking_top50.csv",
    )
    for cand in candidates:
        if cand is None:
            continue
        base = Path(cand)
        for name in names:
            p = base / name
            if p.exists():
                return p
    return None


def load_ranking_index(csv_path):
    """Return (ids, basename->set(ids)) from a ranking CSV."""
    ids = set()
    base_to_ids = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return ids, base_to_ids
        fields = [f.strip().lower() for f in reader.fieldnames]
        for row in reader:
            rec = {fields[i]: (list(row.values())[i] or "").strip() for i in range(len(fields))}
            fname = rec.get("filename", "").strip()
            fpath = rec.get("file", "").strip()
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
    ap.add_argument("--maqam", action="append", default=None, help="restrict to a category (repeatable)")
    ap.add_argument("--ranking-dir", default=None, help="folder with <category>_ranking CSVs (default: auto)")
    ap.add_argument("--flat", action="store_true", help="drop run-folder level (out/<category>/<file>)")
    ap.add_argument("--no-maqam-folders", action="store_true", help="drop per-category level in the output")
    ap.add_argument("--dry-run", action="store_true", help="only print what would be copied")
    args = ap.parse_args(argv)

    ratings_dir, ranking_hint = discover(args.ratings)

    audio_root = _resolve_path(args.audio_root) if args.audio_root else audio_root_default()
    if audio_root is None:
        sys.exit("error: could not determine audio_root; pass --audio-root or set MAQAM_AUDIO_ROOT")
    audio = AudioRoot(audio_root)
    out_root = _resolve_path(args.out)

    csv_candidates = [Path(args.ranking_dir)] if args.ranking_dir else []
    if ranking_hint is not None:
        csv_candidates.append(ranking_hint)
    csv_candidates.append(ratings_dir)
    default_results = audio_root_default_cfg_results()
    if default_results is not None:
        csv_candidates.append(default_results)

    plan = []
    skipped = []
    for maqam, ratings in rating_files(ratings_dir):
        if args.maqam and maqam not in args.maqam:
            continue
        csv_path = find_ranking_csv(maqam, csv_candidates)
        _, base_to_ids = load_ranking_index(csv_path) if csv_path else (None, None)
        for key, val in sorted(ratings.items()):
            stars = stars_of(val)
            if stars is None or (args.min_stars is not None and stars < args.min_stars) \
                    or (args.max_stars is not None and stars > args.max_stars):
                continue
            if "/" in key:
                plan.append((maqam, key, key, stars, audio.resolve_id(key)))
                continue
            if base_to_ids is not None and key not in base_to_ids:
                skipped.append((maqam, key, "not in that category's ranking"))
                continue
            if base_to_ids is not None:
                ids = sorted(base_to_ids[key])
                if len(ids) > 1:
                    skipped.append((maqam, key, f"ambiguous ({len(ids)} takes share this basename); re-rate by take id first"))
                    continue
                plan.append((maqam, ids[0], key, stars, audio.resolve_id(ids[0])))
                continue
            src = audio.resolve_basename(key)
            if src is None:
                matches = [r for r in audio.rels if os.path.basename(r).lower() == key.lower()]
                reason = "no audio file found" if not matches else f"ambiguous: {len(matches)} matching files under audio_root"
                skipped.append((maqam, key, reason))
                continue
            plan.append((maqam, key, key, stars, src))

    seen_names = {}
    copied = 0
    for maqam, take_id, key, stars, src in plan:
        maqam_dir = None if args.no_maqam_folders else maqam
        if args.flat:
            rel = os.path.basename(take_id.replace("/", os.sep))
        else:
            rel = take_id.replace("/", os.sep)
        dest = out_root
        if maqam_dir:
            dest = dest / maqam_dir
        dest = dest / rel
        if args.flat:
            bucket = seen_names.setdefault(maqam_dir or "", set())
            if dest.name in bucket:
                run = os.path.dirname(take_id.replace("/", os.sep))
                dest = dest.with_name(f"{run}__{dest.name}")
            bucket.add(dest.name)
        if src is None or not src.is_file():
            skipped.append((maqam, key, f"audio missing at {src or '?'}"))
            continue
        if dest.exists() and dest.resolve() == src.resolve():
            skipped.append((maqam, key, "source is already at destination"))
            continue
        if args.dry_run:
            print(f"would copy  {src}  ->  {dest}")
            copied += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        copied += 1
        print(f"copied {stars}*  {maqam}: {take_id}  ->  {dest.relative_to(out_root)}")

    print(f"\n{copied} file(s) exported to {out_root}")
    for maqam, key, reason in skipped:
        print(f"  skipped [{maqam}] {key}: {reason}")
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
