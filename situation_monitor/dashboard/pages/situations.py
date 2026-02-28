"""
Situations page - Manage and view monitoring situations.
"""

import streamlit as st
from datetime import datetime
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.storage_client import get_storage_client


def get_status_badge(status: str) -> str:
    """Get status badge HTML."""
    colors = {
        'active': ('🟢', '#059669'),
        'paused': ('⏸️', '#d97706'),
        'error': ('🔴', '#dc2626'),
        'disabled': ('⚪', '#6b7280')
    }
    icon, color = colors.get(status.lower(), ('⚪', '#6b7280'))
    return f"<span style='color: {color}; font-weight: 600;'>{icon} {status.upper()}</span>"


def render_situation_list():
    """Render the list of situations."""
    storage = get_storage_client()
    
    # Filters
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        search = st.text_input("🔍 Search", placeholder="Search situations...", key="sit_search")
    
    with col2:
        status_filter = st.selectbox(
            "Status",
            ["All", "Active", "Paused", "Error", "Disabled"],
            key="sit_status"
        )
    
    with col3:
        st.write("")
        st.write("")
        if st.button("➕ New", use_container_width=True):
            st.session_state.show_create_situation = True
            st.rerun()
    
    # Get situations
    status_param = None if status_filter == "All" else status_filter.lower()
    situations = storage.get_situations(
        status=status_param,
        search_query=search if search else None
    )
    
    if not situations:
        st.info("No situations found. Create your first situation to start monitoring.")
        
        if st.button("➕ Create First Situation", type="primary"):
            st.session_state.show_create_situation = True
            st.rerun()
        return
    
    # Display as table
    data = []
    for s in situations:
        data.append({
            'ID': s.id,
            'Name': s.name,
            'Query': s.query[:60] + "..." if len(s.query) > 60 else s.query,
            'Status': s.status,
            'Sources': s.source_count,
            'Documents': s.document_count,
            'Alerts': s.alert_count,
            'Updated': s.updated_at.strftime('%Y-%m-%d %H:%M')
        })
    
    df = pd.DataFrame(data)
    
    # Custom display
    st.subheader(f"Situations ({len(situations)})")
    
    for s in situations:
        with st.container():
            cols = st.columns([3, 2, 1, 1, 1, 1])
            
            with cols[0]:
                st.markdown(f"**{s.name}**")
                st.caption(s.query[:80] + "..." if len(s.query) > 80 else s.query)
            
            with cols[1]:
                st.markdown(get_status_badge(s.status), unsafe_allow_html=True)
            
            with cols[2]:
                st.metric("Sources", s.source_count, label_visibility="collapsed")
            
            with cols[3]:
                st.metric("Docs", s.document_count, label_visibility="collapsed")
            
            with cols[4]:
                st.metric("Alerts", s.alert_count, label_visibility="collapsed")
            
            with cols[5]:
                if st.button("View", key=f"view_{s.id}"):
                    st.session_state.selected_situation = s.id
                    st.session_state.show_detail = True
                    st.rerun()
            
            st.divider()


