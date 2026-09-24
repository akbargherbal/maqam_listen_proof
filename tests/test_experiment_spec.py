"""Tests for the generic, spec-driven A/B testing layer.

These prove the app is no longer tied to the maqam domain: an experiment spec
can rename the vocabulary, remap arbitrary CSV columns, redefine the score
bands/precision, disable or share a reference, and expose generic API routes,
all without touching Python. The legacy maqam route/env names must keep
working alongside the generic ones.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# A non-maqam CSV: custom column names, no explicit rank, a 0-100 score.
MODEL_CSV = """variant,path,score
take01.wav,/content/model_runs/run_v1/take01.wav,91.2
take01.wav,/content/model_runs/run_v2/take01.wav,88.4
take02.wav,/content/model_runs/run_v1/take02.wav,64.3
"""

# A deliberately messy CSV: a non-numeric score and a row missing its rank
# must not blow up the endpoint.
MESSY_CSV = """rank,filename,similarity,file
1,good.mp3,0.9000,/content/runs/run_a/good.mp3
not-a-number,bad.mp3,oops,/content/runs/run_a/bad.mp3
"""

EXPERIMENT = {
    "id": "example_models",
    "title": "Voice Model A/B",
    "route_prefix": "model",
    "labels": {"singular": "prompt", "plural": "prompts"},
    "rtl": False,
    "columns": {"rank": None, "name": "variant", "score": "score", "path": "path", "id": None},
    "score": {
        "direction": "desc",
        "decimals": 1,
        "bands": [
            {"id": "hi", "label": "Strong", "qualitative": "Strong candidate", "min": 80, "max": 101},
            {"id": "lo", "label": "Weak", "qualitative": "Weak candidate", "min": 0, "max": 80},
        ],
    },
    "ranking": {"glob": "*_ranking*.csv", "full_suffix": "", "subset_suffix": "_top50", "subset_label": "Top 5"},
    "reference": {"mode": "none", "file": None},
}


@pytest.fixture()
def spec_app(tmp_path, monkeypatch):
    """Reload app.py under a custom experiment spec + isolated data dirs."""
    exp_path = tmp_path / "example_models.json"
    exp_path.write_text(json.dumps(EXPERIMENT), encoding="utf-8")

    results = tmp_path / "results"
    audio = tmp_path / "audio"
    ref = tmp_path / "ref"
    results.mkdir()
    audio.mkdir()
    ref.mkdir()
    (results / "promptA_ranking.csv").write_text(MODEL_CSV, encoding="utf-8")
    run_v1 = audio / "run_v1"
    run_v2 = audio / "run_v2"
    run_v1.mkdir()
    run_v2.mkdir()
    (run_v1 / "take01.wav").write_bytes(b"take-a")
    (run_v1 / "take02.wav").write_bytes(b"take-b")
    (run_v2 / "take01.wav").write_bytes(b"take-c")

    monkeypatch.setenv("AB_EXPERIMENT_FILE", str(exp_path))
    monkeypatch.setenv("AB_RESULTS_DIR", str(results))
    monkeypatch.setenv("AB_AUDIO_ROOT", str(audio))
    monkeypatch.setenv("AB_REF_DIR", str(ref))

    import app as app_mod

    importlib.reload(app_mod)
    app_mod.app.config.update(TESTING=True)
    monkeypatch.setattr(app_mod, "CONFIG_PATH", tmp_path / "config.json")
    app_mod.build_audio_index(force=True)
    return app_mod


@pytest.fixture()
def spec_client(spec_app):
    return spec_app.app.test_client()


class TestCustomColumns:
    def test_columns_remapped_and_rank_inferred(self, spec_app):
        df = spec_app.load_ranking("promptA")
        assert list(df["rank"]) == [1, 2, 3]
        assert list(df["filename"]) == ["take01.wav", "take01.wav", "take02.wav"]
        assert list(df["similarity"]) == [91.2, 88.4, 64.3]

    def test_identity_from_configured_path_column(self, spec_app):
        df = spec_app.load_ranking("promptA")
        ids = [spec_app._row_id(r) for _, r in df.iterrows()]
        assert ids == ["run_v1/take01.wav", "run_v2/take01.wav", "run_v1/take02.wav"]


class TestScoreSpec:
    def test_config_exposes_custom_score_bands_and_precision(self, spec_client):
        exp = spec_client.get("/api/config").get_json()["experiment"]
        assert exp["id"] == "example_models"
        assert exp["labels"]["singular"] == "prompt"
        assert exp["score"]["decimals"] == 1
        assert [b["id"] for b in exp["score"]["bands"]] == ["hi", "lo"]


class TestReferenceModes:
    def test_none_mode_means_no_reference(self, spec_app):
        assert spec_app.resolve_ref_file("promptA") is None
        detail = spec_app.app.test_client().get("/api/category/promptA").get_json()
        assert detail["has_ref"] is False

    def test_shared_mode_uses_configured_file(self, tmp_path, monkeypatch):
        exp = dict(EXPERIMENT)
        exp["reference"] = {"mode": "shared", "file": "shared_ref.wav"}
        exp_path = tmp_path / "shared.json"
        exp_path.write_text(json.dumps(exp), encoding="utf-8")
        ref = tmp_path / "ref"
        ref.mkdir()
        (ref / "shared_ref.wav").write_bytes(b"ref")
        monkeypatch.setenv("AB_EXPERIMENT_FILE", str(exp_path))
        monkeypatch.setenv("AB_REF_DIR", str(ref))

        import app as app_mod

        importlib.reload(app_mod)
        monkeypatch.setattr(app_mod, "CONFIG_PATH", tmp_path / "config.json")
        found = app_mod.resolve_ref_file("anything")
        assert found is not None
        assert found.name == "shared_ref.wav"


class TestGenericRoutes:
    def test_categories_and_category_detail(self, spec_client):
        cats = spec_client.get("/api/categories").get_json()
        assert {c["name"] for c in cats["categories"]} == {"promptA"}
        assert cats["experiment"]["labels"]["plural"] == "prompts"

        detail = spec_client.get("/api/category/promptA").get_json()
        assert detail["category"] == "promptA"
        assert detail["total"] == 3
        assert detail["rows"][0]["similarity"] == pytest.approx(91.2)

    def test_generic_rating_route(self, spec_client):
        resp = spec_client.post(
            "/api/category/promptA/rating",
            data=json.dumps({"id": "run_v1/take01.wav", "stars": 5}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["stars"] == 5
        rows = spec_client.get("/api/category/promptA").get_json()["rows"]
        by_id = {r["id"]: r["stars"] for r in rows}
        assert by_id["run_v1/take01.wav"] == 5

    def test_legacy_maqam_aliases_still_work(self, spec_client):
        # Same data must be reachable through the historical route names.
        assert spec_client.get("/api/maqams").status_code == 200
        assert spec_client.get("/api/maqam/promptA").status_code == 200
        resp = spec_client.post(
            "/api/maqam/promptA/rating",
            data=json.dumps({"id": "run_v1/take02.wav", "stars": 3}),
            content_type="application/json",
        )
        assert resp.status_code == 200


class TestDefensiveParsing:
    def test_malformed_cells_do_not_500(self, tmp_path, monkeypatch):
        exp_path = tmp_path / "e.json"
        exp_path.write_text(json.dumps(EXPERIMENT), encoding="utf-8")
        results = tmp_path / "results"
        results.mkdir()
        (results / "promptA_ranking.csv").write_text(MESSY_CSV, encoding="utf-8")
        monkeypatch.setenv("AB_EXPERIMENT_FILE", str(exp_path))
        monkeypatch.setenv("AB_RESULTS_DIR", str(results))

        import app as app_mod

        importlib.reload(app_mod)
        app_mod.app.config.update(TESTING=True)
        monkeypatch.setattr(app_mod, "CONFIG_PATH", tmp_path / "config.json")

        resp = app_mod.app.test_client().get("/api/category/promptA")
        assert resp.status_code == 200
        rows = resp.get_json()["rows"]
        # The row with a non-integer rank is dropped, not fatal.
        assert all(isinstance(r["rank"], int) for r in rows)
        # The bad score cell coerces to 0.0 instead of raising.
        bad = [r for r in rows if r["filename"] == "bad.mp3"]
        assert not bad  # dropped because its rank is unparseable


class TestEnvPrecedence:
    def test_ab_env_beats_maqam_env(self, app_module, tmp_path, monkeypatch):
        monkeypatch.setenv("MAQAM_RESULTS_DIR", "from_maqam")
        monkeypatch.setenv("AB_RESULTS_DIR", "from_ab")
        cfg = app_module.load_config()
        assert cfg["results_dir"] == "from_ab"

    def test_maqam_env_still_honored(self, app_module, monkeypatch):
        monkeypatch.delenv("AB_RESULTS_DIR", raising=False)
        monkeypatch.setenv("MAQAM_RESULTS_DIR", "from_maqam")
        cfg = app_module.load_config()
        assert cfg["results_dir"] == "from_maqam"
