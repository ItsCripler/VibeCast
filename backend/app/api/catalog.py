from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Album, CatalogArtist, Song
from app.db.session import get_db
from app.integrations.jamendo import JamendoAPIError, JamendoClient
from app.schemas.catalog import AlbumOut, CatalogArtistOut, CatalogPage, PlaybackOut, SongOut

router = APIRouter(prefix="/catalog", tags=["catalog"])


@router.get("/songs", response_model=CatalogPage)
def list_songs(q: str | None = Query(default=None, max_length=160),
               genre: str | None = Query(default=None, max_length=80),
               tag: str | None = Query(default=None, max_length=80),
               page: int = Query(default=1, ge=1), page_size: int = Query(default=24, ge=1, le=100),
               db: Session = Depends(get_db)):
    filters = [Song.is_public.is_(True)]
    statement = select(Song).outerjoin(Album, Album.id == Song.album_id)
    count_statement = select(func.count(Song.id)).select_from(Song).outerjoin(Album, Album.id == Song.album_id)
    if q:
        pattern = f"%{q.strip()}%"
        filters.append(or_(Song.title.ilike(pattern), Song.artist_name.ilike(pattern), Album.title.ilike(pattern)))
    if genre:
        filters.append(Song.tags.contains([genre.strip().lower()]))
    if tag:
        filters.append(Song.tags.contains([tag.strip().lower()]))
    statement = statement.where(*filters).order_by(Song.released_at.desc().nullslast(), Song.title.asc())
    count_statement = count_statement.where(*filters)
    total = db.scalar(count_statement) or 0
    rows = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return CatalogPage(items=rows, page=page, page_size=page_size, total=total)


@router.get("/songs/{song_id}", response_model=SongOut)
def song_detail(song_id: str, db: Session = Depends(get_db)):
    song = db.scalar(select(Song).where(Song.id == song_id, Song.is_public.is_(True)))
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    return song


@router.get("/songs/{song_id}/playback", response_model=PlaybackOut)
def playback_resource(song_id: str, db: Session = Depends(get_db)):
    song = db.scalar(select(Song).where(Song.id == song_id, Song.is_public.is_(True)))
    if song is None:
        raise HTTPException(status_code=404, detail="Song not found")
    if song.source == "artist_upload":
        return PlaybackOut(song_id=song.id, url=f"/api/v1/artists/songs/{song.id}/audio",
                           source=song.source, source_url=song.source_url,
                           license_url=song.license_url, audiodownload_allowed=False)
    if not song.jamendo_track_id:
        raise HTTPException(status_code=502, detail="Jamendo track ID is missing")
    client = JamendoClient()
    try:
        current = client.get_track(song.jamendo_track_id)
    except JamendoAPIError:
        raise HTTPException(status_code=502, detail="Jamendo playback could not be refreshed") from None
    finally:
        client.close()
    if current is None or not current.audio_url:
        raise HTTPException(status_code=503, detail="Playback is unavailable for this Jamendo track")
    return PlaybackOut(song_id=song.id, url=current.audio_url, source="jamendo",
                       source_url=current.source_url, license_url=current.license_url,
                       audiodownload_allowed=current.audiodownload_allowed)


@router.get("/artists/jamendo/{artist_id}", response_model=CatalogArtistOut)
def jamendo_artist_detail(artist_id: str, db: Session = Depends(get_db)):
    artist = db.scalar(select(CatalogArtist).where(CatalogArtist.jamendo_artist_id == artist_id))
    if artist is None:
        raise HTTPException(status_code=404, detail="Jamendo artist not found in the synced catalog")
    return artist


@router.get("/albums/{album_id}", response_model=AlbumOut)
def album_detail(album_id: str, db: Session = Depends(get_db)):
    album = db.scalar(select(Album).where(Album.id == album_id))
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")
    songs = db.scalars(select(Song).where(Song.album_id == album.id, Song.is_public.is_(True))
                       .order_by(Song.title.asc())).all()
    return AlbumOut(id=album.id, title=album.title, artwork_url=album.artwork_url,
                    jamendo_album_id=album.jamendo_album_id, songs=songs)
