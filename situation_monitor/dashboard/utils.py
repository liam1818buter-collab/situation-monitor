"""
Dashboard utilities - Helper functions for the dashboard.
"""

import streamlit as st
from datetime import datetime
from typing import Optional


def format_timestamp(ts: datetime) -> str:
    """Format a timestamp for display."""
    now = datetime.utcnow()
    delta = now - ts
    
    if delta.days == 0:
        if delta.seconds < 60:
            return "Just now"
        elif delta.seconds < 3600:
            return f"{delta.seconds // 60}m ago"
        else:
            return f"{delta.seconds // 3600}h ago"
    elif delta.days == 1:
        return "Yesterday"
    elif delta.days < 7:
        return f"{delta.days}d ago"
    else:
        return ts.strftime('%Y-%m-%d')


def get_sentiment_label(score: Optional[float]) -> str:
    """Get human-readable sentiment label."""
    if score is None:
        return "Unknown"
    if score > 0.5:
        return "Very Positive"
    elif score > 0.1:
        return "Positive"
    elif score < -0.5:
        return "Very Negative"
    elif score < -0.1:
        return "Negative"
    return "Neutral"


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def render_error(message: str):
    """Render an error message with consistent styling."""
    st.error(f"❌ {message}")


def render_success(message: str):
    """Render a success message with consistent styling."""
    st.success(f"✅ {message}")


def render_info(message: str):
    """Render an info message with consistent styling."""
    st.info(f"ℹ️ {message}")


def render_warning(message: str):
    """Render a warning message with consistent styling."""
    st.warning(f"⚠️ {message}")


def confirm_dialog(message: str, confirm_label: str = "Confirm", cancel_label: str = "Cancel") -> bool:
    """Show a confirmation dialog. Returns True if confirmed."""
    col1, col2 = st.columns(2)
    with col1:
        if st.button(confirm_label, type="primary", use_container_width=True):
            return True
    with col2:
        if st.button(cancel_label, use_container_width=True):
            return False
    st.write(message)
    return None


def export_to_csv_button(data: list, filename: str, button_label: str = "📥 Export CSV"):
    """Render a CSV export button for data."""
    import pandas as pd
    from datetime import datetime
    
    if not data:
        st.button(button_label, disabled=True, use_container_width=True)
        return
    
    df = pd.DataFrame(data)
    st.download_button(
        button_label,
        df.to_csv(index=False),
        file_name=filename,
        mime="text/csv",
        use_container_width=True
    )


def get_status_badge_html(status: str) -> str:
    """Get HTML for a status badge."""
    colors = {
        'active': '#059669',
        'paused': '#d97706',
        'error': '#dc2626',
        'disabled': '#6b7280',
        'healthy': '#059669',
        'warning': '#d97706'
    }
    color = colors.get(status.lower(), '#6b7280')
    return f'<span style="color: {color}; font-weight: 600;">{status.upper()}</span>'


def get_severity_badge_html(severity: str) -> str:
    """Get HTML for a severity badge."""
    colors = {
        'info': '#3b82f6',
        'warning': '#f59e0b',
        'error': '#ef4444',
        'critical': '#7f1d1d'
    }
    color = colors.get(severity.lower(), '#6b7280')
    return f'<span style="color: {color}; font-weight: 600;">{severity.upper()}</span>'