def render_create_situation():
    """Render the create situation form."""
    st.subheader("➕ Create New Situation")
    
    with st.form("create_situation"):
        name = st.text_input("Name", placeholder="e.g., US-Iran Tensions")
        query = st.text_area(
            "Monitoring Query",
            placeholder="Describe what you want to monitor...",
            help="Be specific about topics, entities, and events you want to track"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            interval = st.selectbox(
                "Check Interval",
                ["5 min", "15 min", "30 min", "1 hour", "6 hours", "Daily"],
                index=2
            )
        with col2:
            severity = st.selectbox(
                "Default Alert Severity",
                ["Info", "Warning", "Error", "Critical"],
                index=1
            )
        
        # Keywords for alerts
        keywords = st.text_input(
            "Alert Keywords (comma-separated)",
            placeholder="escalation, sanctions, breakthrough...",
            help="Keywords that trigger alerts when found in content"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("✅ Create", use_container_width=True, type="primary")
        with col2:
            cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
        
        if submitted:
            if not name or not query:
                st.error("Name and query are required")
            else:
                # Here you would call API to create situation
                st.success(f"Situation '{name}' created successfully!")
                st.session_state.show_create_situation = False
                st.rerun()
        
        if cancelled:
            st.session_state.show_create_situation = False
            st.rerun()


def render_situation_detail(situation_id: str):
    """Render detailed view of a situation."""
    storage = get_storage_client()
    situation = storage.get_situation(situation_id)
    
    if not situation:
        st.error("Situation not found")
        if st.button("← Back to List"):
            st.session_state.show_detail = False
            del st.session_state.selected_situation
            st.rerun()
        return
    
    # Header with back button
    col1, col2 = st.columns([6, 1])
    with col1:
        st.title(f"📋 {situation.name}")
    with col2:
        if st.button("← Back"):
            st.session_state.show_detail = False
            del st.session_state.selected_situation
            st.rerun()
    
    st.markdown(get_status_badge(situation.status), unsafe_allow_html=True)
    st.caption(f"Query: {situation.query}")
    
    st.divider()
    
    # Stats
    stats = storage.get_situation_stats(situation_id)
    
    cols = st.columns(4)
    with cols[0]:
        st.metric("Sources", situation.source_count)
    with cols[1]:
        st.metric("Documents", situation.document_count)
    with cols[2]:
        st.metric("Alerts", situation.alert_count)
    with cols[3]:
        avg_sentiment = stats.get('sentiment', {}).get('average', 0)
        sentiment_label = "😐 Neutral"
        if avg_sentiment > 0.2:
            sentiment_label = "😊 Positive"
        elif avg_sentiment < -0.2:
            sentiment_label = "😟 Negative"
        st.metric("Sentiment", sentiment_label)
    
    st.divider()
    
    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📈 Overview", "📄 Documents", "⚙️ Settings"])
    
    with tab1:
        # Activity chart
        if stats.get('documents_by_day'):
            st.subheader("Document Activity (Last 30 Days)")
            import plotly.express as px
            df = pd.DataFrame(stats['documents_by_day'])
            df['day'] = pd.to_datetime(df['day'])
            fig = px.line(df, x='day', y='count', title="Documents per Day")
            st.plotly_chart(fig, use_container_width=True)
        
        # Alerts by severity
        if stats.get('alerts_by_severity'):
            st.subheader("Alerts by Severity")
            severity_data = stats['alerts_by_severity']
            sev_df = pd.DataFrame([
                {'Severity': k, 'Count': v}
                for k, v in severity_data.items()
            ])
            import plotly.express as px
            fig = px.bar(sev_df, x='Severity', y='Count', color='Severity')
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.subheader("Recent Documents")
        
        docs = storage.get_documents(situation_id=situation_id, limit=10)
        
        if docs:
            for doc in docs:
                with st.expander(f"{doc.title or 'Untitled'} - {doc.timestamp.strftime('%Y-%m-%d %H:%M')}"):
                    st.markdown(f"**Source:** {doc.source_id}")
                    st.markdown(f"**URL:** [{doc.url}]({doc.url})")
                    if doc.sentiment is not None:
                        sentiment_emoji = "😐"
                        if doc.sentiment > 0.2:
                            sentiment_emoji = "😊"
                        elif doc.sentiment < -0.2:
                            sentiment_emoji = "😟"
                        st.markdown(f"**Sentiment:** {sentiment_emoji} {doc.sentiment:.2f}")
                    if doc.keywords:
                        st.markdown(f"**Keywords:** {', '.join(doc.keywords[:10])}")
                    st.markdown("**Content:**")
                    st.text(doc.content[:500] + "..." if len(doc.content) > 500 else doc.content)
        else:
            st.info("No documents yet. Documents will appear here as the situation is monitored.")
    
    with tab3:
        st.subheader("Situation Settings")
        
        col1, col2 = st.columns(2)
        with col1:
            new_status = st.selectbox(
                "Status",
                ["active", "paused", "disabled"],
                index=["active", "paused", "disabled"].index(situation.status)
            )
        
        with col2:
            st.write("")
            st.write("")
            if st.button("💾 Save Changes"):
                st.success("Settings saved!")
        
        st.divider()
        
        # Action buttons
        col1, col2, col3 = st.columns(3)
        with col1:
            if situation.status == "active":
                if st.button("⏸️ Pause Monitoring", use_container_width=True):
                    st.info("Situation paused")
            else:
                if st.button("▶️ Resume Monitoring", use_container_width=True):
                    st.info("Situation resumed")
        with col2:
            if st.button("🔄 Force Refresh", use_container_width=True):
                st.info("Refreshing data...")
        with col3:
            if st.button("🗑️ Delete Situation", use_container_width=True, type="secondary"):
                confirm = st.checkbox("I understand this cannot be undone")
                if confirm and st.button("Confirm Delete", type="primary"):
                    st.warning("Situation deleted")
                    st.session_state.show_detail = False
                    st.rerun()


def render():
    """Main render function for situations page."""
    # Check which view to show
    if st.session_state.get('show_create_situation'):
        render_create_situation()
    elif st.session_state.get('show_detail') and st.session_state.get('selected_situation'):
        render_situation_detail(st.session_state.selected_situation)
    else:
        render_situation_list()
