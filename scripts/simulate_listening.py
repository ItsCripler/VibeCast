"""Seed opt-in synthetic listeners and plays over already-synced Jamendo songs."""

from __future__ import annotations

import argparse
import random
import uuid
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta

from app.config import settings
from app.db.models import PlayEvent, Song, User
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

NAMESPACE = uuid.UUID("f7a6d694-4e95-5d5c-9ff0-0b0911ad7ec5")


def simulate(*, user_count: int, seed: int, days: int, as_of: date) -> int:
    if settings.environment not in {"development", "test"}:
        raise SystemExit("Synthetic listening is restricted to development or test environments.")
    engine = create_engine(settings.database_migration_url, pool_pre_ping=True)
    inserted_events = 0
    try:
        with Session(engine) as db:
            songs = db.scalars(select(Song).where(Song.source == "jamendo", Song.is_public.is_(True))
                               .order_by(Song.id)).all()
            if not songs:
                raise SystemExit("No synced Jamendo tracks found. Run a catalog sync before simulation.")
            songs_by_tag: dict[str, list[Song]] = defaultdict(list)
            tag_counts: Counter[str] = Counter()
            for song in songs:
                for tag in {str(value).casefold() for value in song.tags or []}:
                    songs_by_tag[tag].append(song)
                    tag_counts[tag] += 1
            personas = [tag for tag, _count in tag_counts.most_common(12)] or ["all music"]
            rng = random.Random(seed)
            users = []
            events = []
            as_of_time = datetime.combine(as_of, datetime.max.time(), tzinfo=UTC)
            for index in range(user_count):
                persona = personas[index % len(personas)]
                user_id = uuid.uuid5(NAMESPACE, f"listener:{seed}:{index + 1}")
                email = f"demo-{seed}-{index + 1:04d}@example.invalid"
                users.append({
                    "id": user_id, "name": f"Demo Listener {index + 1:04d}", "email": email,
                    "role": "listener", "password_hash": None,
                    "preferences": {"synthetic_demo": True, "persona_tag": persona},
                })
                themed = songs_by_tag.get(persona, songs)
                other = [song for song in songs if song not in themed]
                count = rng.randint(12, 28)
                for event_index in range(count):
                    pool = themed if rng.random() < 0.8 else (other or songs)
                    song = rng.choice(pool)
                    duration = song.duration_seconds
                    if duration is not None and duration < 30:
                        listened = max(1, duration)
                    else:
                        listened = rng.randint(30, min(max(duration or 240, 30), 240))
                    played_at = as_of_time - timedelta(days=rng.randrange(days),
                                                       seconds=rng.randrange(24 * 60 * 60))
                    event_id = uuid.uuid5(NAMESPACE, f"event:{seed}:{index + 1}:{event_index}")
                    events.append({
                        "id": event_id, "client_event_id": event_id, "user_id": user_id,
                        "song_id": song.id, "played_at": played_at,
                        "duration_played_seconds": listened, "qualified": True,
                    })
            if users:
                db.execute(pg_insert(User).values(users).on_conflict_do_nothing(index_elements=[User.id]))
            if events:
                result = db.execute(pg_insert(PlayEvent).values(events).on_conflict_do_nothing(
                    index_elements=[PlayEvent.client_event_id]))
                inserted_events = result.rowcount or 0
            db.commit()
            print(f"Jamendo tracks used: {len(songs)}")
            print(f"Synthetic listeners considered: {user_count}")
            print(f"New qualified play events inserted: {inserted_events}")
            print(f"Persona tags: {', '.join(personas)}")
    finally:
        engine.dispose()
    return inserted_events


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=100, help="number of synthetic listeners (default: 100)")
    parser.add_argument("--seed", type=int, default=41, help="fixed random seed")
    parser.add_argument("--days", type=int, default=90, help="lookback window for simulated plays")
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(UTC).date(),
                        help="anchor date in YYYY-MM-DD form for repeatable timestamps")
    args = parser.parse_args()
    if args.users < 1 or args.users > 10_000 or args.days < 1 or args.days > 365:
        parser.error("--users must be 1..10000 and --days must be 1..365")
    simulate(user_count=args.users, seed=args.seed, days=args.days, as_of=args.as_of)


if __name__ == "__main__":
    main()
