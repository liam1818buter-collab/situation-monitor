"""
Situation Monitor Dashboard - Main Application
Streamlit-based visualization interface for monitoring situations and exploring data.
"""

import streamlit as st
from datetime import datetime
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Page configuration - MUST be first st command
st.set_page_config(
    page_title="Situation Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/situation-monitor',
        'Report a bug': 'https://github.com/situation-monitor/issues',
        'About': '# Situation Monitor\nZero-cost autonomous monitoring system'
    }
)

# Custom CSS for styling
st.markdown("""
<style>
    /* Main container */
    .main > div {
        padding: 2rem 3rem;
    }
    
    /* Headers */
    h1 {
        color: #1f2937;
        font-weight: 700;
    }
    h2 {
        color: #374151;
        font-weight: 600;
    }
    h3 {
        color: #4b5563;
        font-weight: 600;
    }
    
    /* Metric cards */
    .stMetric {
        background-color: #f9fafb;
        border-radius: 0.5rem;
        padding: 1rem;
        border: 1px solid #e5e7eb;
    }
    
    /* Status badges */
    .status-active {
        color: #059669;
        font-weight: 600;
    }
    .status-paused {
        color: #d97706;
        font-weight: 600;
    }
    .status-error {
        color: #dc2626;
        font-weight: 600;
    }
    .status-disabled {
        color: #6b7280;
        font-weight: 600;
    }
    
    /* Severity badges */
    .severity-info {
        color: #3b82f6;
        font-weight: 600;
    }
    .severity-warning {
        color: #f59e0b;
        font-weight: 600;
    }
    .severity-error {
        color: #ef4444;
        font-weight: 600;
    }
    .severity-critical {
        color: #7f1d1d;
        font-weight: 700;
    }
    
    /* Alert cards */
    .alert-card {
        border-left: 4px solid;
        padding: 1rem;
        margin-bottom: 0.5rem;
        background-color: #f9fafb;
        border-radius: 0 0.375rem 0.375rem 0;
    }
    .alert-info { border-left-color: #3b82f6; }
    .alert-warning { border-left-color: #f59e0b; }
    .alert-error { border-left-color: #ef4444; }
    .alert-critical { border-left-color: #7f1d1d; }
    
    /* Dataframe styling */
    .stDataFrame {
        font-size: 0.875rem;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background-color: #f3f4f6;
    }
    
    /* Auto-refresh indicator */
    .refresh-indicator {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.75rem;
        color: #6b7280;
    }
    
    /* Document card */
    .document-card {
        border: 1px solid #e5e7eb;
        border-radius: 0.5rem;
        padding: 1rem;
        margin-bottom: 1rem;
        background-color: white;
    }
    
    /* Sentiment indicators */
    .sentiment-positive {
        color: #059669;
    }
    .sentiment-negative {
        color: #dc2626;
    }
    .sentiment-neutral {
        color: #6b7280;
    }
</style>
""", unsafe_allow_html=True)

from dashboard.storage_client import get_storage_client, SystemHealth


def get_status_color(status: str) -> str:
    """Get CSS class for status."""
    return f"status-{status.lower()}"


def get_severity_color(severity: str) -> str:
    """Get CSS class for severity."""
    return f"severity-{severity.lower()}"


def render_sidebar():
    """Render the sidebar navigation and controls."""
    with st.sidebar:
        st.markdown("# 📊 Situation Monitor")
        st.caption("Zero-cost autonomous monitoring")
        st.caption("Zero-cost autonomous monitoring")
        
        st.divider()
        
        # Navigation
        st.subheader("Navigation")
        
        pages = {
            "🏠 Home": "home",
            "📋 Situations": "situations",
            "🔍 Documents": "documents",
            "🚨 Alerts": "alerts",
            "📈 Analytics": "analytics",
            "📝 Logs": "logs",
            "⚙️ Settings": "settings"
        }
        
        for label, page_id in pages.items():
            if st.button(label, key=f"nav_{page_id}", use_container_width=True):
                st.session_state.current_page = page_id
                st.rerun()
        
        st.divider()
        
        # Quick stats
        storage = get_storage_client()
        health = storage.get_system_health()
        
        st.subheader("System Status")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Active", health.active_situations)
        with col2:
            st.metric("Alerts", health.unacknowledged_alerts, 
                     delta=f"{health.unacknowledged_alerts} unack" if health.unacknowledged_alerts > 0 else None)
        
        # Storage status indicator
        if health.storage_connected:
            st.success("🟢 Storage Connected")
        else:
            st.error("🔴 Storage Disconnected")
        
        st.divider()
        
        # Auto-refresh toggle
        st.subheader("Auto-Refresh")
        auto_refresh = st.toggle("Enable (60s)", value=st.session_state.get('auto_refresh', True))
        st.session_state.auto_refresh = auto_refresh
        
        if auto_refresh:
            st.caption("⏱️ Refreshes every 60 seconds")
            st_autorefresh = True
        
        st.divider()
        
        # Version info
        st.caption("v0.1.0 | Built with Streamlit")


