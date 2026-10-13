-- Runs once, when the database volume is first created.
-- Tables are created in step 4; for now we only enable pgvector.
CREATE EXTENSION IF NOT EXISTS vector;
