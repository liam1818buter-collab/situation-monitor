"""
Logs page - System logs and error tracking.
"""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.storage_client import get_storage_client


def get_level_color(level: str) -> str:
    """Get color for log level."""
    return {
        'DEBUG': '#6b7280',
        'INFO': '#3b82f6',
        'WARNING': '#f59e0b',
        'ERROR': '#ef4444',
        'CRITICAL': '#7f1d1d'
    }.get(level.upper(), '#6b7280')


def get_level_emoji(level: str) -> str:
    """Get emoji for log level."""
    return {
        'DEBUG': '🔍',
        'INFO': 'ℹ️',
        'WARNING': '⚠️',
        'ERROR': '❌',
        'CRITICAL': '🚨'
    }.get(level.upper(), 'ℹ️')


def render():
    """Main render function for logs page."""
    st.title("📝 System Logs")
    st.caption("View system logs and error tracking")
    
    storage = get_storage_client()
    
    # Filters
    with st.expander("🔍 Filters", expanded=True):
        col1, col2, col3 = st.columns([2, 2, 2])
        
        with col1:
            level_filter = st.multiselect(
                "Log Level",
                ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                default=["INFO", "WARNING", "ERROR", "CRITICAL"],
                key="log_level"
            )
        
        with col2:
            source_filter = st.text_input(
                "Source Filter",
                placeholder="Filter by source...",
                key="log_source"
            )
        
        with col3:
            time_filter = st.selectbox(
                "Time Range",
                ["Last 1 hour", "Last 6 hours", "Last 24 hours", "Last 7 days", "All"],
                key="log_time"
            )
        
        # Search in message
        search_query = st.text_input(
            "Search in messages",
            placeholder="Search log messages...",
            key="log_search"
        )
    
    # Determine since time
    since = None
    if time_filter == "Last 1 hour":
        since = datetime.utcnow() - timedelta(hours=1)
    elif time_filter == "Last 6 hours":
        since = datetime.utcnow() - timedelta(hours=6)
    elif time_filter == "Last 24 hours":
        since = datetime.utcnow() - timedelta(hours=24)
    elif time_filter == "Last 7 days":
        since = datetime.utcnow() - timedelta(days=7)
    
    # Get logs
    logs = storage.get_logs(since=since, limit=500)
    
    # Apply level filter
    if level_filter:
        logs = [log for log in logs if log['level'] in level_filter]
    
    # Apply source filter
    if source_filter:
        logs = [log for log in logs if source_filter.lower() in log.get('source', '').lower()]
    
    # Apply search
    if search_query:
        logs = [log for log in logs if search_query.lower() in log['message'].lower()]
    
    # Summary stats
    st.divider()
    
    if logs:
        error_count = len([l for l in logs if l['level'] == 'ERROR'])
        warning_count = len([l for l in logs if l['level'] == 'WARNING'])
        
        cols = st.columns(4)
        with cols[0]:
            st.metric("Total Logs", len(logs))
        with cols[1]:
            st.metric("Errors", error_count, delta=f"{error_count} errors" if error_count else None, delta_color="inverse")
        with cols[2]:
            st.metric("Warnings", warning_count, delta=f"{warning_count} warnings" if warning_count else None, delta_color="off")
        with cols[3]:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()
    
    # Display logs
    st.divider()
    
    # Export
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader(f"Log Entries ({len(logs)})")
    with col2:
        if logs:
            df = pd.DataFrame(logs)
            st.download_button(
                "📥 Export",
                df.to_csv(index=False),
                file_name=f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    
    if logs:
        # Create a dataframe for display
        df = pd.DataFrame(logs)
        
        # Add color column
        df['color'] = df['level'].apply(get_level_color)
        
        # Display as styled table
        st.dataframe(
            df[['timestamp', 'level', 'source', 'message']],
            column_config={
                'timestamp': st.column_config.DatetimeColumn("Time", width="medium"),
                'level': st.column_config.TextColumn("Level", width="small"),
                'source': st.column_config.TextColumn("Source", width="medium"),
                'message': st.column_config.TextColumn("Message", width="large")
            },
            use_container_width=True,
            hide_index=True
        )
        
        # Detailed log view
        st.divider()
        st.subheader("Detailed View")
        
        for log in logs[:50]:  # Show last 50
            color = get_level_color(log['level'])
            emoji = get_level_emoji(log['level'])
            
            with st.container():
                cols = st.columns([1, 4, 4])
                with cols[0]:
                    st.markdown(f"<span style='color: {color};'>{emoji} {log['level']}</span>", unsafe_allow_html=True)
                with cols[1]:
                    st.caption(log['timestamp'])
                with cols[2]:
                    st.caption(f"Source: {log.get('source', 'unknown')}")
                
                st.text(log['message'])
                
                # Show metadata if available
                if log.get('metadata'):
                    with st.expander("Metadata"):
                        st.json(log['metadata'])
                
                st.divider()
    else:
        st.info("No logs match your filters.")
        
        if not storage.check_connection():
            st.error("Unable to connect to storage. Logs will appear here once the system is running and connected.")
