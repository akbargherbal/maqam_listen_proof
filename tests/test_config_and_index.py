import json
import pytest


class TestLoadConfig:
    def test_defaults_used_when_file_missing(self, app_module, tmp_path, monkeypatch):
        monkeypatch.setattr(app_module, "CONFIG_PATH", tmp_path / "no_such_config.json")
        cfg = app_module.load_config()
        assert cfg["results_dir"] == app_module.DEFAULT_CONFIG["results_dir"]
        assert cfg["audio_root"] == app_module.DEFAULT_CONFIG["audio_root"]
        assert (tmp_path / "no_such_config.json").exists()

    def test_file_values_override_defaults(self, app_module, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(
            json.dumps({"results_dir": "custom_results"}), encoding="utf-8"
        )
        monkeypatch.setattr(app_module, "CONFIG_PATH", cfg_path)
        cfg = app_module.load_config()
        assert cfg["results_dir"] == "custom_results"
        assert cfg["ref_dir"] == app_module.DEFAULT_CONFIG["ref_dir"]

    def test_malformed_json_falls_back_to_defaults(
        self, app_module, tmp_path, monkeypatch
    ):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text("{ not valid json", encoding="utf-8")
        monkeypatch.setattr(app_module, "CONFIG_PATH", cfg_path)
        cfg = app_module.load_config()
        assert cfg == app_module.DEFAULT_CONFIG

    def test_env_vars_take_priority_over_file(self, app_module, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps({"results_dir": "from_file"}), encoding="utf-8")
        monkeypatch.setattr(app_module, "CONFIG_PATH", cfg_path)
        monkeypatch.setenv("MAQAM_RESULTS_DIR", "from_env")
        cfg = app_module.load_config()
        assert cfg["results_dir"] == "from_env"


class TestSaveConfig:
    def test_save_persists_only_editable_keys(self, app_module, tmp_path, monkeypatch):
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(
            json.dumps({"backend": "clap", "results_dir": "old"}), encoding="utf-8"
        )
        monkeypatch.setattr(app_module, "CONFIG_PATH", cfg_path)
        app_module.CONFIG["results_dir"] = "new_results"
        app_module.CONFIG["audio_root"] = "new_audio"
        app_module.CONFIG["ref_dir"] = "new_ref"
        assert app_module.save_config() is True
        on_disk = json.loads(cfg_path.read_text(encoding="utf-8"))
        assert on_disk["results_dir"] == "new_results"
        assert on_disk["backend"] == "clap"


class TestResolve:
    def test_relative_path_resolves_against_base_dir(self, app_module):
        result = app_module.resolve("some_folder")
        assert result == (app_module.BASE_DIR / "some_folder").resolve()

    def test_absolute_path_used_as_is(self, app_module, tmp_path):
        abs_path = str(tmp_path / "abs_folder")
        result = app_module.resolve(abs_path)
        assert str(result) == str(tmp_path / "abs_folder")


class TestAudioIndex:
    def test_build_audio_index_walks_recursively(self, app_module, data_dirs):
        app_module.CONFIG["audio_root"] = str(data_dirs["audio"])
        index = app_module.build_audio_index(force=True)
        assert "track_a.mp3" in index
        assert "track_b.mp3" in index
        assert len(index) == 4

    def test_resolve_audio_file_ignores_foreign_machine_path(
        self, app_module, data_dirs
    ):
        app_module.CONFIG["audio_root"] = str(data_dirs["audio"])
        app_module.build_audio_index(force=True)
        local = app_module.resolve_audio_file(
            "/content/SUNO_BACKUP/some_run/track_a.mp3"
        )
        assert local is not None
        assert local.endswith("track_a.mp3")

    def test_resolve_audio_file_returns_none_for_missing_file(
        self, app_module, data_dirs
    ):
        app_module.CONFIG["audio_root"] = str(data_dirs["audio"])
        app_module.build_audio_index(force=True)
        assert app_module.resolve_audio_file("nonexistent_track.mp3") is None


class TestResolveRefFile:
    def test_matches_by_arabic_prefix(self, app_module, data_dirs):
        app_module.CONFIG["ref_dir"] = str(data_dirs["ref"])
        f = app_module.resolve_ref_file("hijaz")
        assert f is not None
        assert f.name.startswith("حجاز")

    def test_falls_back_to_substring_match(self, app_module, data_dirs):
        app_module.CONFIG["ref_dir"] = str(data_dirs["ref"])
        f = app_module.resolve_ref_file("ajam")
        assert f is not None
        assert "ajam" in f.name.lower()

    def test_returns_none_when_no_reference_exists(self, app_module, data_dirs):
        app_module.CONFIG["ref_dir"] = str(data_dirs["ref"])
        assert app_module.resolve_ref_file("kurd") is None
