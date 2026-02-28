"""
Documents page - Browse, search, and view documents.
"""

import streamlit as st
from datetime import datetime, timedelta
import pandas as pd
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.storage_client import get_storage_client


def get_sentiment_emoji(sentiment: float) -> str:
    """Get emoji for sentiment score."""
    if sentiment > 0.3:
        return "😊"
    elif sentiment > 0.1:
        return "🙂"
    elif sentiment < -0.3:
        return "😟"
    elif sentiment < -0.1:
        return "🙁"
    return "😐"


def render_document_card(doc):
    """Render a single document card."""
    with st.container():
        # Title and metadata
        col1, col2 = st.columns([6, 1])
        with col1:
            title = doc.title or "Untitled Document"
            st.markdown(f"**{title}**")
        with col2:
            if st.button("View", key=f"doc_view_{doc.id}"):
                st.session_state.selected_document = doc.id
                st.session_state.show_document_detail = True
                st.rerun()
        
        # Meta line
        meta_parts = [
            f"📅 {doc.timestamp.strftime('%Y-%m-%d %H:%M')}",
            f"📦 {doc.source_id}",
        ]
        if doc.sentiment is not None:
            meta_parts.append(f"{get_sentiment_emoji(doc.sentiment)} {doc.sentiment:.2f}")
        
        st.caption(" | ".join(meta_parts))
        
        # Preview
        preview = doc.content[:200] + "..." if len(doc.content) > 200 else doc.content
        st.text(preview)
        
        # Keywords
        if doc.keywords:
            st.markdown("🏷️ " + ", ".join([f"`{kw}`" for kw in doc.keywords[:8]]))
        
        st.divider()


