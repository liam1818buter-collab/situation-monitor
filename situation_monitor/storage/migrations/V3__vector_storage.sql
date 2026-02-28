-- Migration V3: Vector Storage
-- Created: 2026-02-28
-- Adds tables for vector embeddings using sqlite-vec or external ChromaDB

-- Table to track embedding status
CREATE TABLE IF NOT EXISTS document_embeddings (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL UNIQUE,
    situation_id TEXT NOT NULL,
    embedding_model TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    embedding_dimensions INTEGER DEFAULT 384,
    -- For sqlite-vec: stored as binary blob
    -- For ChromaDB: stores external ID/reference
    vector_data BLOB,
    chroma_id TEXT,  -- ChromaDB document ID if using ChromaDB
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (situation_id) REFERENCES situations(id) ON DELETE CASCADE
);

-- Index for quick lookup
CREATE INDEX IF NOT EXISTS idx_embeddings_document ON document_embeddings(document_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_situation ON document_embeddings(situation_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_chroma ON document_embeddings(chroma_id);

-- Table for archived documents (compressed storage)
CREATE TABLE IF NOT EXISTS archived_documents (
    id TEXT PRIMARY KEY,
    original_document_id TEXT NOT NULL,
    situation_id TEXT NOT NULL,
    archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archive_format TEXT DEFAULT 'zstd',  -- zstd, gzip, etc.
    compressed_data BLOB NOT NULL,
    original_size INTEGER,
    compressed_size INTEGER,
    metadata TEXT NOT NULL DEFAULT '{}'  -- JSON with original timestamps, etc.
);

CREATE INDEX IF NOT EXISTS idx_archived_situation ON archived_documents(situation_id);
CREATE INDEX IF NOT EXISTS idx_archived_original ON archived_documents(original_document_id);
CREATE INDEX IF NOT EXISTS idx_archived_at ON archived_documents(archived_at);
