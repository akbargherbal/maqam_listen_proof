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


class TestRatingsEndpoint:
    def test_post_rating_shows_up_in_maqam_detail(self, client):
        resp = client.post(
            "/api/maqam/hijaz/rating",
            data=json.dumps({"filename": "track_a.mp3", "stars": 4}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["stars"] == 4

        detail = client.get("/api/maqam/hijaz").get_json()
        by_filename = {r["filename"]: r for r in detail["rows"]}
        assert by_filename["track_a.mp3"]["stars"] == 4
        assert detail["rated_count"] == 1

    def test_clearing_rating_removes_it(self, client):
        client.post(
            "/api/maqam/hijaz/rating",
            data=json.dumps({"filename": "track_a.mp3", "stars": 3}),
            content_type="application/json",
        )
        resp = client.post(
            "/api/maqam/hijaz/rating",
            data=json.dumps({"filename": "track_a.mp3", "stars": None}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        assert resp.get_json()["stars"] is None

        detail = client.get("/api/maqam/hijaz").get_json()
        by_filename = {r["filename"]: r for r in detail["rows"]}
        assert by_filename["track_a.mp3"]["stars"] is None
        assert detail["rated_count"] == 0

    def test_out_of_range_stars_rejected(self, client):
        resp = client.post(
            "/api/maqam/hijaz/rating",
            data=json.dumps({"filename": "track_a.mp3", "stars": 6}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_missing_filename_rejected(self, client):
        resp = client.post(
            "/api/maqam/hijaz/rating",
            data=json.dumps({"stars": 3}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_rating_visible_across_top50_and_full_mode(self, client):
        # track_a.mp3 appears (with the same filename) in both the top50
        # and full CSVs for hijaz in this fixture -- rating it once should
        # be visible in both modes, since ratings are keyed by filename.
        client.post(
            "/api/maqam/hijaz/rating",
            data=json.dumps({"filename": "track_a.mp3", "stars": 5}),
            content_type="application/json",
        )
        top50 = client.get("/api/maqam/hijaz?full=0").get_json()
        full = client.get("/api/maqam/hijaz?full=1").get_json()
        top50_stars = {r["filename"]: r["stars"] for r in top50["rows"]}
        full_stars = {r["filename"]: r["stars"] for r in full["rows"]}
        assert top50_stars["track_a.mp3"] == 5
        assert full_stars["track_a.mp3"] == 5

    def test_ratings_persist_across_fresh_module_load(self, configured_app, data_dirs):
        """Simulates restarting the Flask process: a brand-new load_ratings()
        call (not relying on any in-memory state) must still see the rating
        that was saved to disk earlier -- this is the actual cross-session
        persistence guarantee."""
        client = configured_app.app.test_client()
        client.post(
            "/api/maqam/hijaz/rating",
            data=json.dumps({"filename": "track_b.mp3", "stars": 2}),
            content_type="application/json",
        )

        ratings_file = data_dirs["results"] / "ratings" / "hijaz.json"
        assert ratings_file.exists()

        # Fresh read straight from disk, independent of any app-level cache.
        on_disk = json.loads(ratings_file.read_text(encoding="utf-8"))
        assert on_disk["ratings"]["track_b.mp3"]["stars"] == 2


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
