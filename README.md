# Situation Monitor 🎯

Autonomous, zero-cost monitoring application. Input a situation (e.g., "US-Iran tensions", "AI breakthroughs") and the system continuously monitors, analyzes, and reports on it across multiple dimensions.

**100% Free**: Open-source tools only. No paid APIs.

---

## Quick Start

### 1. Install Dependencies

```bash
cd /root/clawd/situation-monitor
pip install -r requirements.txt
```

### 2. Download NLP Models

```bash
cd situation_monitor/analysis
bash setup.sh
cd ../..
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings (optional for local use)
```

### 4. Run Integration Test

```bash
python main.py test
```

### 5. Launch Dashboard

```bash
python main.py dashboard
# Or directly:
streamlit run situation_monitor/dashboard/app.py
```

Access at: http://localhost:8501

---

## Architecture

```
situation_monitor/
├── core/           # Base abstractions & config
├── nlp/            # Input parsing (Agent 2)
├── analysis/       # NLP pipeline (Agent 5)
│   ├── sentiment.py    # DistilBERT sentiment
│   ├── summarizer.py   # BART summarization
│   ├── entities.py     # spaCy NER
│   └── keywords.py     # KeyBERT extraction
├── alerts/         # Notification system (Agent 7)
│   ├── email.py        # SMTP alerts
│   ├── discord.py      # Webhook alerts
│   └── webhook.py      # Generic webhooks
├── storage/        # Database layer (Agent 6)
├── dashboard/      # Streamlit UI (Agent 8)
└── sources/        # Discovery engine (Agent 3)
```

---

## Usage Examples

### Monitor via Dashboard

1. Open http://localhost:8501
2. Click "➕ New Situation"
3. Enter: "Track breakthrough papers in multimodal AI"
4. System auto-discovers sources and begins monitoring

### Programmatic Usage

```python
from situation_monitor.core.base import Document
from situation_monitor.analysis.pipeline import AnalysisPipeline

# Create a document
doc = Document(
    url="https://arxiv.org/abs/...",
    title="New Multimodal Architecture",
    content="Full paper text here...",
    source_type="academic"
)

# Analyze
pipeline = AnalysisPipeline()
results = await pipeline.analyze([doc])

# Results include:
# - sentiment: float (-1 to 1)
# - summary: str
# - entities: List[str]
# - keywords: List[str]
```

---

## Configuration

Edit `.env` file:

```bash
# Database
DATABASE_URL=sqlite:///./situation_monitor.db

# Email Alerts (optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password

# Discord Alerts (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Alert Rate Limiting
ALERT_COOLDOWN_MINUTES=15
```

---

## Example Situations

| Situation | Sources Monitored | Alerts On |
|-----------|------------------|-----------|
| "US-Iran nuclear negotiations" | Reuters, AP, Gov press releases | Escalation keywords, sanctions |
| "Breakthrough papers in multimodal AI" | arXiv, PapersWithCode, Twitter | State-of-the-art results |
| "EU cryptocurrency policy changes" | ECB, EU Parliament, Coindesk | New legislation, enforcement |
| "Rare earth supply disruptions" | Industry reports, customs data | Export restrictions, price spikes |

---

## Zero-Cost Stack

| Component | Tool | Cost |
|-----------|------|------|
| Web Scraping | scrapling | Free |
| Search | DuckDuckGo + RSS | Free |
| NLP Models | HuggingFace (local) | Free |
| Embeddings | sentence-transformers | Free |
| Database | SQLite | Free |
| Dashboard | Streamlit | Free |
| Notifications | Email/Discord | Free |

---

## Testing

```bash
# Run all tests
pytest situation_monitor/ -v

# Run integration test
python main.py test

# Run specific module tests
pytest situation_monitor/test_scheduler.py -v
```

---

## Project Status

| Module | Status |
|--------|--------|
| Core Architecture | ✅ Complete |
| Input Parser | ✅ Complete |
| Source Discovery | ✅ Complete |
| Data Collector | ✅ Complete |
| NLP Analysis | ✅ Complete |
| Knowledge Base | ✅ Complete |
| Alert System | ✅ Complete |
| Dashboard | ✅ Complete |
| Integration Tests | ✅ Complete |

---

## License

MIT - Open source, free to use and modify.

Built by 9 parallel sub-agents orchestrated by Clud 🐾