def render_home():
    """Render the home/dashboard overview page."""
    st.title("🏠 Dashboard Overview")
    
    storage = get_storage_client()
    health = storage.get_system_health()
    
    # Summary metrics
    st.subheader("System Overview")
    
    cols = st.columns(4)
    with cols[0]:
        st.metric(
            "Active Situations", 
            health.active_situations,
            help="Number of currently monitored situations"
        )
    with cols[1]:
        st.metric(
            "Total Documents", 
            f"{health.total_documents:,}",
            help="Total documents collected across all situations"
        )
    with cols[2]:
        st.metric(
            "Total Alerts", 
            f"{health.total_alerts:,}",
            help="Total alerts generated"
        )
    with cols[3]:
        st.metric(
            "Unacknowledged", 
            health.unacknowledged_alerts,
            delta=f"{health.unacknowledged_alerts} need attention" if health.unacknowledged_alerts > 0 else "All caught up!",
            delta_color="inverse",
            help="Alerts requiring acknowledgment"
        )
    
    st.divider()
    
    # Recent alerts
    st.subheader("🚨 Recent Alerts (24h)")
    
    recent_alerts = storage.get_recent_alerts(hours=24, limit=10)
    
    if recent_alerts:
        for alert in recent_alerts:
            severity_class = get_severity_color(alert.severity)
            acknowledged_icon = "✓" if alert.acknowledged else "○"
            
            with st.container():
                st.markdown(f"""
                <div class="alert-card alert-{alert.severity.lower()}">
                    <div style="display: flex; justify-content: space-between; align-items: start;">
                        <div>
                            <span class="{severity_class}">{alert.severity.upper()}</span>
                            <strong>{alert.title}</strong>
                            <br/><small>{alert.timestamp.strftime('%Y-%m-%d %H:%M')}</small>
                        </div>
                        <span style="font-size: 1.2rem;">{acknowledged_icon}</span>
                    </div>
                    <p style="margin: 0.5rem 0 0 0; color: #4b5563;">{alert.message}</p>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No alerts in the last 24 hours")
    
    st.divider()
    
    # Quick actions
    st.subheader("⚡ Quick Actions")
    
    cols = st.columns(4)
    with cols[0]:
        if st.button("➕ New Situation", use_container_width=True):
            st.session_state.current_page = "situations"
            st.session_state.show_create = True
            st.rerun()
    with cols[1]:
        if st.button("🔍 Search Docs", use_container_width=True):
            st.session_state.current_page = "documents"
            st.rerun()
    with cols[2]:
        if st.button("📊 View Analytics", use_container_width=True):
            st.session_state.current_page = "analytics"
            st.rerun()
    with cols[3]:
        if st.button("📝 View Logs", use_container_width=True):
            st.session_state.current_page = "logs"
            st.rerun()
    
    st.divider()
    
    # System health
    st.subheader("💓 System Health")
    
    health_cols = st.columns(3)
    with health_cols[0]:
        if health.status == "healthy":
            st.success("Status: Healthy")
        elif health.status == "warning":
            st.warning("Status: Warning")
        else:
            st.error(f"Status: {health.status.title()}")
    
    with health_cols[1]:
        if health.storage_connected:
            st.success("Storage: Connected")
        else:
            st.error("Storage: Disconnected")
    
    with health_cols[2]:
        st.info(f"Last Updated: {health.timestamp.strftime('%H:%M:%S')}")
    
    if health.last_error:
        st.error(f"Last Error: {health.last_error}")


def render_situations():
    """Render the situations management page."""
    import dashboard.pages.situations as situations_page
    situations_page.render()


def render_documents():
    """Render the document browser page."""
    import dashboard.pages.documents as documents_page
    documents_page.render()


def render_alerts():
    """Render the alerts page."""
    import dashboard.pages.alerts as alerts_page
    alerts_page.render()


def render_analytics():
    """Render the analytics page."""
    import dashboard.pages.analytics as analytics_page
    analytics_page.render()


def render_logs():
    """Render the system logs page."""
    import dashboard.pages.logs as logs_page
    logs_page.render()


def render_settings():
    """Render the settings page."""
    import dashboard.pages.settings as settings_page
    settings_page.render()


def main():
    """Main application entry point."""
    # Initialize session state
    if 'current_page' not in st.session_state:
        st.session_state.current_page = "home"
    
    if 'auto_refresh' not in st.session_state:
        st.session_state.auto_refresh = True
    
    # Render sidebar
    render_sidebar()
    
    # Auto-refresh logic
    if st.session_state.get('auto_refresh', True):
        st.empty()  # Trigger placeholder for refresh
        import time
        # Use JavaScript for auto-refresh to avoid full rerun issues
        st.markdown(
            """
            <script>
                setTimeout(function() {
                    window.location.reload();
                }, 60000);
            </script>
            """,
            unsafe_allow_html=True
        )
    
    # Route to current page
    page = st.session_state.current_page
    
    if page == "home":
        render_home()
    elif page == "situations":
        render_situations()
    elif page == "documents":
        render_documents()
    elif page == "alerts":
        render_alerts()
    elif page == "analytics":
        render_analytics()
    elif page == "logs":
        render_logs()
    elif page == "settings":
        render_settings()
    else:
        render_home()


if __name__ == "__main__":
    main()
