"""Shared pytest fixtures for the Flask backend (app.py)."""

import importlib
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HIJAZ_TOP50_CSV = """rank,filename,similarity,file
1,track_a.mp3,0.9123,/content/foreign/machine/path/track_a.mp3
2,track_b.mp3,0.8501,/content/foreign/machine/path/track_b.mp3
3,missing_on_disk.mp3,0.7000,/content/foreign/machine/path/missing_on_disk.mp3
"""

AJAM_FULL_CSV = """rank,filename,similarity,file
1,ajam_track_one.mp3,0.8800,D:\\some\\windows\\path\\ajam_track_one.mp3
2,ajam_track_two.mp3,0.8100,D:\\some\\windows\\path\\ajam_track_two.mp3
"""


@pytest.fixture()
def app_module():
    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config.update(TESTING=True)
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

    nested = audio / "some_album_folder"
    nested.mkdir()
    (nested / "track_a.mp3").write_bytes(b"fake-mp3-bytes-a")
    (audio / "track_b.mp3").write_bytes(b"fake-mp3-bytes-b")
    (audio / "ajam_track_one.mp3").write_bytes(b"fake-mp3-bytes-c")
    (audio / "ajam_track_two.mp3").write_bytes(b"fake-mp3-bytes-d")

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


@pytest.fixture()
def client(configured_app):
    return configured_app.app.test_client()
