-- Migration V1: Initial Schema
-- Created: 2026-02-28
-- Creates core tables for situations, documents, analyses, alerts, and sources

-- Situations table: tracks monitoring topics/queries
CREATE TABLE IF NOT EXISTS situations (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    parsed_entities TEXT NOT NULL DEFAULT '[]',  -- JSON array
    keywords TEXT NOT NULL DEFAULT '[]',  -- JSON array
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'paused', 'archived', 'error')),
    config TEXT NOT NULL DEFAULT '{}'  -- JSON object
);

-- Documents table: stores fetched content
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    situation_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    title TEXT,
    text TEXT NOT NULL,
    summary TEXT,
    published_at TIMESTAMP,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'new' CHECK (status IN ('new', 'fetching', 'analyzed', 'failed', 'archived')),
    language TEXT,
    word_count INTEGER DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}',  -- JSON object
    FOREIGN KEY (situation_id) REFERENCES situations(id) ON DELETE CASCADE
);

-- Analyses table: NLP analysis results
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL UNIQUE,
    situation_id TEXT NOT NULL,
    sentiment_score REAL CHECK (sentiment_score >= -1.0 AND sentiment_score <= 1.0),
    sentiment_label TEXT,
    summary TEXT,
    key_phrases TEXT NOT NULL DEFAULT '[]',  -- JSON array
    entities TEXT NOT NULL DEFAULT '[]',  -- JSON array of objects
    keywords TEXT NOT NULL DEFAULT '[]',  -- JSON array
    topics TEXT NOT NULL DEFAULT '[]',  -- JSON array
    readability_score REAL,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    model_version TEXT DEFAULT 'unknown',
    processing_time_ms INTEGER,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY (situation_id) REFERENCES situations(id) ON DELETE CASCADE
);

-- Alerts table: generated alerts and notifications
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY,
    situation_id TEXT NOT NULL,
    document_id TEXT,
    analysis_id TEXT,
    alert_type TEXT NOT NULL CHECK (alert_type IN ('entity_mention', 'sentiment_shift', 'volume_spike', 'keyword_match', 'anomaly_detected', 'system')),
    severity TEXT NOT NULL CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
    message TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}',  -- JSON object
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMP,
    acknowledged_by TEXT,
    FOREIGN KEY (situation_id) REFERENCES situations(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL
);

-- Sources table: monitored data sources
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    situation_id TEXT NOT NULL,
    url TEXT NOT NULL,
    source_type TEXT NOT NULL,
    credibility_score REAL DEFAULT 0.5 CHECK (credibility_score >= 0.0 AND credibility_score <= 1.0),
    credibility_label TEXT DEFAULT 'medium' CHECK (credibility_label IN ('high', 'medium', 'low')),
    last_fetched TIMESTAMP,
    fetch_count INTEGER DEFAULT 0,
    document_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',  -- JSON object
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (situation_id) REFERENCES situations(id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_situation ON documents(situation_id);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_fetched ON documents(fetched_at);
CREATE INDEX IF NOT EXISTS idx_documents_published ON documents(published_at);

CREATE INDEX IF NOT EXISTS idx_analyses_document ON analyses(document_id);
CREATE INDEX IF NOT EXISTS idx_analyses_situation ON analyses(situation_id);
CREATE INDEX IF NOT EXISTS idx_analyses_sentiment ON analyses(sentiment_score);

CREATE INDEX IF NOT EXISTS idx_alerts_situation ON alerts(situation_id);
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at);

CREATE INDEX IF NOT EXISTS idx_sources_situation ON sources(situation_id);
CREATE INDEX IF NOT EXISTS idx_sources_url ON sources(url);

-- Trigger to update updated_at on situations
CREATE TRIGGER IF NOT EXISTS trigger_situations_updated_at
AFTER UPDATE ON situations
BEGIN
    UPDATE situations SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
