# ReviewLens — AI Sentiment Dashboard Extension

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     BROWSER (Product Page)                   │
│                                                             │
│  ┌───────────────┐    ┌──────────────────────────────────┐  │
│  │  Content      │    │  Background Service Worker       │  │
│  │  Script       │───▶│  (chrome.runtime.sendMessage)    │  │
│  │  - Scrapes    │    │  - Proxies fetch to backend      │  │
│  │    reviews    │◀───│  - Avoids CORS                   │  │
│  │  - Injects    │    └──────────────┬───────────────────┘  │
│  │    iframe     │                   │                       │
│  └───────────────┘                   │                       │
│         │                            │ HTTP POST /analyze    │
│         │ postMessage(data)          ▼                       │
│  ┌──────▼──────────────────┐  ┌─────────────────────────┐  │
│  │  React Dashboard        │  │  FastAPI Backend         │  │
│  │  (runs in iframe)       │  │                         │  │
│  │  - Recharts             │  │  DistilRoBERTa           │  │
│  │  - Sentiment donut      │  │  Sentiment Classification│  │
│  │  - Aspect bar chart     │  │  Aspect Extraction       │  │
│  │  - Trend area chart     │  │  Keyword Extraction      │  │
│  │  - Review list          │  │  (KeyBERT / YAKE)        │  │
│  └─────────────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Folder Structure

```
reviewlens/
├── extension/
│   ├── public/
│   │   ├── manifest.json      # MV3 manifest
│   │   ├── content.css        # Minimal injected styles
│   │   └── icons/             # Extension icons (add your own)
│   ├── src/
│   │   ├── components/
│   │   │   └── Dashboard.jsx  # Full React dashboard
│   │   ├── content.js         # Scraping + injection logic
│   │   ├── background.js      # Service worker / proxy
│   │   └── main.jsx           # React entry point
│   ├── index.html             # Dashboard shell
│   ├── vite.config.js
│   └── package.json
│
└── backend/
    ├── app/
    │   ├── main.py            # FastAPI app
    │   ├── routers/
    │   │   └── analysis.py    # /analyze endpoint
    │   ├── services/
    │   │   └── nlp_service.py # Sentiment + aspect pipeline
    │   └── models/
    │       └── schemas.py     # Pydantic request/response
    ├── requirements.txt
    └── README.md
```