from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import settings


class JamendoAPIError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, status_code: int | None = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class JamendoRateLimitError(JamendoAPIError):
    pass


@dataclass(frozen=True)
class JamendoTrack:
    track_id: str
    title: str
    artist_id: str | None
    artist_name: str
    album_id: str | None
    album_name: str | None
    album_image: str | None
    artwork_url: str | None
    duration_seconds: int | None
    tags: list[str]
    musicinfo: dict[str, Any]
    audio_url: str | None
    download_url: str | None
    audiodownload_allowed: bool
    license_url: str | None
    source_url: str
    released_at: str | None


def _as_nonempty(value: Any) -> str | None:
    text_value = str(value).strip() if value is not None else ""
    return text_value or None


def _flatten_tags(musicinfo: dict[str, Any]) -> list[str]:
    tags = musicinfo.get("tags") or {}
    result: list[str] = []
    if isinstance(tags, dict):
        for values in tags.values():
            if isinstance(values, str):
                values = [values]
            if isinstance(values, list):
                result.extend(str(value).strip().lower() for value in values if str(value).strip())
    return sorted(set(result))


def normalize_track(raw: dict[str, Any]) -> JamendoTrack:
    """Translate one provider payload into the stable internal contract."""
    track_id = _as_nonempty(raw.get("id"))
    title = _as_nonempty(raw.get("name"))
    if not track_id or not title:
        raise JamendoAPIError("Track response omitted its stable ID or title")
    try:
        duration = int(raw["duration"]) if raw.get("duration") not in (None, "") else None
    except (TypeError, ValueError):
        duration = None
    musicinfo = raw.get("musicinfo") if isinstance(raw.get("musicinfo"), dict) else {}
    share_url = _as_nonempty(raw.get("shareurl")) or f"https://www.jamendo.com/track/{track_id}"
    return JamendoTrack(
        track_id=track_id,
        title=title,
        artist_id=_as_nonempty(raw.get("artist_id")),
        artist_name=_as_nonempty(raw.get("artist_name")) or "Unknown artist",
        album_id=_as_nonempty(raw.get("album_id")),
        album_name=_as_nonempty(raw.get("album_name")),
        album_image=_as_nonempty(raw.get("album_image")),
        artwork_url=_as_nonempty(raw.get("image")),
        duration_seconds=max(0, duration) if duration is not None else None,
        tags=_flatten_tags(musicinfo),
        musicinfo=musicinfo,
        audio_url=_as_nonempty(raw.get("audio")),
        download_url=_as_nonempty(raw.get("audiodownload")),
        audiodownload_allowed=raw.get("audiodownload_allowed") is True,
        license_url=_as_nonempty(raw.get("license_ccurl")),
        source_url=share_url,
        released_at=_as_nonempty(raw.get("releasedate")),
    )


class JamendoClient:
    """Small read-only API v3 adapter; never downloads or persists audio bytes."""

    def __init__(self, client_id: str | None = None, base_url: str | None = None,
                 client: httpx.Client | None = None):
        self.client_id = client_id or settings.jamendo_client_id
        self.base_url = (base_url or settings.jamendo_api_base).rstrip("/")
        self._client = client or httpx.Client(timeout=httpx.Timeout(20.0, connect=5.0))
        self._owns_client = client is None
        self._last_request = 0.0

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> JamendoClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _get_document(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.client_id:
            raise JamendoAPIError("Jamendo client ID is not configured")
        query = {**params, "client_id": self.client_id, "format": "json"}
        last_error: Exception | None = None
        for attempt in range(4):
            wait = settings.jamendo_min_request_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            try:
                response = self._client.get(f"{self.base_url}/{method.lstrip('/')}", params=query)
                self._last_request = time.monotonic()
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    delay = min(float(retry_after), 30.0) if retry_after and retry_after.isdigit() else min(2**attempt, 30.0)
                    if attempt == 3:
                        raise JamendoRateLimitError("Jamendo rate limit exceeded", status_code=429)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                document = response.json()
                if not isinstance(document, dict) or not isinstance(document.get("headers"), dict):
                    raise JamendoAPIError("Malformed Jamendo response")
                headers = document["headers"]
                code = int(headers.get("code", 0))
                if code == 6:
                    if attempt == 3:
                        raise JamendoRateLimitError("Jamendo rate limit exceeded", code=code)
                    time.sleep(min(2**attempt, 30.0))
                    continue
                if code != 0:
                    raise JamendoAPIError(str(headers.get("error_message") or "Jamendo request failed"), code=code)
                results = document.get("results")
                if not isinstance(results, list):
                    raise JamendoAPIError("Jamendo response did not contain a results list")
                return document
            except JamendoAPIError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ValueError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise JamendoAPIError("Jamendo rejected the request", status_code=exc.response.status_code) from None
                if attempt < 3:
                    time.sleep(min(0.5 * (2**attempt), 8.0))
        raise JamendoAPIError("Jamendo is unavailable after retries") from last_error

    def get_tracks(self, *, limit: int, offset: int, search: str | None = None,
                   track_id: str | None = None) -> list[JamendoTrack]:
        params: dict[str, Any] = {
            "limit": min(max(limit, 1), 200),
            "offset": max(offset, 0),
            "type": "single albumtrack",
            "audioformat": "mp32",
            "include": "musicinfo licenses",
            "imagesize": 300,
        }
        if search:
            params["search"] = search
        if track_id:
            params["id"] = track_id
        elif not search:
            params["order"] = "popularity_total_desc"
        document = self._get_document("tracks", params)
        try:
            return [normalize_track(item) for item in document["results"] if isinstance(item, dict)]
        except (KeyError, TypeError) as exc:
            raise JamendoAPIError("Malformed Jamendo track response") from exc

    def get_track(self, track_id: str) -> JamendoTrack | None:
        tracks = self.get_tracks(limit=1, offset=0, track_id=track_id)
        return tracks[0] if tracks else None

    def download_track_to(self, track_id: str, destination: Path, *, max_bytes: int = 100 * 1024 * 1024) -> bool:
        """Temporarily retrieve a track via Jamendo's gated file endpoint."""
        if not self.client_id:
            raise JamendoAPIError("Jamendo client ID is not configured")
        endpoint = f"{self.base_url}/tracks/file"
        params = {"client_id": self.client_id, "id": track_id, "action": "download", "audioformat": "mp32"}
        try:
            with self._client.stream("GET", endpoint, params=params, follow_redirects=True) as response:
                if response.status_code == 404:
                    return False
                response.raise_for_status()
                host = urlparse(str(response.url)).hostname or ""
                if not (host == "jamendo.com" or host.endswith(".jamendo.com")):
                    raise JamendoAPIError("Jamendo returned an unexpected audio host")
                total = 0
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes(64 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise JamendoAPIError("Track exceeds the temporary analysis size limit")
                        output.write(chunk)
                return total > 0
        except JamendoAPIError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
            raise JamendoAPIError("Jamendo audio download failed", status_code=getattr(exc, "status_code", None)) from exc
