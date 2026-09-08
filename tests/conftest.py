"""Shared pytest fixtures for the Flask backend (app.py)."""

import importlib
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HIJAZ_TOP50_CSV = """rank,filename,similarity,file
1,track_a.mp3,0.9123,/content/SUNO_BACKUP_11082026/run_antara/track_a.mp3
2,track_b.mp3,0.8501,/content/SUNO_BACKUP_11082026/run_majnoon/track_b.mp3
3,missing_on_disk.mp3,0.7000,/content/SUNO_BACKUP_11082026/run_missing/missing_on_disk.mp3
"""

# ajam rows deliberately put TWO different takes under the same run folder to
# prove resolution is per-row (run folder + filename), never basename alone.
AJAM_FULL_CSV = """rank,filename,similarity,file
1,ajam_track_one.mp3,0.8800,D:\\some\\windows\\path\\run_ajam\\ajam_track_one.mp3
2,ajam_track_two.mp3,0.8100,D:\\some\\windows\\path\\run_ajam\\ajam_track_two.mp3
"""


@pytest.fixture()
def app_module(tmp_path, monkeypatch):
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config.update(TESTING=True)
    # Redirect config.json writes to an isolated tmp file so tests never
    # touch the real repo-root config.json (this previously caused a real
    # POST /api/settings test to permanently overwrite the developer's
    # actual folder settings on disk).
    monkeypatch.setattr(app_mod, "CONFIG_PATH", tmp_path / "config.json")
    yield app_mod


@pytest.fixture()
def data_dirs(tmp_path):
    results = tmp_path / "results"
    audio = tmp_path / "audio_root"
    ref = tmp_path / "ref"
    results.mkdir()
    audio.mkdir()
    ref.mkdir()

    (results / "hijaz_ranking.csv").write_text(HIJAZ_TOP50_CSV, encoding="utf-8")
    (results / "hijaz_ranking_top50.csv").write_text(HIJAZ_TOP50_CSV, encoding="utf-8")
    (results / "ajam_ranking.csv").write_text(AJAM_FULL_CSV, encoding="utf-8")

    # Mirror the real layout: audio_root/<run folder>/<file>. Two DIFFERENT
    # files can share a basename across folders (that is the bug under test);
    # here each folder has distinct names so per-take ids are unambiguous.
    run_antara = audio / "run_antara"
    run_majnoon = audio / "run_majnoon"
    run_ajam = audio / "run_ajam"
    run_antara.mkdir()
    run_majnoon.mkdir()
    run_ajam.mkdir()
    (run_antara / "track_a.mp3").write_bytes(b"fake-mp3-bytes-a")
    (run_majnoon / "track_b.mp3").write_bytes(b"fake-mp3-bytes-b")
    (run_ajam / "ajam_track_one.mp3").write_bytes(b"fake-mp3-bytes-c")
    (run_ajam / "ajam_track_two.mp3").write_bytes(b"fake-mp3-bytes-d")

    (ref / "حجاز_reference_track.mp3").write_bytes(b"fake-ref-hijaz")
    (ref / "some_ajam_reference.mp3").write_bytes(b"fake-ref-ajam")

    return {"results": results, "audio": audio, "ref": ref}


@pytest.fixture()
def configured_app(app_module, data_dirs):
    app_module.CONFIG["results_dir"] = str(data_dirs["results"])
    app_module.CONFIG["audio_root"] = str(data_dirs["audio"])
    app_module.CONFIG["ref_dir"] = str(data_dirs["ref"])
    app_module.build_audio_index(force=True)
    return app_module


DUP_CSV = """rank,filename,similarity,file
1,same_song.mp3,0.9123,/content/SUNO_BACKUP_11082026/run_old/same_song.mp3
2,same_song.mp3,0.8401,/content/SUNO_BACKUP_11082026/run_new/same_song.mp3
3,only_old.mp3,0.7000,/content/SUNO_BACKUP_11082026/run_old/only_old.mp3
"""


@pytest.fixture()
def dup_app(app_module, tmp_path):
    """Fixture for the duplicate-basename bug: the SAME basename (same_song.mp3)
    exists in two run folders as two distinct takes, ranked independently."""
    results = tmp_path / "results"
    audio = tmp_path / "audio"
    ref = tmp_path / "ref"
    results.mkdir()
    audio.mkdir()
    ref.mkdir()
    (results / "hijaz_ranking.csv").write_text(DUP_CSV, encoding="utf-8")
    (results / "hijaz_ranking_top50.csv").write_text(DUP_CSV, encoding="utf-8")
    run_old = audio / "run_old"
    run_new = audio / "run_new"
    run_old.mkdir()
    run_new.mkdir()
    (run_old / "same_song.mp3").write_bytes(b"fake-old-take")
    (run_new / "same_song.mp3").write_bytes(b"fake-new-take")
    (run_old / "only_old.mp3").write_bytes(b"fake-only-old")

    app_module.CONFIG["results_dir"] = str(results)
    app_module.CONFIG["audio_root"] = str(audio)
    app_module.CONFIG["ref_dir"] = str(ref)
    app_module.build_audio_index(force=True)
    return app_module


@pytest.fixture()
def dup_client(dup_app):
    return dup_app.app.test_client()


@pytest.fixture()
def client(configured_app):
    return configured_app.app.test_client()
