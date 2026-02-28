"""
Storage client for dashboard to interface with Agent 6's storage layer.
Provides read-only access to situations, documents, alerts, and analytics data.
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import asyncio


@dataclass
class Situation:
    id: str
    name: str
    query: str
    status: str  # active, paused, disabled
    created_at: datetime
    updated_at: datetime
    config: Dict[str, Any]
    source_count: int = 0
    document_count: int = 0
    alert_count: int = 0


@dataclass
class Document:
    id: str
    situation_id: str
    source_id: str
    title: str
    content: str
    url: str
    timestamp: datetime
    sentiment: Optional[float] = None
    entities: List[Dict] = None
    keywords: List[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class Alert:
    id: str
    situation_id: str
    rule_id: str
    severity: str
    title: str
    message: str
    timestamp: datetime
    acknowledged: bool = False
    document_id: Optional[str] = None


@dataclass
class SystemHealth:
    timestamp: datetime
    status: str
    active_situations: int
    total_documents: int
    total_alerts: int
    unacknowledged_alerts: int
    storage_connected: bool
    last_error: Optional[str] = None


class DashboardStorageClient:
    """
    Client for reading data from Agent 6's storage layer.
    Read-only interface for dashboard consumption.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize storage client.
        
        Args:
            db_path: Path to SQLite database. If None, uses default location.
        """
        if db_path is None:
            # Default to situation_monitor data directory
            data_dir = Path(__file__).parent.parent / "data"
            db_path = data_dir / "situation_monitor.db"
        
        self.db_path = Path(db_path)
        self._connection: Optional[sqlite3.Connection] = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._connection.row_factory = sqlite3.Row
        return self._connection
    
    def close(self):
        """Close database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None
    
    def check_connection(self) -> bool:
        """Check if database is accessible."""
        try:
            conn = self._get_connection()
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    # ===== Situations =====
    
    def get_situations(
        self, 
        status: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 100
    ) -> List[Situation]:
        """
        Get all situations with optional filtering.
        
        Args:
            status: Filter by status (active, paused, disabled)
            search_query: Search in name/query
            limit: Maximum results
            
        Returns:
            List of Situation objects
        """
        try:
            conn = self._get_connection()
            
            query = """
                SELECT s.*, 
                       COUNT(DISTINCT src.id) as source_count,
                       COUNT(DISTINCT d.id) as document_count,
                       COUNT(DISTINCT a.id) as alert_count
                FROM situations s
                LEFT JOIN sources src ON src.situation_id = s.id
                LEFT JOIN documents d ON d.situation_id = s.id
                LEFT JOIN alerts a ON a.situation_id = s.id
            """
            params = []
            conditions = []
            
            if status:
                conditions.append("s.status = ?")
                params.append(status)
            
            if search_query:
                conditions.append("(s.name LIKE ? OR s.query LIKE ?)")
                params.extend([f"%{search_query}%", f"%{search_query}%"])
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += f" GROUP BY s.id ORDER BY s.updated_at DESC LIMIT {limit}"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            situations = []
            for row in rows:
                situations.append(Situation(
                    id=row['id'],
                    name=row['name'],
                    query=row['query'],
                    status=row['status'],
                    created_at=datetime.fromisoformat(row['created_at']),
                    updated_at=datetime.fromisoformat(row['updated_at']),
                    config=json.loads(row['config']) if row['config'] else {},
                    source_count=row['source_count'] or 0,
                    document_count=row['document_count'] or 0,
                    alert_count=row['alert_count'] or 0
                ))
            
            return situations
            
        except Exception as e:
            # If tables don't exist yet, return empty list
            return []
    
    def get_situation(self, situation_id: str) -> Optional[Situation]:
        """Get a single situation by ID."""
        situations = self.get_situations()
        for s in situations:
            if s.id == situation_id:
                return s
        return None
    
    def get_situation_stats(self, situation_id: str) -> Dict[str, Any]:
        """Get statistics for a specific situation."""
        try:
            conn = self._get_connection()
            
            # Document count by day
            doc_by_day = conn.execute("""
                SELECT DATE(timestamp) as day, COUNT(*) as count
                FROM documents
                WHERE situation_id = ?
                GROUP BY DATE(timestamp)
                ORDER BY day DESC
                LIMIT 30
            """, (situation_id,)).fetchall()
            
            # Alert count by severity
            alerts_by_severity = conn.execute("""
                SELECT severity, COUNT(*) as count
                FROM alerts
                WHERE situation_id = ?
                GROUP BY severity
            """, (situation_id,)).fetchall()
            
            # Sentiment distribution
            sentiment = conn.execute("""
                SELECT 
                    AVG(sentiment) as avg_sentiment,
                    MIN(sentiment) as min_sentiment,
                    MAX(sentiment) as max_sentiment
                FROM documents
                WHERE situation_id = ? AND sentiment IS NOT NULL
            """, (situation_id,)).fetchone()
            
            return {
                'documents_by_day': [{'day': r['day'], 'count': r['count']} for r in doc_by_day],
                'alerts_by_severity': {r['severity']: r['count'] for r in alerts_by_severity},
                'sentiment': {
                    'average': sentiment['avg_sentiment'] if sentiment else 0,
                    'min': sentiment['min_sentiment'] if sentiment else 0,
                    'max': sentiment['max_sentiment'] if sentiment else 0,
                }
            }
        except Exception:
            return {'documents_by_day': [], 'alerts_by_severity': {}, 'sentiment': {}}
    
    # ===== Documents =====
    
    def get_documents(
        self,
        situation_id: Optional[str] = None,
        source_id: Optional[str] = None,
        search_query: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Document]:
        """Get documents with filtering."""
        try:
            conn = self._get_connection()
            
            query = "SELECT * FROM documents WHERE 1=1"
            params = []
            
            if situation_id:
                query += " AND situation_id = ?"
                params.append(situation_id)
            
            if source_id:
                query += " AND source_id = ?"
                params.append(source_id)
            
            if search_query:
                query += " AND (title LIKE ? OR content LIKE ?)"
                params.extend([f"%{search_query}%", f"%{search_query}%"])
            
            if since:
                query += " AND timestamp >= ?"
                params.append(since.isoformat())
            
            if until:
                query += " AND timestamp <= ?"
                params.append(until.isoformat())
            
            query += f" ORDER BY timestamp DESC LIMIT {limit} OFFSET {offset}"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            documents = []
            for row in rows:
                documents.append(Document(
                    id=row['id'],
                    situation_id=row['situation_id'],
                    source_id=row['source_id'],
                    title=row['title'] or '',
                    content=row['content'] or '',
                    url=row['url'] or '',
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    sentiment=row['sentiment'],
                    entities=json.loads(row['entities']) if row['entities'] else [],
                    keywords=json.loads(row['keywords']) if row['keywords'] else [],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                ))
            
            return documents
            
        except Exception:
            return []
    
    def get_document(self, document_id: str) -> Optional[Document]:
        """Get a single document by ID."""
        try:
            conn = self._get_connection()
            row = conn.execute(
                "SELECT * FROM documents WHERE id = ?", 
                (document_id,)
            ).fetchone()
            
            if row:
                return Document(
                    id=row['id'],
                    situation_id=row['situation_id'],
                    source_id=row['source_id'],
                    title=row['title'] or '',
                    content=row['content'] or '',
                    url=row['url'] or '',
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    sentiment=row['sentiment'],
                    entities=json.loads(row['entities']) if row['entities'] else [],
                    keywords=json.loads(row['keywords']) if row['keywords'] else [],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {}
                )
            return None
        except Exception:
            return None
    
    # ===== Alerts =====
    
    def get_alerts(
        self,
        situation_id: Optional[str] = None,
        acknowledged: Optional[bool] = None,
        severity: Optional[str] = None,
        limit: int = 100
    ) -> List[Alert]:
        """Get alerts with filtering."""
        try:
            conn = self._get_connection()
            
            query = "SELECT * FROM alerts WHERE 1=1"
            params = []
            
            if situation_id:
                query += " AND situation_id = ?"
                params.append(situation_id)
            
            if acknowledged is not None:
                query += " AND acknowledged = ?"
                params.append(1 if acknowledged else 0)
            
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            
            query += f" ORDER BY timestamp DESC LIMIT {limit}"
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            alerts = []
            for row in rows:
                alerts.append(Alert(
                    id=row['id'],
                    situation_id=row['situation_id'],
                    rule_id=row['rule_id'],
                    severity=row['severity'],
                    title=row['title'],
                    message=row['message'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    acknowledged=bool(row['acknowledged']),
                    document_id=row.get('document_id')
                ))
            
            return alerts
            
        except Exception:
            return []
    
    def get_recent_alerts(self, hours: int = 24, limit: int = 50) -> List[Alert]:
        """Get alerts from the last N hours."""
        since = datetime.utcnow() - timedelta(hours=hours)
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                """SELECT * FROM alerts 
                   WHERE timestamp >= ? 
                   ORDER BY timestamp DESC LIMIT ?""",
                (since.isoformat(), limit)
            )
            rows = cursor.fetchall()
            
            alerts = []
            for row in rows:
                alerts.append(Alert(
                    id=row['id'],
                    situation_id=row['situation_id'],
                    rule_id=row['rule_id'],
                    severity=row['severity'],
                    title=row['title'],
                    message=row['message'],
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    acknowledged=bool(row['acknowledged']),
                    document_id=row.get('document_id')
                ))
            return alerts
        except Exception:
            return []
    
    # ===== Analytics =====
    
    def get_sentiment_trend(
        self, 
        situation_id: str, 
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get daily sentiment averages for a situation."""
        try:
            conn = self._get_connection()
            since = datetime.utcnow() - timedelta(days=days)
            
            cursor = conn.execute("""
                SELECT 
                    DATE(timestamp) as day,
                    AVG(sentiment) as avg_sentiment,
                    COUNT(*) as count
                FROM documents
                WHERE situation_id = ? 
                  AND timestamp >= ?
                  AND sentiment IS NOT NULL
                GROUP BY DATE(timestamp)
                ORDER BY day
            """, (situation_id, since.isoformat()))
            
            return [
                {
                    'day': row['day'],
                    'sentiment': row['avg_sentiment'],
                    'count': row['count']
                }
                for row in cursor.fetchall()
            ]
        except Exception:
            return []
    
    def get_keyword_frequency(
        self, 
        situation_id: str, 
        top_n: int = 20
    ) -> List[Dict[str, Any]]:
        """Get most frequent keywords for a situation."""
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT keywords FROM documents WHERE situation_id = ? AND keywords IS NOT NULL",
                (situation_id,)
            )
            
            keyword_counts = {}
            for row in cursor.fetchall():
                keywords = json.loads(row['keywords'])
                for kw in keywords:
                    keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
            
            # Sort by frequency and return top N
            sorted_keywords = sorted(
                keyword_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:top_n]
            
            return [
                {'keyword': kw, 'count': count}
                for kw, count in sorted_keywords
            ]
        except Exception:
            return []
    
    def get_entity_timeline(
        self, 
        situation_id: str, 
        days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get entity mentions over time."""
        try:
            conn = self._get_connection()
            since = datetime.utcnow() - timedelta(days=days)
            
            cursor = conn.execute("""
                SELECT 
                    DATE(timestamp) as day,
                    entities
                FROM documents
                WHERE situation_id = ? 
                  AND timestamp >= ?
                  AND entities IS NOT NULL
                ORDER BY day
            """, (situation_id, since.isoformat()))
            
            timeline = {}
            for row in cursor.fetchall():
                day = row['day']
                entities = json.loads(row['entities'])
                
                if day not in timeline:
                    timeline[day] = {}
                
                for entity in entities:
                    name = entity.get('name', entity.get('text', 'Unknown'))
                    timeline[day][name] = timeline[day].get(name, 0) + 1
            
            # Convert to list format
            result = []
            for day, entities in sorted(timeline.items()):
                for entity, count in entities.items():
                    result.append({'day': day, 'entity': entity, 'count': count})
            
            return result
        except Exception:
            return []
    
    def get_activity_heatmap(
        self, 
        situation_id: str, 
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get document activity by day and hour."""
        try:
            conn = self._get_connection()
            since = datetime.utcnow() - timedelta(days=days)
            
            cursor = conn.execute("""
                SELECT 
                    DATE(timestamp) as day,
                    CAST(strftime('%H', timestamp) AS INTEGER) as hour,
                    COUNT(*) as count
                FROM documents
                WHERE situation_id = ? AND timestamp >= ?
                GROUP BY day, hour
                ORDER BY day, hour
            """, (situation_id, since.isoformat()))
            
            return [
                {'day': row['day'], 'hour': row['hour'], 'count': row['count']}
                for row in cursor.fetchall()
            ]
        except Exception:
            return []
    
    # ===== System Health =====
    
    def get_system_health(self) -> SystemHealth:
        """Get overall system health status."""
        try:
            conn = self._get_connection()
            
            # Count active situations
            active_situations = conn.execute(
                "SELECT COUNT(*) as count FROM situations WHERE status = 'active'"
            ).fetchone()['count'] or 0
            
            # Count total documents
            total_docs = conn.execute(
                "SELECT COUNT(*) as count FROM documents"
            ).fetchone()['count'] or 0
            
            # Count total alerts
            total_alerts = conn.execute(
                "SELECT COUNT(*) as count FROM alerts"
            ).fetchone()['count'] or 0
            
            # Count unacknowledged alerts
            unack_alerts = conn.execute(
                "SELECT COUNT(*) as count FROM alerts WHERE acknowledged = 0"
            ).fetchone()['count'] or 0
            
            # Check storage connection
            storage_connected = self.check_connection()
            
            # Get last error from logs
            last_error = None
            try:
                error_row = conn.execute(
                    "SELECT message FROM logs WHERE level = 'ERROR' ORDER BY timestamp DESC LIMIT 1"
                ).fetchone()
                if error_row:
                    last_error = error_row['message']
            except:
                pass
            
            # Determine overall status
            if not storage_connected:
                status = "error"
            elif unack_alerts > 10:
                status = "warning"
            else:
                status = "healthy"
            
            return SystemHealth(
                timestamp=datetime.utcnow(),
                status=status,
                active_situations=active_situations,
                total_documents=total_docs,
                total_alerts=total_alerts,
                unacknowledged_alerts=unack_alerts,
                storage_connected=storage_connected,
                last_error=last_error
            )
            
        except Exception as e:
            return SystemHealth(
                timestamp=datetime.utcnow(),
                status="error",
                active_situations=0,
                total_documents=0,
                total_alerts=0,
                unacknowledged_alerts=0,
                storage_connected=False,
                last_error=str(e)
            )
    
    # ===== Logs =====
    
    def get_logs(
        self, 
        level: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get system logs."""
        try:
            conn = self._get_connection()
            
            query = "SELECT * FROM logs WHERE 1=1"
            params = []
            
            if level:
                query += " AND level = ?"
                params.append(level.upper())
            
            if since:
                query += " AND timestamp >= ?"
                params.append(since.isoformat())
            
            query += f" ORDER BY timestamp DESC LIMIT {limit}"
            
            cursor = conn.execute(query, params)
            return [
                {
                    'timestamp': row['timestamp'],
                    'level': row['level'],
                    'message': row['message'],
                    'source': row.get('source', 'unknown'),
                    'metadata': json.loads(row['metadata']) if row.get('metadata') else {}
                }
                for row in cursor.fetchall()
            ]
        except Exception:
            return []


# Singleton instance
_storage_client: Optional[DashboardStorageClient] = None


def get_storage_client(db_path: Optional[str] = None) -> DashboardStorageClient:
    """Get singleton storage client instance."""
    global _storage_client
    if _storage_client is None:
        _storage_client = DashboardStorageClient(db_path)
    return _storage_client
