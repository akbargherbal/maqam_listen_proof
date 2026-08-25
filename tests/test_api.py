import json
import pytest


class TestIndexPage:
    def test_index_serves_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Maqam" in resp.data


class TestConfigEndpoint:
    def test_api_config_reports_configured_state(self, client):
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["is_configured"] is True
        assert data["results_exists"] is True
        assert data["audio_root_exists"] is True
        assert data["ref_dir_exists"] is True
        assert data["indexed_files"] == 4
        assert data["maqam_count"] == 2


class TestSettingsEndpoint:
    def test_post_settings_updates_and_persists_config(self, configured_app, tmp_path):
        client = configured_app.app.test_client()
        new_audio = tmp_path / "brand_new_audio_root"
        new_audio.mkdir()
        (new_audio / "only_track.mp3").write_bytes(b"x")

        resp = client.post(
            "/api/settings",
            data=json.dumps({"audio_root": str(new_audio)}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["audio_root_exists"] is True
        assert data["indexed_files"] == 1
        assert configured_app.CONFIG["audio_root"] == str(new_audio)


class TestMaqamsEndpoint:
    def test_lists_all_maqams_with_metadata(self, client):
        resp = client.get("/api/maqams")
        assert resp.status_code == 200
        data = resp.get_json()
        names = {m["name"]: m for m in data["maqams"]}
        assert set(names) == {"ajam", "hijaz"}
        assert names["hijaz"]["count"] == 3
        assert names["hijaz"]["has_ref"] is True


class TestMaqamDetailEndpoint:
    def test_returns_rows_with_found_flags(self, client):
        resp = client.get("/api/maqam/hijaz")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["maqam"] == "hijaz"
        assert data["total"] == 3
        by_rank = {r["rank"]: r for r in data["rows"]}
        assert by_rank[1]["found"] is True
        assert by_rank[3]["found"] is False
        assert by_rank[1]["similarity"] == pytest.approx(0.9123)

    def test_unknown_maqam_returns_404(self, client):
        resp = client.get("/api/maqam/does_not_exist")
        assert resp.status_code == 404


class TestAudioStreaming:
    def test_stream_reference_track(self, client):
        resp = client.get("/audio/ref/hijaz")
        assert resp.status_code == 200
        assert resp.data == b"fake-ref-hijaz"

    def test_stream_candidate_track(self, client):
        resp = client.get("/audio/track/hijaz/1")
        assert resp.status_code == 200
        assert resp.data == b"fake-mp3-bytes-a"

    def test_candidate_missing_from_disk_returns_404(self, client):
        resp = client.get("/audio/track/hijaz/3")
        assert resp.status_code == 404
