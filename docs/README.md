# VibeCast operations and development guide

## Local setup

1. Install Docker Desktop with Compose, then copy `.env.example` to `.env`.
2. Set unique `POSTGRES_PASSWORD`, `VIBECAST_APP_DB_PASSWORD`, and a random `VIBECAST_JWT_SECRET` of at least 32 characters. Add a Jamendo API client ID to enable catalog sync. Google sign-in is optional.
3. Start the stack with `docker compose up --build`.
4. Create the first administrator with `docker compose exec api python -m app.cli create-admin`.
5. Open [http://localhost:5173](http://localhost:5173), sign in, and start the catalog sync from Platform admin.

The app starts with an empty catalog by design. A first sync adds metadata and queue jobs; the worker creates text embeddings asynchronously. Vibe playlists become available once embeddings have been generated. Audio URLs are refreshed from Jamendo by stable track ID when playback begins.

## Data and access boundaries

- Jamendo tracks are the only third-party catalog records. They remain metadata rows tied to Jamendo IDs. Artist uploads use a separate source and storage path.
- PostgreSQL is the source of truth for accounts, playlists, play events, stats, features, embeddings, similarity rows, and jobs.
- The API uses the restricted `vibecast_app` role. Migrations use the owner role. Transaction-local PostgreSQL settings identify the caller or worker; row-level security limits private data.
- Qualified listening means at least 30 seconds, or at least 80% of a track shorter than 30 seconds. Event IDs make client retries idempotent. A database trigger applies atomic rollups.
- Embedding text combines actual title, artist, Jamendo tags and music information. Essentia fields are clearly stored separately from derived features. The hybrid recommender uses the listener’s qualified plays and persisted item similarities; new users receive real catalog popularity and recency fallback.
- Weekly playlists are unique per user and week. The queue worker claims jobs with `FOR UPDATE SKIP LOCKED` and retries transient failures with bounded backoff.

## Jamendo usage

Provide a read API client ID through `VIBECAST_JAMENDO_CLIENT_ID`. Sync uses the official API, follows its 200-track page limit, and stores stable IDs, attribution links, available playback metadata, tags, licenses, and download permission. It does not bundle a synthetic track catalog. Every Jamendo track links to its Jamendo page and shows the provider name.

Jamendo API access terms require attribution and describe limits on use and caching. Temporary audio analysis is attempted only when the API says downloads are allowed and the returned license URL is Creative Commons; the temporary file is removed after processing. Check the current Jamendo terms and licensing details before public or commercial hosting. The local project defaults to a non-commercial development scope.

## Artists and analysis

An artist account can upload an audio file, provide its license URL, and explicitly confirm the rights statement. Uploads are private while embedding is pending and only become public after processing. The default image omits Essentia because its platform support varies. `INSTALL_ESSENTIA=true` enables the optional dependency in the backend image; when installed, analysis uses a 44.1 kHz mono stream for rhythm, key, loudness, and spectral descriptors. Missing Essentia marks analysis unavailable rather than fabricating acoustic values.

## Tests and checks

Install backend development dependencies with `python -m pip install -e "backend[dev]"`, then run `cd backend` and `python -m pytest`. Frontend checks use the pinned pnpm version: `cd frontend`, `pnpm install --frozen-lockfile`, `pnpm run build`, and `pnpm test`.

The PostgreSQL migration and database policies can be exercised with the Compose database: `docker compose exec api alembic upgrade head`. CI starts PostgreSQL with pgvector, applies the migration, and runs the backend suite. The concurrency demonstration requires the database and migration-owner credentials.

## Synthetic listening and concurrency demo

The opt-in listening generator uses only already-synced Jamendo tracks. It creates non-login `example.invalid` listener accounts, with deterministic IDs and idempotent play-event IDs. Synthetic records are tagged in user preferences. The command refuses `production`:

```powershell
docker compose exec api python /srv/vibecast/scripts/simulate_listening.py --users 100 --seed 41 --days 90 --as-of 2026-09-24
```

Repeated runs with the same seed and anchor date do not duplicate users or events. Use a different seed to create another synthetic cohort. Reset the local database if you want to remove demo rows.

The counter demo first runs two transactions that both read zero and write one, then runs two atomic SQL increments. It uses the dedicated `demo_counters` row named `concurrency-demo`:

```powershell
docker compose exec api python /srv/vibecast/scripts/concurrency_demo.py
```

Expected output is `1` for the stale read/modify/write pattern and `2` for atomic increments. It requires the migration schema and the configured migration-owner database URL.

## Deployment notes

Set `VIBECAST_ENVIRONMENT=production`, a strong JWT secret, secure cookies, public frontend/API origins, secrets, and persistent volume backups. Production startup rejects the example JWT and database credentials. Google OAuth redirect URLs must exactly match the configured callback. Do not expose the database or use the migration-owner URL in the API. Review the Jamendo terms, creator attribution, and license for each hosting use before deployment. This Compose file is a development starting point, not a production hardening bundle.
