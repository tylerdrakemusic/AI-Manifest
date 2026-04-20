# 👁 AI-Manifest

AI integration platform for Tyler James Drake. Centralized hub for external AI service integrations, starting with ElevenLabs voice synthesis.

## Quick Start

```bash
# Install dependencies
C:\G\python.exe -m pip install -r requirements.txt

# Set up API key (one-time)
# Place your ElevenLabs API key in: f:\executedcode\tokens\elevenlabs

# Test the connection
C:\G\python.exe -m src.integrations.elevenlabs.client --test
```

## Structure

```
👁AI-Manifest/
├── src/
│   ├── integrations/
│   │   └── elevenlabs/    # ElevenLabs voice API client
│   ├── config/            # API settings, voice presets
│   └── utils/             # Shared utilities
├── tests/                 # pytest test suite
├── research/              # AI integration research
├── docs/                  # Architecture docs
├── tools/                 # CLI tools and scripts
└── logs/                  # Runtime logs
```

## Integrations

| Service | Status | Purpose |
|---------|--------|---------|
| ElevenLabs | Scaffolded | Voice synthesis, cloning, streaming |