def render_document_detail(doc_id: str):
    """Render detailed view of a document."""
    storage = get_storage_client()
    doc = storage.get_document(doc_id)
    
    if not doc:
        st.error("Document not found")
        if st.button("← Back"):
            st.session_state.show_document_detail = False
            del st.session_state.selected_document
            st.rerun()
        return
    
    # Header
    col1, col2 = st.columns([6, 1])
    with col1:
        st.title("📄 Document Viewer")
    with col2:
        if st.button("← Back"):
            st.session_state.show_document_detail = False
            del st.session_state.selected_document
            # Return to previous page if set
            if st.session_state.get('return_to'):
                st.session_state.current_page = st.session_state.return_to
                del st.session_state.return_to
            st.rerun()
    
    st.divider()
    
    # Document title
    st.header(doc.title or "Untitled Document")
    
    # Metadata
    cols = st.columns(4)
    with cols[0]:
        st.metric("Source", doc.source_id)
    with cols[1]:
        st.metric("Collected", doc.timestamp.strftime('%Y-%m-%d'))
    with cols[2]:
        st.metric("Time", doc.timestamp.strftime('%H:%M'))
    with cols[3]:
        if doc.sentiment is not None:
            st.metric("Sentiment", f"{get_sentiment_emoji(doc.sentiment)} {doc.sentiment:.2f}")
        else:
            st.metric("Sentiment", "N/A")
    
    st.divider()
    
    # URL
    if doc.url:
        st.markdown(f"**URL:** [{doc.url}]({doc.url})")
    
    # Content
    st.subheader("Content")
    st.markdown(doc.content)
    
    st.divider()
    
    # Entities
    if doc.entities:
        st.subheader("🔍 Extracted Entities")
        
        entity_data = []
        for entity in doc.entities:
            entity_data.append({
                'Name': entity.get('name', entity.get('text', 'Unknown')),
                'Type': entity.get('type', entity.get('label', 'Unknown')),
                'Confidence': entity.get('confidence', entity.get('score', 'N/A'))
            })
        
        if entity_data:
            df = pd.DataFrame(entity_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Keywords
    if doc.keywords:
        st.subheader("🏷️ Keywords")
        st.markdown(" ".join([f"`{kw}`" for kw in doc.keywords]))
    
    # Raw metadata
    with st.expander("📋 Metadata"):
        st.json(doc.metadata)
    
    # Export options
    st.divider()
    st.subheader("📥 Export")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📄 Copy Text"):
            st.code(doc.content)
            st.success("Content ready to copy!")
    with col2:
        # JSON export
        import json
        doc_dict = {
            'id': doc.id,
            'title': doc.title,
            'content': doc.content,
            'url': doc.url,
            'source_id': doc.source_id,
            'timestamp': doc.timestamp.isoformat(),
            'sentiment': doc.sentiment,
            'entities': doc.entities,
            'keywords': doc.keywords,
            'metadata': doc.metadata
        }
        st.download_button(
            "📥 Download JSON",
            json.dumps(doc_dict, indent=2),
            file_name=f"document_{doc.id}.json",
            mime="application/json"
        )


def render():
    """Main render function for documents page."""
    
    if st.session_state.get('show_document_detail') and st.session_state.get('selected_document'):
        render_document_detail(st.session_state.selected_document)
        return
    
    st.title("🔍 Document Browser")
    st.caption("Search and explore collected documents")
    
    storage = get_storage_client()
    
    # Search and filter section
    with st.expander("🔍 Search & Filters", expanded=True):
        col1, col2, col3 = st.columns([3, 2, 2])
        
        with col1:
            search_query = st.text_input(
                "Search",
                placeholder="Search in title and content...",
                key="doc_search"
            )
        
        with col2:
            situation_filter = st.selectbox(
                "Situation",
                ["All Situations"] + [s.name for s in storage.get_situations()],
                key="doc_situation"
            )
        
        with col3:
            source_filter = st.selectbox(
                "Source",
                ["All Sources"],  # Would populate from actual sources
                key="doc_source"
            )
        
        # Date range
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            date_preset = st.selectbox(
                "Time Range",
                ["All Time", "Last 24h", "Last 7 days", "Last 30 days", "Custom"],
                key="doc_date_preset"
            )
        
        since = None
        until = None
        
        if date_preset == "Last 24h":
            since = datetime.utcnow() - timedelta(days=1)
        elif date_preset == "Last 7 days":
            since = datetime.utcnow() - timedelta(days=7)
        elif date_preset == "Last 30 days":
            since = datetime.utcnow() - timedelta(days=30)
        elif date_preset == "Custom":
            with col2:
                since = st.date_input("From", value=datetime.utcnow() - timedelta(days=7))
            with col3:
                until = st.date_input("To", value=datetime.utcnow())
            since = datetime.combine(since, datetime.min.time())
            until = datetime.combine(until, datetime.max.time())
        
        # Search button
        col1, col2 = st.columns([1, 5])
        with col1:
            do_search = st.button("🔍 Search", type="primary", use_container_width=True)
        with col2:
            if st.button("🔄 Reset Filters"):
                st.rerun()
    
    # Get documents
    situation_id = None
    if situation_filter != "All Situations":
        situations = storage.get_situations()
        for s in situations:
            if s.name == situation_filter:
                situation_id = s.id
                break
    
    # Always show some results (recent documents by default)
    documents = storage.get_documents(
        situation_id=situation_id,
        search_query=search_query if search_query else None,
        since=since,
        until=until,
        limit=50
    )
    
    # Results header
    st.divider()
    col1, col2 = st.columns([4, 1])
    with col1:
        st.subheader(f"📄 Documents ({len(documents)})")
    with col2:
        if documents:
            st.download_button(
                "📥 Export CSV",
                pd.DataFrame([{
                    'id': d.id,
                    'title': d.title,
                    'source': d.source_id,
                    'timestamp': d.timestamp,
                    'sentiment': d.sentiment,
                    'url': d.url
                } for d in documents]).to_csv(index=False),
                file_name=f"documents_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
    
    # Display documents
    if documents:
        for doc in documents:
            render_document_card(doc)
        
        # Pagination (simplified)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.info("Showing up to 50 most recent documents. Use filters to narrow results.")
    else:
        st.info("No documents found matching your criteria.")
        
        # Show some help
        with st.expander("💡 Tips"):
            st.markdown("""
            - Try broadening your search terms
            - Check if the selected situation has documents
            - Try a different time range
            - Documents appear as the system collects them from sources
            """)
