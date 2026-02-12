-- PostgreSQL 16 tuning for MedTimeline on M4 MacBook Air 16GB
-- Run once after createdb: psql medtimeline < scripts/pg-tuning.sql
--
-- These settings optimize for bulk imports of large Epic EHI exports
-- (hundreds of TSV files, millions of rows) while keeping the system
-- responsive for interactive queries.

-- Memory
ALTER SYSTEM SET shared_buffers = '512MB';
ALTER SYSTEM SET work_mem = '32MB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';
ALTER SYSTEM SET effective_cache_size = '2GB';

-- WAL — tuned for sustained bulk inserts
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET max_wal_size = '2GB';
ALTER SYSTEM SET min_wal_size = '512MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET checkpoint_timeout = '15min';

-- Connections
ALTER SYSTEM SET max_connections = 20;

-- Query planner — SSD-optimized
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;

-- Logging — helpful for debugging slow queries during development
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- log queries > 1s
ALTER SYSTEM SET log_checkpoints = 'on';
ALTER SYSTEM SET log_temp_files = 0;

-- Apply changes (requires restart)
SELECT pg_reload_conf();

-- NOTE: Some settings (shared_buffers) require a PostgreSQL restart:
--   brew services restart postgresql@16
