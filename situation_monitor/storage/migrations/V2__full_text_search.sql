-- Migration V2: Full Text Search
-- Created: 2026-02-28
-- Adds FTS5 virtual tables for full-text search on documents

-- FTS5 virtual table for document full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    text,
    content='documents',
    content_rowid='rowid'
);

-- Trigger to keep FTS index up to date on insert
CREATE TRIGGER IF NOT EXISTS documents_fts_insert
AFTER INSERT ON documents
BEGIN
    INSERT INTO documents_fts(rowid, title, text)
    VALUES (new.rowid, new.title, new.text);
END;

-- Trigger to keep FTS index up to date on update
CREATE TRIGGER IF NOT EXISTS documents_fts_update
AFTER UPDATE ON documents
BEGIN
    UPDATE documents_fts SET 
        title = new.title,
        text = new.text
    WHERE rowid = new.rowid;
END;

-- Trigger to keep FTS index up to date on delete
CREATE TRIGGER IF NOT EXISTS documents_fts_delete
AFTER DELETE ON documents
BEGIN
    DELETE FROM documents_fts WHERE rowid = old.rowid;
END;

-- Index documents already in the database
INSERT INTO documents_fts(rowid, title, text)
SELECT rowid, title, text FROM documents;
