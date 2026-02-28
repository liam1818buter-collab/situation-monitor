"""
Analytics page - Visualizations and insights.
"""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.storage_client import get_storage_client

# Try to import visualization libraries
try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import altair as alt
    HAS_ALTAIR = True
except ImportError:
    HAS_ALTAIR = False


def render_sentiment_trend(storage, situation_id, days=7):
    """Render sentiment trend chart."""
    data = storage.get_sentiment_trend(situation_id, days=days)
    
    if not data:
        st.info("No sentiment data available yet")
        return
    
    df = pd.DataFrame(data)
    df['day'] = pd.to_datetime(df['day'])
    
    st.subheader("📊 Sentiment Trend")
    
    if HAS_PLOTLY:
        fig = px.line(
            df, 
            x='day', 
            y='sentiment',
            title=f"Average Sentiment Over Time (Last {days} days)",
            labels={'sentiment': 'Sentiment Score', 'day': 'Date'}
        )
        fig.add_hline(y=0, line_dash="dash", line_color="gray")
        fig.add_hrect(y0=-1, y1=-0.3, line_width=0, fillcolor="red", opacity=0.1, annotation_text="Negative")
        fig.add_hrect(y0=0.3, y1=1, line_width=0, fillcolor="green", opacity=0.1, annotation_text="Positive")
        st.plotly_chart(fig, use_container_width=True)
    elif HAS_ALTAIR:
        chart = alt.Chart(df).mark_line(point=True).encode(
            x='day:T',
            y='sentiment:Q',
            tooltip=['day', 'sentiment']
        ).properties(
            title=f"Sentiment Trend (Last {days} days)"
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.line_chart(df.set_index('day')['sentiment'])


def render_keyword_cloud(storage, situation_id):
    """Render keyword frequency visualization."""
    data = storage.get_keyword_frequency(situation_id, top_n=30)
    
    if not data:
        st.info("No keyword data available yet")
        return
    
    st.subheader("🏷️ Top Keywords")
    
    df = pd.DataFrame(data)
    
    if HAS_PLOTLY:
        fig = px.bar(
            df,
            x='count',
            y='keyword',
            orientation='h',
            title="Most Frequent Keywords",
            labels={'count': 'Frequency', 'keyword': 'Keyword'}
        )
        fig.update_layout(yaxis={'categoryorder': 'total ascending'})
        st.plotly_chart(fig, use_container_width=True)
    elif HAS_ALTAIR:
        chart = alt.Chart(df).mark_bar().encode(
            x='count:Q',
            y=alt.Y('keyword:N', sort='-x'),
            tooltip=['keyword', 'count']
        ).properties(
            title="Top Keywords"
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.bar_chart(df.set_index('keyword')['count'])


def render_entity_timeline(storage, situation_id, days=7):
    """Render entity mentions timeline."""
    data = storage.get_entity_timeline(situation_id, days=days)
    
    if not data:
        st.info("No entity data available yet")
        return
    
    st.subheader("👥 Entity Mentions")
    
    df = pd.DataFrame(data)
    
    # Get top entities
    top_entities = df.groupby('entity')['count'].sum().nlargest(10).index.tolist()
    df_filtered = df[df['entity'].isin(top_entities)]
    
    if HAS_PLOTLY:
        fig = px.line(
            df_filtered,
            x='day',
            y='count',
            color='entity',
            title=f"Top Entity Mentions Over Time (Last {days} days)",
            labels={'count': 'Mentions', 'day': 'Date'}
        )
        st.plotly_chart(fig, use_container_width=True)
    elif HAS_ALTAIR:
        chart = alt.Chart(df_filtered).mark_line(point=True).encode(
            x='day:T',
            y='count:Q',
            color='entity:N',
            tooltip=['entity', 'day', 'count']
        ).properties(
            title="Entity Timeline"
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        pivot_df = df_filtered.pivot(index='day', columns='entity', values='count').fillna(0)
        st.line_chart(pivot_df)


def render_activity_heatmap(storage, situation_id, days=30):
    """Render activity heatmap."""
    data = storage.get_activity_heatmap(situation_id, days=days)
    
    if not data:
        st.info("No activity data available yet")
        return
    
    st.subheader("🔥 Activity Heatmap")
    
    df = pd.DataFrame(data)
    
    # Create pivot for heatmap
    pivot_df = df.pivot(index='day', columns='hour', values='count').fillna(0)
    
    if HAS_PLOTLY:
        fig = px.density_heatmap(
            df,
            x='hour',
            y='day',
            z='count',
            title="Document Activity by Hour and Day",
            labels={'hour': 'Hour of Day', 'day': 'Date', 'count': 'Documents'},
            color_continuous_scale='YlOrRd'
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("Activity by hour:")
        st.dataframe(pivot_df, use_container_width=True)


def render_document_volume(storage, situation_id, days=7):
    """Render document volume over time."""
    try:
        from dashboard.storage_client import Document
        docs = storage.get_documents(situation_id=situation_id, limit=1000)
        
        if not docs:
            st.info("No documents available yet")
            return
        
        # Group by day
        df = pd.DataFrame([
            {'date': d.timestamp.date(), 'count': 1}
            for d in docs
            if d.timestamp > datetime.utcnow() - timedelta(days=days)
        ])
        
        if df.empty:
            st.info("No documents in the selected time range")
            return
        
        daily_counts = df.groupby('date').sum().reset_index()
        
        st.subheader("📈 Document Volume")
        
        if HAS_PLOTLY:
            fig = px.bar(
                daily_counts,
                x='date',
                y='count',
                title=f"Documents Collected Per Day (Last {days} days)",
                labels={'count': 'Documents', 'date': 'Date'}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.bar_chart(daily_counts.set_index('date')['count'])
            
    except Exception as e:
        st.error(f"Error loading document volume: {e}")


def render():
    """Main render function for analytics page."""
    st.title("📈 Analytics")
    st.caption("Visualizations and insights from monitored data")
    
    storage = get_storage_client()
    
    # Situation selector
    situations = storage.get_situations()
    
    if not situations:
        st.info("No situations available. Create a situation to see analytics.")
        return
    
    situation_options = {s.name: s.id for s in situations}
    
    col1, col2, col3 = st.columns([3, 2, 2])
    
    with col1:
        selected_name = st.selectbox(
            "Select Situation",
            list(situation_options.keys()),
            key="analytics_situation"
        )
    
    with col2:
        time_range = st.selectbox(
            "Time Range",
            ["Last 7 days", "Last 14 days", "Last 30 days"],
            key="analytics_range"
        )
    
    days = 7
    if time_range == "Last 14 days":
        days = 14
    elif time_range == "Last 30 days":
        days = 30
    
    situation_id = situation_options[selected_name]
    
    st.divider()
    
    # Analytics tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview",
        "😊 Sentiment",
        "🏷️ Keywords",
        "👥 Entities",
        "🔥 Activity"
    ])
    
    with tab1:
        render_document_volume(storage, situation_id, days)
        
        # Key metrics
        stats = storage.get_situation_stats(situation_id)
        
        cols = st.columns(4)
        with cols[0]:
            total_docs = len(storage.get_documents(situation_id=situation_id, limit=10000))
            st.metric("Total Documents", total_docs)
        with cols[1]:
            sentiment_avg = stats.get('sentiment', {}).get('average', 0)
            st.metric("Avg Sentiment", f"{sentiment_avg:.2f}")
        with cols[2]:
            alerts_count = len(storage.get_alerts(situation_id=situation_id))
            st.metric("Total Alerts", alerts_count)
        with cols[3]:
            keywords_count = len(stats.get('alerts_by_severity', {}))
            st.metric("Alert Types", keywords_count)
    
    with tab2:
        render_sentiment_trend(storage, situation_id, days)
        
        # Sentiment distribution
        docs = storage.get_documents(situation_id=situation_id, limit=1000)
        sentiment_docs = [d for d in docs if d.sentiment is not None]
        
        if sentiment_docs:
            st.subheader("Sentiment Distribution")
            
            # Categorize sentiments
            positive = len([d for d in sentiment_docs if d.sentiment > 0.1])
            negative = len([d for d in sentiment_docs if d.sentiment < -0.1])
            neutral = len(sentiment_docs) - positive - negative
            
            if HAS_PLOTLY:
                fig = px.pie(
                    names=['Positive', 'Neutral', 'Negative'],
                    values=[positive, neutral, negative],
                    title="Sentiment Distribution",
                    color=['Positive', 'Neutral', 'Negative'],
                    color_discrete_map={
                        'Positive': '#10b981',
                        'Neutral': '#6b7280',
                        'Negative': '#ef4444'
                    }
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write(f"Positive: {positive}, Neutral: {neutral}, Negative: {negative}")
    
    with tab3:
        render_keyword_cloud(storage, situation_id)
    
    with tab4:
        render_entity_timeline(storage, situation_id, days)
    
    with tab5:
        render_activity_heatmap(storage, situation_id, days=30)
    
    # Export options
    st.divider()
    st.subheader("📥 Export Analytics")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Generate Report", use_container_width=True):
            st.info("Report generation would create a PDF summary of all analytics")
    with col2:
        if st.button("📊 Export Data", use_container_width=True):
            # Export sentiment data
            sentiment_data = storage.get_sentiment_trend(situation_id, days)
            if sentiment_data:
                df = pd.DataFrame(sentiment_data)
                st.download_button(
                    "Download Sentiment CSV",
                    df.to_csv(index=False),
                    file_name=f"sentiment_{situation_id}_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
