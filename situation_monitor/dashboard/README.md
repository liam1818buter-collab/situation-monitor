# Situation Monitor Dashboard

A Streamlit-based web interface for monitoring situations and exploring collected data.

## Features

### 📊 Dashboard Overview
- Real-time system health monitoring
- Active situations summary
- Recent alerts with acknowledgment tracking
- Quick action buttons

### 📋 Situation Management
- Create, edit, pause, and delete situations
- View situation statistics (documents, alerts, sources)
- Timeline view of activity
- Source management per situation

### 🔍 Document Browser
- Full-text search across documents
- Filter by situation, source, and date range
- View document details with extracted entities
- Export documents to CSV/JSON

### 🚨 Alerts
- View all system alerts
- Filter by severity, status, and situation
- Acknowledge alerts individually or in bulk
- Export alert history

### 📈 Analytics
- Sentiment trend analysis over time
- Keyword frequency visualization
- Entity mention timelines
- Activity heatmaps
- Export analytics data

### 📝 System Logs
- View application logs
- Filter by level, source, and time
- Search log messages
- Export log data

### ⚙️ Settings
- Alert preferences and notification channels
- Data source configuration
- Storage settings and retention
- System preferences

## Installation

The dashboard is included with the situation_monitor package. Ensure you have the required dependencies:

```bash
pip install streamlit plotly pandas
```

## Usage

### Run the Dashboard

From the `situation_monitor` directory:

```bash
./run_dashboard.sh
```

Or manually:

```bash
streamlit run dashboard/app.py
```

The dashboard will be available at `http://localhost:8501`.

### Run with Custom Port

```bash
./run_dashboard.sh --server.port=8080
```

## Architecture

```
dashboard/
├── app.py                    # Main Streamlit application
├── storage_client.py         # Interface to Agent 6's storage layer
├── run_dashboard.sh          # Convenience startup script
├── pages/                    # Page modules
│   ├── situations.py         # Situation management
│   ├── documents.py          # Document browser
│   ├── alerts.py             # Alert management
│   ├── analytics.py          # Data visualizations
│   ├── logs.py               # System logs
│   └── settings.py           # Configuration
└── components/               # Reusable UI components
```

## Data Flow

1. **Agent 6 (Storage Layer)** - SQLite database with situations, documents, alerts
2. **DashboardStorageClient** - Read-only interface to storage
3. **Page Modules** - Business logic and data fetching
4. **Streamlit UI** - Interactive web interface

## Configuration

The dashboard reads from the same SQLite database used by the core system. No additional configuration is required.

Database location: `./data/situation_monitor.db`

## Development

### Adding a New Page

1. Create a new file in `dashboard/pages/`
2. Implement a `render()` function
3. Add navigation in `app.py`

Example:

```python
# dashboard/pages/my_page.py
import streamlit as st

def render():
    st.title("My Page")
    st.write("Content here")
```

### Adding Visualizations

The dashboard supports both Plotly and Altair:

```python
import plotly.express as px

fig = px.line(data, x='date', y='value')
st.plotly_chart(fig, use_container_width=True)
```

## Auto-Refresh

The dashboard auto-refreshes every 60 seconds when enabled. This can be toggled in the sidebar.

## Integration with Agent 6

The dashboard queries Agent 6's storage layer via `DashboardStorageClient`. It provides read-only access to:

- Situations and their metadata
- Documents with full text, entities, and keywords
- Alerts and their status
- System logs
- Analytics aggregations

All modifications (create, update, delete) should go through the appropriate API endpoints.

## Zero-Cost Design

- **Streamlit**: Open-source, free local hosting
- **SQLite**: Built-in, no external database needed
- **Plotly/Altair**: Open-source visualization libraries

## Future Enhancements

- [ ] Real-time WebSocket updates
- [ ] PDF report generation
- [ ] Multi-user authentication
- [ ] Mobile-responsive improvements
- [ ] Custom dashboard widgets
