-- Migration V4: Time Series and Analytics
-- Created: 2026-02-28
-- Adds tables for time-series analytics and trend tracking

-- Aggregated daily metrics for situations
CREATE TABLE IF NOT EXISTS situation_metrics_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    situation_id TEXT NOT NULL,
    date TEXT NOT NULL,  -- ISO format YYYY-MM-DD
    document_count INTEGER DEFAULT 0,
    source_count INTEGER DEFAULT 0,
    alert_count INTEGER DEFAULT 0,
    avg_sentiment REAL,
    sentiment_positive_count INTEGER DEFAULT 0,
    sentiment_negative_count INTEGER DEFAULT 0,
    sentiment_neutral_count INTEGER DEFAULT 0,
    top_keywords TEXT NOT NULL DEFAULT '[]',  -- JSON array
    top_entities TEXT NOT NULL DEFAULT '[]',  -- JSON array
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(situation_id, date)
);

-- Hourly metrics for recent data (kept for 30 days)
CREATE TABLE IF NOT EXISTS situation_metrics_hourly (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    situation_id TEXT NOT NULL,
    hour TEXT NOT NULL,  -- ISO format YYYY-MM-DDTHH
    document_count INTEGER DEFAULT 0,
    alert_count INTEGER DEFAULT 0,
    avg_sentiment REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(situation_id, hour)
);

-- Detected trends/anomalies
CREATE TABLE IF NOT EXISTS trends (
    id TEXT PRIMARY KEY,
    situation_id TEXT NOT NULL,
    metric TEXT NOT NULL,  -- sentiment, volume, mentions, etc.
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    trend_direction TEXT NOT NULL,  -- increasing, decreasing, stable
    trend_strength REAL NOT NULL CHECK (trend_strength >= 0.0 AND trend_strength <= 1.0),
    anomaly_detected BOOLEAN DEFAULT FALSE,
    anomaly_score REAL,
    details TEXT NOT NULL DEFAULT '{}',  -- JSON object
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (situation_id) REFERENCES situations(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_metrics_daily_situation ON situation_metrics_daily(situation_id);
CREATE INDEX IF NOT EXISTS idx_metrics_daily_date ON situation_metrics_daily(date);
CREATE INDEX IF NOT EXISTS idx_metrics_hourly_situation ON situation_metrics_hourly(situation_id);
CREATE INDEX IF NOT EXISTS idx_metrics_hourly_hour ON situation_metrics_hourly(hour);
CREATE INDEX IF NOT EXISTS idx_trends_situation ON trends(situation_id);
CREATE INDEX IF NOT EXISTS idx_trends_metric ON trends(metric);
CREATE INDEX IF NOT EXISTS idx_trends_created ON trends(created_at);
