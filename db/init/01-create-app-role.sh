#!/bin/sh
set -eu

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 \
  --set=app_password="$VIBECAST_APP_DB_PASSWORD" <<'SQL'
CREATE ROLE vibecast_app LOGIN PASSWORD :'app_password';
SQL
