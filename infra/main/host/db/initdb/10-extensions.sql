-- Runs once, on an empty data directory, in POSTGRES_DB. The same two extensions the app needs:
-- locally postgis comes with the postgis/postgis image and vector from the migration.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;
