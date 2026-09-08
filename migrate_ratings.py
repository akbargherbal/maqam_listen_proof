#!/usr/bin/env python3
"""One-off migration of basename-keyed rating files to per-take identities.

Ratings were historically keyed by a bare basename, which conflates distinct
takes that share a filename across run folders (e.g. the same generated track
in majnoon_layla_18082026 vs majnoon_layla_19082026). This rewrites each
results_dir/ratings/<maqam>.json so its "ratings" map is keyed by the
per-take identity "<run folder>/<filename>":

  * a basename that names exactly one take   -> carried over, same rating
  * a basename that names several takes      -> ambiguous; moved to an
    "unresolved_legacy" section so it is NOT lost, but excluded from the
    active view (those takes need to be re-rated individually)
  * an already-migrated identity             -> left untouched

Nothing is deleted: the original file is only rewritten after a .bak copy.

Usage:
    python migrate_ratings.py                 # migrate whatever results_dir points to
    MAQAM_RESULTS_DIR=/path/to/results python migrate_ratings.py
"""

import json
import os
import shutil
import sys

import app


def migrate_file(maqam):
    p = app.ratings_path(maqam)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [skip] {maqam}: unreadable ({e})")
        return None
    raw = data.get("ratings", {})
    if not isinstance(raw, dict):
        print(f"  [skip] {maqam}: 'ratings' is not an object")
        return None

    m = app._basename_to_ids(maqam)
    known = {i for ids in m.values() for i in ids}

    new = {}
    unresolved = {}
    carried = 0
    for key, val in raw.items():
        if key in known:
            new[key] = val
            continue
        ids = m.get(key)
        if ids and len(ids) == 1:
            new[next(iter(ids))] = val
            carried += 1
        elif key not in m:
            new[key] = val  # not in this ranking anymore; preserve as-is
        else:
            unresolved[key] = val  # ambiguous: keep for the record, exclude

    ambiguous = len(unresolved)
    if carried == 0 and ambiguous == 0:
        print(f"  {maqam}: already migrated ({len(new)} ratings)")
        return None

    bak = str(p) + ".bak"
    shutil.copyfile(str(p), bak)
    data["maqam"] = maqam
    data["ratings"] = new
    if unresolved:
        data["unresolved_legacy"] = unresolved
    data["migration"] = {"carried_over": carried, "ambiguous": ambiguous}
    data["updated"] = app._now_iso()
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"  {maqam}: {len(raw)} keys -> {len(new)} active "
        f"(carried {carried}, ambiguous {ambiguous}, backup at {bak})"
    )
    return {"maqam": maqam, "carried": carried, "ambiguous": ambiguous}


def main():
    results = app.results_dir()
    print(f"Migrating ratings under {results}")
    totals = {"carried": 0, "ambiguous": 0}
    for maqam in app.list_maqams():
        res = migrate_file(maqam)
        if res:
            totals["carried"] += res["carried"]
            totals["ambiguous"] += res["ambiguous"]
    print(
        f"Done. Carried over {totals['carried']} ratings; "
        f"{totals['ambiguous']} ambiguous ratings left for re-rating."
    )


if __name__ == "__main__":
    sys.exit(main())
