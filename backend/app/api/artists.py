import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.dependencies import OptionalUser, require_roles
from app.config import settings
from app.db.models import ArtistProfile, Job, Song, User
from app.db.session import get_db
from app.schemas.catalog import ArtistSongOut
from app.services.catalog_sync import EMBEDDING_VERSION

router = APIRouter(prefix="/artists", tags=["artists"])
ArtistUser = Depends(require_roles("artist"))
ALLOWED_FORMATS = {".mp3", ".wav", ".flac", ".ogg"}


def _valid_audio_header(extension: str, header: bytes) -> bool:
    if extension == ".wav":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if extension == ".flac":
        return header.startswith(b"fLaC")
    if extension == ".ogg":
        return header.startswith(b"OggS")
    return header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0)


@router.get("/me")
def artist_profile(artist: User = ArtistUser, db: Session = Depends(get_db)):
    profile = db.scalar(select(ArtistProfile).where(ArtistProfile.user_id == artist.id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Artist profile has not been created")
    return {"id": profile.id, "stage_name": profile.stage_name, "bio": profile.bio,
            "label_id": profile.label_id}


@router.get("/me/songs", response_model=list[ArtistSongOut])
def my_songs(artist: User = ArtistUser, db: Session = Depends(get_db)):
    profile = db.scalar(select(ArtistProfile).where(ArtistProfile.user_id == artist.id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Artist profile has not been created")
    return db.scalars(select(Song).where(Song.artist_profile_id == profile.id)
                      .order_by(Song.created_at.desc())).all()


@router.post("/me/songs", status_code=status.HTTP_202_ACCEPTED)
async def upload_song(title: str = Form(min_length=1, max_length=240),
                      tags: str = Form(default="", max_length=500),
                      license_url: str = Form(min_length=8, max_length=500),
                      rights_confirmed: bool = Form(),
                      audio: UploadFile = File(),
                      artist: User = ArtistUser, db: Session = Depends(get_db)):
    if not rights_confirmed:
        raise HTTPException(status_code=422, detail="Confirm that you have the rights to upload this recording")
    if not license_url.startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail="Provide an http(s) license or rights-information URL")
    suffix = Path(audio.filename or "").suffix.lower()
    if suffix not in ALLOWED_FORMATS:
        raise HTTPException(status_code=415, detail="Upload an MP3, WAV, FLAC, or OGG audio file")
    profile = db.scalar(select(ArtistProfile).where(ArtistProfile.user_id == artist.id))
    if profile is None:
        raise HTTPException(status_code=409, detail="Ask a platform administrator to create your artist profile")

    root = Path(settings.upload_directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    song_id = uuid.uuid4()
    final_path = root / f"{song_id}{suffix}"
    total = 0
    prefix = b""
    try:
        with final_path.open("wb") as target:
            while chunk := await audio.read(64 * 1024):
                if len(prefix) < 16:
                    prefix += chunk[:16 - len(prefix)]
                total += len(chunk)
                if total > settings.upload_max_bytes:
                    raise HTTPException(status_code=413, detail="Audio upload exceeds the configured size limit")
                target.write(chunk)
        if total == 0 or not _valid_audio_header(suffix, prefix):
            raise HTTPException(status_code=415, detail="The file contents do not match the selected audio format")
        song = Song(
            id=song_id, source="artist_upload", artist_profile_id=profile.id,
            title=title.strip(), artist_name=profile.stage_name,
            duration_seconds=None, tags=sorted({tag.strip().lower() for tag in tags.split(",") if tag.strip()}),
            artwork_url=None, source_url=None, license_url=license_url.strip(),
            upload_rights_confirmed_at=datetime.now(UTC), upload_path=str(final_path),
            is_public=False, analysis_status="pending",
        )
        db.add(song)
        db.flush()
        db.add_all([
            Job(kind="embed_song", idempotency_key=f"upload-embed:{song.id}:{EMBEDDING_VERSION}",
                payload={"song_id": str(song.id), "version": EMBEDDING_VERSION}),
            Job(kind="analyze_song", idempotency_key=f"upload-analysis:{song.id}:v1",
                payload={"song_id": str(song.id)}),
        ])
        db.commit()
    except HTTPException:
        db.rollback()
        final_path.unlink(missing_ok=True)
        raise
    except Exception:
        db.rollback()
        final_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Audio upload could not be saved") from None
    finally:
        await audio.close()
    return {"song_id": song_id, "source": "artist_upload", "status": "processing",
            "message": "The track will appear after metadata embedding completes."}


@router.get("/me/performance")
def my_performance(artist: User = ArtistUser, db: Session = Depends(get_db)):
    profile = db.scalar(select(ArtistProfile).where(ArtistProfile.user_id == artist.id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Artist profile has not been created")
    rows = db.execute(text("SELECT song_id, title, qualified_plays, listening_seconds, last_played_at "
                           "FROM artist_song_performance WHERE artist_profile_id = :artist_id "
                           "ORDER BY qualified_plays DESC"), {"artist_id": profile.id}).all()
    return [{"song_id": row.song_id, "title": row.title, "qualified_plays": int(row.qualified_plays),
             "listening_seconds": int(row.listening_seconds), "last_played_at": row.last_played_at}
            for row in rows]


@router.get("/songs/{song_id}/audio")
def stream_artist_upload(song_id: uuid.UUID, user: OptionalUser, db: Session = Depends(get_db)):
    song = db.scalar(select(Song).where(Song.id == song_id, Song.source == "artist_upload"))
    if song is None:
        raise HTTPException(status_code=404, detail="Uploaded song not found")
    if not song.is_public and (user is None or song.artist_profile_id is None):
        raise HTTPException(status_code=404, detail="Uploaded song not found")
    root = Path(settings.upload_directory).resolve()
    try:
        path = Path(song.upload_path or "").resolve()
        path.relative_to(root)
    except (ValueError, OSError):
        raise HTTPException(status_code=404, detail="Uploaded audio is unavailable") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Uploaded audio is unavailable")
    return FileResponse(path, media_type="audio/mpeg" if path.suffix == ".mp3" else None,
                        headers={"Cache-Control": "no-store"})
