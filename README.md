# VibeCast

Jamendo-only music discovery with vibe playlists, hybrid recommendations, listening analytics, artist uploads, and database-enforced access control.

## Quick start

1. Copy `.env.example` to `.env` and set unique local passwords, a random `VIBECAST_JWT_SECRET`, and a Jamendo API client ID.
2. Run `docker compose up --build`.
3. Create the first platform administrator with `docker compose exec api python -m app.cli create-admin`.
4. Open [http://localhost:5173](http://localhost:5173); the API health page is [http://localhost:8000/health/ready](http://localhost:8000/health/ready).
5. Sign in as the administrator and start a catalog sync. The UI stays empty until real Jamendo catalog records have synced.

## Project guide

- [Architecture audit and design](ARCHITECTURE.md)
- [Implementation checklist](docs/implementation-checklist.md)
- [Setup, data, security, testing, and troubleshooting](docs/README.md)

VibeCast does not ship a fallback song catalog. Jamendo is the only external catalog source; artist uploads are stored separately as `artist_upload`. See the architecture document for Jamendo attribution and usage constraints before any hosted release.
