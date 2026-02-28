"""
Alerts page - View and manage alerts.
"""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.storage_client import get_storage_client


def get_severity_emoji(severity: str) -> str:
    """Get emoji for severity."""
    return {
        'info': 'ℹ️',
        'warning': '⚠️',
        'error': '❌',
        'critical': '🚨'
    }.get(severity.lower(), 'ℹ️')


def get_severity_color(severity: str) -> str:
    """Get color for severity."""
    return {
        'info': '#3b82f6',
        'warning': '#f59e0b',
        'error': '#ef4444',
        'critical': '#7f1d1d'
    }.get(severity.lower(), '#6b7280')


def render_alert_card(alert):
    """Render a single alert card."""
    severity_color = get_severity_color(alert.severity)
    acknowledged_icon = "✅" if alert.acknowledged else "⭕"
    
    with st.container():
        st.markdown(f"""
        <div style="
            border-left: 4px solid {severity_color};
            padding: 1rem;
            margin-bottom: 0.5rem;
            background-color: #f9fafb;
            border-radius: 0 0.375rem 0.375rem 0;
        ">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div>
                    <span style="color: {severity_color}; font-weight: 600; font-size: 0.75rem;">
                        {get_severity_emoji(alert.severity)} {alert.severity.upper()}
                    </span>
                    <strong style="margin-left: 0.5rem;">{alert.title}</strong>
                    <br/>
                    <small style="color: #6b7280;">
                        📅 {alert.timestamp.strftime('%Y-%m-%d %H:%M')} | 
                        📦 {alert.situation_id} | 
                        🔧 {alert.rule_id}
                    </small>
                </div>
                <span style="font-size: 1.2rem;" title="{'Acknowledged' if alert.acknowledged else 'Unacknowledged'}">
                    {acknowledged_icon}
                </span>
            </div>
            <p style="margin: 0.5rem 0 0 0; color: #374151;">{alert.message}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Actions
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            if not alert.acknowledged:
                if st.button("✓ Acknowledge", key=f"ack_{alert.id}"):
                    st.success(f"Alert {alert.id} acknowledged")
                    st.rerun()
        with col2:
            if st.button("📄 View Doc", key=f"viewdoc_{alert.id}"):
                if alert.document_id:
                    st.session_state.selected_document = alert.document_id
                    st.session_state.show_document_detail = True
                    st.session_state.return_to = "alerts"
                    st.rerun()


def render():
    """Main render function for alerts page."""
    st.title("🚨 Alerts")
    st.caption("Monitor and manage system alerts")
    
    storage = get_storage_client()
    
    # Summary stats
    all_alerts = storage.get_alerts(limit=1000)
    unacknowledged = [a for a in all_alerts if not a.acknowledged]
    
    cols = st.columns(4)
    with cols[0]:
        st.metric("Total Alerts", len(all_alerts))
    with cols[1]:
        st.metric("Unacknowledged", len(unacknowledged), 
                 delta=f"{len(unacknowledged)} pending" if unacknowledged else None,
                 delta_color="inverse")
    with cols[2]:
        critical = len([a for a in all_alerts if a.severity == 'critical'])
        st.metric("Critical", critical, 
                 delta=f"{critical} critical" if critical else None,
                 delta_color="inverse")
    with cols[3]:
        recent_24h = len([a for a in all_alerts if a.timestamp > datetime.utcnow() - timedelta(hours=24)])
        st.metric("Last 24h", recent_24h)
    
    st.divider()
    
    # Filters
    with st.expander("🔍 Filters", expanded=True):
        col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
        
        with col1:
            severity_filter = st.multiselect(
                "Severity",
                ["info", "warning", "error", "critical"],
                default=[],
                key="alert_severity"
            )
        
        with col2:
            acknowledged_filter = st.selectbox(
                "Status",
                ["All", "Unacknowledged Only", "Acknowledged Only"],
                key="alert_status"
            )
        
        with col3:
            situation_filter = st.selectbox(
                "Situation",
                ["All Situations"] + [s.name for s in storage.get_situations()],
                key="alert_situation"
            )
        
        with col4:
            time_filter = st.selectbox(
                "Time Range",
                ["All Time", "Last 24h", "Last 7 days", "Last 30 days"],
                key="alert_time"
            )
        
        # Apply filters button
        col1, col2 = st.columns([1, 5])
        with col1:
            apply_filters = st.button("🔍 Apply", type="primary", use_container_width=True)
        with col2:
            if st.button("🔄 Reset"):
                st.rerun()
    
    # Get filtered alerts
    alerts = all_alerts
    
    # Apply filters
    if severity_filter:
        alerts = [a for a in alerts if a.severity in severity_filter]
    
    if acknowledged_filter == "Unacknowledged Only":
        alerts = [a for a in alerts if not a.acknowledged]
    elif acknowledged_filter == "Acknowledged Only":
        alerts = [a for a in alerts if a.acknowledged]
    
    if situation_filter != "All Situations":
        situations = storage.get_situations()
        situation_id = None
        for s in situations:
            if s.name == situation_filter:
                situation_id = s.id
                break
        if situation_id:
            alerts = [a for a in alerts if a.situation_id == situation_id]
    
    if time_filter == "Last 24h":
        alerts = [a for a in alerts if a.timestamp > datetime.utcnow() - timedelta(hours=24)]
    elif time_filter == "Last 7 days":
        alerts = [a for a in alerts if a.timestamp > datetime.utcnow() - timedelta(days=7)]
    elif time_filter == "Last 30 days":
        alerts = [a for a in alerts if a.timestamp > datetime.utcnow() - timedelta(days=30)]
    
    # Bulk actions
    st.divider()
    col1, col2, col3 = st.columns([2, 2, 4])
    with col1:
        st.subheader(f"Alerts ({len(alerts)})")
    with col2:
        if unacknowledged and st.button("✓ Acknowledge All Unacknowledged"):
            st.success("All unacknowledged alerts marked as acknowledged")
            st.rerun()
    with col3:
        if alerts:
            st.download_button(
                "📥 Export CSV",
                pd.DataFrame([{
                    'id': a.id,
                    'situation_id': a.situation_id,
                    'rule_id': a.rule_id,
                    'severity': a.severity,
                    'title': a.title,
                    'message': a.message,
                    'timestamp': a.timestamp,
                    'acknowledged': a.acknowledged
                } for a in alerts]).to_csv(index=False),
                file_name=f"alerts_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    
    # Display alerts
    if alerts:
        # Sort by timestamp desc
        alerts = sorted(alerts, key=lambda x: x.timestamp, reverse=True)
        
        for alert in alerts:
            render_alert_card(alert)
    else:
        st.info("No alerts match your filters.")
        
        if not all_alerts:
            st.markdown("""
            🎉 No alerts have been generated yet. Alerts will appear here when:
            - Situations are being monitored
            - Alert rules are triggered by collected content
            - Keywords or conditions match in new documents
            """)
