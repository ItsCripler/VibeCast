from __future__ import annotations

import httpx
import pytest

from app.config import settings
from app.integrations.jamendo import JamendoClient, normalize_track
from app.recommendations.hybrid import normalize_scores
from app.recommendations.vibe import _feature_score, _tag_score, _weighted_score


def test_normalize_track_preserves_real_provider_identity_and_handles_single() -> None:
    track = normalize_track({
        "id": "track-42", "name": "Night Drive", "artist_id": "artist-5",
        "artist_name": "A Real Artist", "duration": "205", "image": "https://img.example/art.jpg",
        "shareurl": "https://www.jamendo.com/track/track-42",
        "musicinfo": {"tags": {"genres": ["Electronic", "ambient"], "vartags": ["Night"]}},
        "audiodownload_allowed": False,
    })

    assert track.track_id == "track-42"
    assert track.album_id is None
    assert track.duration_seconds == 205
    assert track.tags == ["ambient", "electronic", "night"]
    assert track.audiodownload_allowed is False
    assert track.source_url.endswith("track-42")


def test_jamendo_client_sends_required_client_id_and_normalizes_results(monkeypatch) -> None:
    monkeypatch.setattr(settings, "jamendo_min_request_interval", 0.0)
    requested: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requested.append(request)
        return httpx.Response(200, json={"headers": {"code": 0}, "results": [
            {"id": "real-1", "name": "Blue Hour", "artist_name": "Aster", "musicinfo": {}}
        ]})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        with JamendoClient(client_id="test-client-id", client=http) as jamendo:
            result = jamendo.get_tracks(limit=250, offset=0)

    assert len(result) == 1 and result[0].track_id == "real-1"
    assert requested[0].url.params["client_id"] == "test-client-id"
    assert requested[0].url.params["limit"] == "200"
    assert requested[0].url.path.endswith("/tracks")


def test_vibe_matching_uses_tags_and_only_scores_observed_feature_intents() -> None:
    assert _tag_score("calm ambient", ["ambient", "downtempo"]) == 0.5
    assert _tag_score("party", ["art"]) == 0.0
    assert _feature_score("calm slow", {"energy": 0.2, "tempo": 78}) == 1.0
    assert _feature_score("slow upbeat", {"tempo_bpm": 74, "energy_category": "high"}) == 1.0
    assert _feature_score("calm", {}) is None
    assert _weighted_score(0.8, 0.5, None) == pytest.approx((0.8 * 0.65 + 0.5 * 0.2) / 0.85)


def test_score_normalization_is_stable_for_equal_and_mixed_values() -> None:
    assert normalize_scores({}) == {}
    assert normalize_scores({"a": 0.4, "b": 0.4}) == {"a": 1.0, "b": 1.0}
    assert normalize_scores({"a": 0.0, "b": 2.0}) == {"a": 0.0, "b": 1.0}
