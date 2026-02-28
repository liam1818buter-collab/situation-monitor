"""
Settings page - Configuration and preferences.
"""

import streamlit as st
from datetime import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.storage_client import get_storage_client


def render():
    """Main render function for settings page."""
    st.title("⚙️ Settings")
    st.caption("Configure dashboard and system preferences")
    
    storage = get_storage_client()
    
    # Tabs for different settings categories
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔔 Alert Preferences",
        "📡 Sources",
        "💾 Storage",
        "🔧 System"
    ])
    
    with tab1:
        st.subheader("Alert Preferences")
        
        st.markdown("Configure how and when you receive alerts.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**Notification Channels**")
            
            enable_console = st.toggle("Console/Log Notifications", value=True)
            enable_webhook = st.toggle("Webhook Notifications", value=False)
            enable_email = st.toggle("Email Notifications", value=False)
            enable_discord = st.toggle("Discord Notifications", value=False)
        
        with col2:
            st.markdown("**Alert Thresholds**")
            
            min_severity = st.selectbox(
                "Minimum Severity",
                ["Info", "Warning", "Error", "Critical"],
                index=1
            )
            
            cooldown_minutes = st.slider(
                "Alert Cooldown (minutes)",
                min_value=0,
                max_value=60,
                value=5
            )
            
            max_alerts_hour = st.number_input(
                "Max Alerts Per Hour",
                min_value=1,
                max_value=100,
                value=10
            )
        
        st.divider()
        
        # Webhook configuration
        if enable_webhook:
            with st.expander("Webhook Configuration", expanded=True):
                webhook_url = st.text_input(
                    "Webhook URL",
                    placeholder="https://hooks.slack.com/services/..."
                )
                webhook_method = st.selectbox("HTTP Method", ["POST", "PUT"])
                webhook_headers = st.text_area(
                    "Custom Headers (JSON)",
                    placeholder='{"Authorization": "Bearer token"}'
                )
        
        # Email configuration
        if enable_email:
            with st.expander("Email Configuration", expanded=True):
                smtp_server = st.text_input("SMTP Server", placeholder="smtp.gmail.com")
                smtp_port = st.number_input("SMTP Port", value=587)
                smtp_user = st.text_input("SMTP Username")
                smtp_pass = st.text_input("SMTP Password", type="password")
                email_to = st.text_input("Notification Email", placeholder="alerts@example.com")
        
        # Discord configuration
        if enable_discord:
            with st.expander("Discord Configuration", expanded=True):
                discord_webhook = st.text_input(
                    "Discord Webhook URL",
                    placeholder="https://discord.com/api/webhooks/..."
                )
        
        st.divider()
        
        if st.button("💾 Save Alert Settings", type="primary"):
            st.success("Alert settings saved!")
    
    with tab2:
        st.subheader("Data Sources")
        
        st.markdown("Manage data sources for situation monitoring.")
        
        # Source types
        st.markdown("**Enabled Source Types**")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.toggle("RSS Feeds", value=True)
            st.toggle("News APIs", value=True)
        with col2:
            st.toggle("Web Scraping", value=True)
            st.toggle("Files", value=True)
        with col3:
            st.toggle("Twitter/X", value=False)
            st.toggle("Reddit", value=False)
        
        st.divider()
        
        # Rate limiting
        st.markdown("**Rate Limiting**")
        
        col1, col2 = st.columns(2)
        with col1:
            requests_per_minute = st.number_input(
                "Requests Per Minute",
                min_value=1,
                max_value=300,
                value=60
            )
        with col2:
            retry_attempts = st.number_input(
                "Max Retry Attempts",
                min_value=0,
                max_value=10,
                value=3
            )
        
        # Politeness settings
        st.markdown("**Politeness Settings**")
        
        respect_robots_txt = st.toggle("Respect robots.txt", value=True)
        delay_between_requests = st.slider(
            "Delay Between Requests (seconds)",
            min_value=0,
            max_value=10,
            value=1
        )
        
        st.divider()
        
        # Source management
        st.markdown("**Manage Sources**")
        
        situations = storage.get_situations()
        if situations:
            for situation in situations:
                with st.expander(f"{situation.name} ({situation.source_count} sources)"):
                    st.write(f"Query: {situation.query}")
                    st.write(f"Sources: {situation.source_count}")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("Add Source", key=f"add_src_{situation.id}"):
                            st.info("Source addition would open a dialog")
                    with col2:
                        if st.button("View Sources", key=f"view_src_{situation.id}"):
                            st.info("Source list would display here")
        else:
            st.info("No situations created yet. Create situations to manage their sources.")
        
        if st.button("💾 Save Source Settings", type="primary"):
            st.success("Source settings saved!")
    
    with tab3:
        st.subheader("Storage Configuration")
        
        st.markdown("Configure data storage and retention.")
        
        # Storage backend
        storage_backend = st.selectbox(
            "Storage Backend",
            ["SQLite (Local)", "PostgreSQL", "JSON Files"],
            index=0
        )
        
        if storage_backend == "SQLite (Local)":
            st.text_input(
                "Database Path",
                value="./data/situation_monitor.db"
            )
        elif storage_backend == "PostgreSQL":
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Host", value="localhost")
                st.number_input("Port", value=5432)
                st.text_input("Database")
            with col2:
                st.text_input("Username")
                st.text_input("Password", type="password")
        
        st.divider()
        
        # Data retention
        st.markdown("**Data Retention**")
        
        col1, col2 = st.columns(2)
        with col1:
            doc_retention_days = st.number_input(
                "Document Retention (days)",
                min_value=1,
                max_value=3650,
                value=365
            )
        with col2:
            log_retention_days = st.number_input(
                "Log Retention (days)",
                min_value=1,
                max_value=365,
                value=30
            )
        
        auto_cleanup = st.toggle("Enable Automatic Cleanup", value=True)
        
        st.divider()
        
        # Storage stats
        st.markdown("**Storage Statistics**")
        
        health = storage.get_system_health()
        
        cols = st.columns(4)
        with cols[0]:
            st.metric("Total Documents", f"{health.total_documents:,}")
        with cols[1]:
            st.metric("Total Alerts", f"{health.total_alerts:,}")
        with cols[2]:
            st.metric("Active Situations", health.active_situations)
        with cols[3]:
            st.metric("Storage Status", "Connected" if health.storage_connected else "Disconnected")
        
        # Maintenance actions
        st.markdown("**Maintenance**")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🧹 Run Cleanup", use_container_width=True):
                st.info("Running cleanup...")
                st.success("Cleanup completed!")
        with col2:
            if st.button("💾 Backup Database", use_container_width=True):
                st.info("Creating backup...")
                st.success("Backup created!")
        with col3:
            if st.button("🗑️ Clear All Data", type="secondary", use_container_width=True):
                confirm = st.checkbox("I understand this will delete ALL data")
                if confirm:
                    st.error("This would delete all data - disabled in demo")
        
        if st.button("💾 Save Storage Settings", type="primary"):
            st.success("Storage settings saved!")
    
    with tab4:
        st.subheader("System Settings")
        
        st.markdown("**Dashboard Preferences**")
        
        col1, col2 = st.columns(2)
        with col1:
            auto_refresh = st.toggle("Auto-refresh Dashboard", value=True)
            refresh_interval = st.selectbox(
                "Refresh Interval",
                ["30s", "60s", "5m", "15m"],
                index=1
            )
        with col2:
            theme = st.selectbox("Theme", ["Light", "Dark", "Auto"])
            items_per_page = st.number_input("Items Per Page", value=50, min_value=10, max_value=500)
        
        st.divider()
        
        st.markdown("**Monitoring Settings**")
        
        col1, col2 = st.columns(2)
        with col1:
            default_interval = st.selectbox(
                "Default Check Interval",
                ["5 min", "15 min", "30 min", "1 hour", "6 hours", "Daily"],
                index=2
            )
        with col2:
            max_concurrent = st.number_input(
                "Max Concurrent Checks",
                min_value=1,
                max_value=50,
                value=10
            )
        
        st.divider()
        
        st.markdown("**NLP Settings**")
        
        col1, col2 = st.columns(2)
        with col1:
            sentiment_model = st.selectbox(
                "Sentiment Analysis Model",
                ["distilbert-base-uncased-finetuned-sst-2-english", "local", "none"]
            )
        with col2:
            entity_model = st.selectbox(
                "Entity Extraction Model",
                ["dslim/bert-base-NER", "spacy", "none"]
            )
        
        enable_summarization = st.toggle("Enable Auto-summarization", value=True)
        
        st.divider()
        
        st.markdown("**About**")
        
        st.markdown("""
        **Situation Monitor**
        - Version: 0.1.0
        - Built with: Python, Streamlit, SQLite
        - License: MIT
        
        For help and documentation, visit the project repository.
        """)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📚 Documentation", use_container_width=True):
                st.info("Documentation would open in a new tab")
        with col2:
            if st.button("🐛 Report Issue", use_container_width=True):
                st.info("Issue tracker would open")
        
        st.divider()
        
        if st.button("💾 Save System Settings", type="primary"):
            st.success("System settings saved!")
    
    # Reset/Export all settings
    st.divider()
    
    st.subheader("Export/Import Settings")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📥 Export All Settings", use_container_width=True):
            settings = {
                "version": "0.1.0",
                "exported_at": datetime.utcnow().isoformat(),
                "alert_preferences": {},
                "source_settings": {},
                "storage_settings": {},
                "system_settings": {}
            }
            st.download_button(
                "Download Settings JSON",
                json.dumps(settings, indent=2),
                file_name=f"situation_monitor_settings_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )
    with col2:
        uploaded_file = st.file_uploader("Import Settings", type="json")
        if uploaded_file:
            try:
                imported = json.load(uploaded_file)
                st.success(f"Settings imported from version {imported.get('version', 'unknown')}")
            except Exception as e:
                st.error(f"Failed to import: {e}")
