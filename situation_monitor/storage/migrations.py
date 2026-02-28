"""
Database migration system for Situation Monitor.

Supports simple versioned SQL migrations for SQLite and PostgreSQL.
"""

import os
import re
import aiosqlite
from typing import List, Optional, Tuple
from datetime import datetime
from pathlib import Path


class MigrationManager:
    """
    Manages database schema migrations.
    
    Uses simple versioned SQL files with format:
    V{version}__{description}.sql
    
    Example:
        V1__initial_schema.sql
        V2__add_ft5_search.sql
    """
    
    def __init__(self, db_path: str, migrations_dir: Optional[str] = None):
        self.db_path = db_path
        self.migrations_dir = migrations_dir or os.path.join(
            os.path.dirname(__file__), "migrations"
        )
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def _get_connection(self) -> aiosqlite.Connection:
        """Get or create database connection."""
        if self._connection is None:
            self._connection = await aiosqlite.connect(self.db_path)
            self._connection.row_factory = aiosqlite.Row
        return self._connection
    
    async def _init_migrations_table(self) -> None:
        """Create the migrations tracking table."""
        conn = await self._get_connection()
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS _migrations (
                version INTEGER PRIMARY KEY,
                description TEXT NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                checksum TEXT
            )
        """)
        await conn.commit()
    
    async def _get_applied_migrations(self) -> List[int]:
        """Get list of already applied migration versions."""
        conn = await self._get_connection()
        try:
            cursor = await conn.execute(
                "SELECT version FROM _migrations ORDER BY version"
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
        except aiosqlite.OperationalError:
            # Table doesn't exist yet
            return []
    
    def _get_available_migrations(self) -> List[Tuple[int, str, str]]:
        """
        Get list of available migration files.
        
        Returns:
            List of (version, description, filepath) tuples
        """
        migrations = []
        pattern = re.compile(r'V(\d+)__(.+)\.sql$')
        
        if not os.path.exists(self.migrations_dir):
            return migrations
        
        for filename in sorted(os.listdir(self.migrations_dir)):
            match = pattern.match(filename)
            if match:
                version = int(match.group(1))
                description = match.group(2).replace('_', ' ')
                filepath = os.path.join(self.migrations_dir, filename)
                migrations.append((version, description, filepath))
        
        return migrations
    
    async def migrate(self, target_version: Optional[int] = None) -> List[str]:
        """
        Run pending migrations.
        
        Args:
            target_version: Specific version to migrate to (None = latest)
            
        Returns:
            List of applied migration descriptions
        """
        await self._init_migrations_table()
        
        applied = set(await self._get_applied_migrations())
        available = self._get_available_migrations()
        
        applied_migrations = []
        conn = await self._get_connection()
        
        for version, description, filepath in available:
            # Skip if already applied
            if version in applied:
                continue
            
            # Stop if we've reached target version
            if target_version and version > target_version:
                break
            
            # Read and execute migration
            with open(filepath, 'r') as f:
                sql = f.read()
            
            # Execute migration in transaction
            try:
                # Split by semicolon to handle multiple statements
                statements = [s.strip() for s in sql.split(';') if s.strip()]
                for statement in statements:
                    await conn.execute(statement)
                
                # Record migration
                await conn.execute(
                    "INSERT INTO _migrations (version, description) VALUES (?, ?)",
                    (version, description)
                )
                await conn.commit()
                
                applied_migrations.append(f"V{version}: {description}")
                
            except Exception as e:
                await conn.rollback()
                raise MigrationError(
                    f"Failed to apply migration V{version} ({description}): {e}"
                )
        
        return applied_migrations
    
    async def rollback(self, steps: int = 1) -> List[str]:
        """
        Rollback migrations.
        
        Args:
            steps: Number of migrations to rollback
            
        Returns:
            List of rolled back migration descriptions
        """
        # Note: SQLite doesn't support transactional DDL rollback
        # This is a simplified implementation
        conn = await self._get_connection()
        
        cursor = await conn.execute(
            "SELECT version, description FROM _migrations ORDER BY version DESC LIMIT ?",
            (steps,)
        )
        to_rollback = await cursor.fetchall()
        
        rolled_back = []
        for version, description in to_rollback:
            # Look for rollback file
            rollback_file = os.path.join(
                self.migrations_dir, f"V{version}__{description.replace(' ', '_')}.rollback.sql"
            )
            
            if os.path.exists(rollback_file):
                with open(rollback_file, 'r') as f:
                    sql = f.read()
                
                statements = [s.strip() for s in sql.split(';') if s.strip()]
                for statement in statements:
                    await conn.execute(statement)
            
            # Remove migration record
            await conn.execute(
                "DELETE FROM _migrations WHERE version = ?",
                (version,)
            )
            await conn.commit()
            
            rolled_back.append(f"V{version}: {description}")
        
        return rolled_back
    
    async def status(self) -> dict:
        """Get current migration status."""
        await self._init_migrations_table()
        
        applied = await self._get_applied_migrations()
        available = self._get_available_migrations()
        
        pending = [v for v, _, _ in available if v not in applied]
        
        return {
            "current_version": max(applied) if applied else 0,
            "latest_version": max([v for v, _, _ in available]) if available else 0,
            "applied_count": len(applied),
            "pending_count": len(pending),
            "pending_versions": pending
        }
    
    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None


class MigrationError(Exception):
    """Raised when a migration fails."""
    pass


async def create_migration(
    description: str,
    migrations_dir: Optional[str] = None,
    sql_content: str = ""
) -> str:
    """
    Create a new migration file.
    
    Args:
        description: Brief description of the migration
        migrations_dir: Directory to create migration in
        sql_content: SQL content for the migration
        
    Returns:
        Path to created migration file
    """
    migrations_dir = migrations_dir or os.path.join(
        os.path.dirname(__file__), "migrations"
    )
    
    os.makedirs(migrations_dir, exist_ok=True)
    
    # Get next version number
    existing = [f for f in os.listdir(migrations_dir) if f.endswith('.sql')]
    versions = []
    for f in existing:
        match = re.match(r'V(\d+)__', f)
        if match:
            versions.append(int(match.group(1)))
    
    next_version = max(versions, default=0) + 1
    
    # Create filename
    safe_description = description.replace(' ', '_').lower()
    filename = f"V{next_version}__{safe_description}.sql"
    filepath = os.path.join(migrations_dir, filename)
    
    # Write migration file with header
    header = f"""-- Migration V{next_version}: {description}
-- Created: {datetime.utcnow().isoformat()}

"""
    
    with open(filepath, 'w') as f:
        f.write(header + sql_content)
    
    return filepath
