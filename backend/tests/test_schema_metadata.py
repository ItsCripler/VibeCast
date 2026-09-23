from sqlalchemy import UniqueConstraint

from app.db.models import PlaylistSong


def test_playlist_song_unique_constraints_have_distinct_names() -> None:
    unique_names = {
        constraint.name
        for constraint in PlaylistSong.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_names == {
        "uq_playlist_songs_playlist_id_song_id",
        "uq_playlist_songs_playlist_id_position",
    }
