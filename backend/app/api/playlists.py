import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, OptionalUser
from app.db.models import Playlist, PlaylistSong, Song
from app.db.session import get_db
from app.recommendations.vibe import rank_vibe_songs
from app.schemas.catalog import SongOut
from app.schemas.playlists import (
    PlaylistCreate,
    PlaylistOut,
    PlaylistSongOut,
    PlaylistUpdate,
    ReorderSongs,
    VibePlaylistOut,
    VibeRequest,
    VibeResult,
)

router = APIRouter(prefix="/playlists", tags=["playlists"])


def _playlist_out(db: Session, playlist: Playlist) -> PlaylistOut:
    rows = db.execute(
        select(PlaylistSong, Song).join(Song, Song.id == PlaylistSong.song_id)
        .where(PlaylistSong.playlist_id == playlist.id)
        .order_by(PlaylistSong.position.asc())
    ).all()
    return PlaylistOut(
        id=playlist.id, owner_id=playlist.owner_id, name=playlist.name,
        is_public=playlist.is_public, generation_type=playlist.generation_type,
        original_prompt=playlist.original_prompt, generated_at=playlist.generated_at,
        created_at=playlist.created_at,
        songs=[PlaylistSongOut(song=SongOut.model_validate(song), position=link.position,
                               relevance_score=link.relevance_score) for link, song in rows],
    )


@router.get("", response_model=list[PlaylistOut])
def list_playlists(user: OptionalUser, db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=100)):
    playlists = db.scalars(select(Playlist).order_by(Playlist.updated_at.desc()).limit(limit)).all()
    return [_playlist_out(db, playlist) for playlist in playlists]


@router.post("", response_model=PlaylistOut, status_code=status.HTTP_201_CREATED)
def create_playlist(payload: PlaylistCreate, user: CurrentUser, db: Session = Depends(get_db)):
    playlist = Playlist(owner_id=user.id, name=payload.name, is_public=payload.is_public,
                        generation_type="manual")
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return _playlist_out(db, playlist)


@router.get("/{playlist_id}", response_model=PlaylistOut)
def get_playlist(playlist_id: uuid.UUID, user: OptionalUser, db: Session = Depends(get_db)):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return _playlist_out(db, playlist)


@router.patch("/{playlist_id}", response_model=PlaylistOut)
def update_playlist(playlist_id: uuid.UUID, payload: PlaylistUpdate, user: CurrentUser,
                    db: Session = Depends(get_db)):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if playlist.owner_id != user.id and user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Only the playlist owner can edit it")
    if payload.name is not None:
        playlist.name = payload.name
    if payload.is_public is not None:
        playlist.is_public = payload.is_public
    playlist.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(playlist)
    return _playlist_out(db, playlist)


@router.delete("/{playlist_id}", status_code=204)
def delete_playlist(playlist_id: uuid.UUID, user: CurrentUser, db: Session = Depends(get_db)):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if playlist.owner_id != user.id and user.role != "platform_admin":
        raise HTTPException(status_code=403, detail="Only the playlist owner can delete it")
    db.delete(playlist)
    db.commit()


@router.post("/{playlist_id}/songs", response_model=PlaylistOut)
def add_song(playlist_id: uuid.UUID, song_id: uuid.UUID, user: CurrentUser,
             db: Session = Depends(get_db)):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if playlist.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the playlist owner can edit it")
    song = db.scalar(select(Song).where(Song.id == song_id, Song.is_public.is_(True)))
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    exists = db.scalar(select(PlaylistSong.id).where(PlaylistSong.playlist_id == playlist_id,
                                                   PlaylistSong.song_id == song_id))
    if exists:
        return _playlist_out(db, playlist)
    position = (db.scalar(select(func.max(PlaylistSong.position)).where(
        PlaylistSong.playlist_id == playlist_id)) or -1) + 1
    db.add(PlaylistSong(playlist_id=playlist_id, song_id=song_id, position=position))
    playlist.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(playlist)
    return _playlist_out(db, playlist)


@router.delete("/{playlist_id}/songs/{song_id}", response_model=PlaylistOut)
def remove_song(playlist_id: uuid.UUID, song_id: uuid.UUID, user: CurrentUser,
                db: Session = Depends(get_db)):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if playlist.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the playlist owner can edit it")
    db.execute(delete(PlaylistSong).where(PlaylistSong.playlist_id == playlist_id,
                                         PlaylistSong.song_id == song_id))
    remaining = db.scalars(select(PlaylistSong).where(PlaylistSong.playlist_id == playlist_id)
                            .order_by(PlaylistSong.position)).all()
    for position, item in enumerate(remaining):
        item.position = 100_000 + position
    db.flush()
    for position, item in enumerate(remaining):
        item.position = position
    playlist.updated_at = datetime.now(UTC)
    db.commit()
    return _playlist_out(db, playlist)


@router.put("/{playlist_id}/songs/order", response_model=PlaylistOut)
def reorder_songs(playlist_id: uuid.UUID, payload: ReorderSongs, user: CurrentUser,
                  db: Session = Depends(get_db)):
    playlist = db.get(Playlist, playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="Playlist not found")
    if playlist.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the playlist owner can edit it")
    if len(set(payload.song_ids)) != len(payload.song_ids):
        raise HTTPException(status_code=422, detail="A song may appear only once in a playlist")
    existing = {row.song_id: row for row in db.scalars(
        select(PlaylistSong).where(PlaylistSong.playlist_id == playlist_id))}
    if set(existing) != set(payload.song_ids):
        raise HTTPException(status_code=422, detail="Reorder must include every playlist song exactly once")
    for position, song_id in enumerate(payload.song_ids):
        existing[song_id].position = 100_000 + position
    db.flush()
    for position, song_id in enumerate(payload.song_ids):
        existing[song_id].position = position
    playlist.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(playlist)
    return _playlist_out(db, playlist)


@router.post("/vibe", response_model=VibePlaylistOut, status_code=201)
def generate_vibe_playlist(payload: VibeRequest, user: CurrentUser,
                            db: Session = Depends(get_db)):
    try:
        matches = rank_vibe_songs(db, payload.prompt, limit=payload.limit)
    except Exception:
        raise HTTPException(status_code=503, detail="Vibe matching is unavailable; verify the embedding model is loaded") from None
    if not matches:
        raise HTTPException(status_code=409, detail="No embedded Jamendo tracks are available yet. Sync the catalog and generate embeddings first.")
    playlist = Playlist(owner_id=user.id, name=f"Vibe: {payload.prompt[:56]}", is_public=False,
                        generation_type="vibe", original_prompt=payload.prompt,
                        generated_at=datetime.now(UTC))
    db.add(playlist)
    db.flush()
    db.add_all([
        PlaylistSong(playlist_id=playlist.id, song_id=match.song.id, position=position,
                     relevance_score=match.score)
        for position, match in enumerate(matches)
    ])
    db.commit()
    return VibePlaylistOut(
        playlist_id=playlist.id, name=playlist.name, prompt=payload.prompt,
        generated_at=playlist.generated_at,
        results=[VibeResult(song=SongOut.model_validate(match.song), score=match.score,
                            semantic_score=match.semantic_score, tag_score=match.tag_score,
                            feature_score=match.feature_score) for match in matches],
    )
