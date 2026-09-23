from __future__ import annotations

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import Job, Song, SongFeature
from app.integrations.jamendo import JamendoAPIError, JamendoClient


def _license_is_creative_commons(license_url: str | None) -> bool:
    return bool(license_url and "creativecommons.org/licenses/" in license_url.lower())


def _essentia_features(audio_path: Path) -> tuple[dict, dict, str]:
    try:
        import essentia
        import essentia.standard as es
    except ImportError as exc:
        raise RuntimeError("Essentia is not installed in this worker") from exc

    signal = np.asarray(es.MonoLoader(filename=str(audio_path), sampleRate=44_100)(), dtype=np.float32)
    if signal.size < 44_100 * 3:
        raise ValueError("Track is too short for the selected analysis")
    bpm, _ticks, confidence, _estimates, _intervals = es.RhythmExtractor2013(method="multifeature")(signal)
    key, scale, key_strength = es.KeyExtractor(sampleRate=44_100)(signal)
    loudness = float(es.Loudness()(signal))
    spectral_centroid = float(es.SpectralCentroidTime(sampleRate=44_100)(signal))
    rms = float(np.sqrt(np.mean(np.square(signal), dtype=np.float64)))

    tempo = float(bpm)
    energy = min(1.0, max(0.0, rms / 0.25))
    essentia_values = {
        "tempo_bpm": tempo,
        "beat_confidence": float(confidence),
        "key": str(key),
        "key_scale": str(scale),
        "key_strength": float(key_strength),
        "loudness_stevens": loudness,
        "spectral_centroid_hz": spectral_centroid,
        "rms_amplitude": rms,
    }
    derived_values = {
        "tempo_category": "slow" if tempo < 80 else "fast" if tempo >= 120 else "moderate",
        "energy": energy,
        "energy_category": "low" if energy < 0.35 else "high" if energy >= 0.65 else "moderate",
        "derivation": "tempo thresholds 80/120 BPM; energy is RMS normalized by 0.25",
    }
    return essentia_values, derived_values, str(getattr(essentia, "__version__", "unknown"))


def analyze_song(db: Session, song_id: str) -> str:
    song = db.scalar(select(Song).where(Song.id == uuid.UUID(song_id)))
    if song is None:
        return "missing"
    if song.analysis_status == "completed":
        return "already_completed"

    if song.source == "jamendo":
        if not song.audiodownload_allowed or not _license_is_creative_commons(song.license_url):
            song.analysis_status = "unavailable"
            db.commit()
            return "unavailable"
        with tempfile.TemporaryDirectory(prefix="vibecast-analysis-") as temp_dir:
            temporary_audio = Path(temp_dir) / "track.mp3"
            client = JamendoClient()
            try:
                current = client.get_track(song.jamendo_track_id or "")
                if current is None or not current.audiodownload_allowed or not _license_is_creative_commons(current.license_url):
                    song.analysis_status = "unavailable"
                    db.commit()
                    return "unavailable"
                downloaded = client.download_track_to(current.track_id, temporary_audio)
                if not downloaded:
                    song.analysis_status = "unavailable"
                    db.commit()
                    return "unavailable"
            except JamendoAPIError:
                song.analysis_status = "failed"
                db.commit()
                raise
            finally:
                client.close()
            try:
                values, derived, version = _essentia_features(temporary_audio)
            except RuntimeError as exc:
                if "not installed" in str(exc):
                    song.analysis_status = "unavailable"
                    db.commit()
                    return "unavailable"
                raise
    elif song.source == "artist_upload":
        path = Path(song.upload_path or "")
        if not path.is_file():
            song.analysis_status = "unavailable"
            db.commit()
            return "unavailable"
        try:
            values, derived, version = _essentia_features(path)
        except RuntimeError as exc:
            if "not installed" in str(exc):
                song.analysis_status = "unavailable"
                db.commit()
                return "unavailable"
            raise
    else:
        song.analysis_status = "unavailable"
        db.commit()
        return "unavailable"

    analyzed_at = datetime.now(UTC)
    db.execute(pg_insert(SongFeature).values(
        song_id=song.id, essentia_values=values, derived_values=derived,
        analyzer_version=f"essentia-{version}", analyzed_at=analyzed_at,
    ).on_conflict_do_update(
        index_elements=[SongFeature.song_id],
        set_={"essentia_values": values, "derived_values": derived,
              "analyzer_version": f"essentia-{version}", "analyzed_at": analyzed_at},
    ))
    song.analysis_status = "completed"
    song.updated_at = analyzed_at
    db.add(Job(kind="embed_song", idempotency_key=f"analysis-embed:{song.id}:v1:{analyzed_at.date()}",
               payload={"song_id": str(song.id), "version": "v1"}))
    db.commit()
    return "completed"
