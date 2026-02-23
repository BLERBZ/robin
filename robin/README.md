# Robin

**BLERBZ's Own Open Source Sidekick**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![BLERBZ OS](https://img.shields.io/badge/BLERBZ-Open%20Source-blue.svg)](https://blerbz.com)
[![Managed by Kait](https://img.shields.io/badge/Managed%20by-Kait%20OS%20Sidekick-green.svg)](https://github.com/blerbz/kait-intel)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)

## Overview

Robin is an open-source AI sidekick built by [BLERBZ LLC](https://blerbz.com).
It provides a self-evolving intelligence layer for AI agents — text and audio/voice only,
designed to expand with skills and additional knowledge.

Robin is the community edition of the Kait intelligence platform, optimized for
open-source contributors and developers.

## Features

- **Self-evolving intelligence** — Learns from every interaction
- **Text & audio/voice interface** — No visual UI, pure efficiency
- **Skill-based expansion** — Add new capabilities as skills
- **GitHub integration** — Full OS project lifecycle management
- **Multi-backend TTS** — ElevenLabs, OpenAI, Piper, macOS Say
- **Autonomous operation** — Can manage projects independently
- **Cognitive learning** — Distills insights from patterns
- **Advisory system** — Pre-tool guidance based on learned patterns

## Quick Start

```bash
# Clone Robin
git clone https://github.com/blerbz/robin.git
cd robin

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install with all features
pip install -e ".[dev,tts,services]"

# Check status
robin status

# View learnings
robin learnings

# Run health check
robin health
```

## Architecture

```
Input Layer → Event Queue → Bridge Cycle → Learning → Advisory → Output
     ↓                          ↓              ↓
  Adapters                  Memory Banks    Cognitive
  (stdin,                   (Project-       Insights
   webhooks,                 scoped)
   Claude Code)
                                              ↓
                                    Sidekick (TTS, Agents, Reasoning)
```

### Core Components

| Component | Purpose |
|-----------|---------|
| **Event Queue** | Ultra-fast event capture (<10ms) |
| **Bridge Cycle** | Signal extraction and processing |
| **Cognitive Learner** | Insight distillation and storage |
| **Advisory Engine** | Pre-tool guidance generation |
| **Memory Banks** | Project-scoped memory retrieval |
| **Semantic Retriever** | Embeddings-based fast retrieval |
| **EIDOS** | Distillation with prediction-outcome tracking |
| **Chips** | Pluggable domain expertise modules |
| **TTS Engine** | Multi-backend text-to-speech |

## Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude API key (optional) | — |
| `ROBIN_TTS_BACKEND` | TTS backend: auto, elevenlabs, openai, piper, say | auto |
| `ROBIN_LLM_TEMPERATURE` | LLM temperature | 0.7 |

See [Configuration Guide](docs/TUNEABLES.md) for all options.

## Contributing

We welcome contributions! Please read our [Contributing Guide](CONTRIBUTING.md) first.

### Good First Issues

Look for issues labeled [`good first issue`](https://github.com/blerbz/robin/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) to get started.

### Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

# Run specific test
pytest tests/test_queue.py -v
```

### Commit Convention

We follow conventional commits:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation
- `refactor:` Code refactoring
- `test:` Adding tests
- `chore:` Maintenance

## Documentation

- [Architecture Guide](docs/ARCHITECTURE.md)
- [Adapters Guide](docs/adapters.md)
- [Configuration Reference](docs/TUNEABLES.md)
- [Advisory System](docs/ADVISORY_SYSTEM.md)
- [Chips (Domain Modules)](docs/CHIPS.md)
- [EIDOS Guide](docs/EIDOS_GUIDE.md)

## Community

- [GitHub Discussions](https://github.com/blerbz/robin/discussions) — Questions, ideas, feedback
- [Issue Tracker](https://github.com/blerbz/robin/issues) — Bug reports, feature requests
- [Contributing Guide](CONTRIBUTING.md) — How to contribute

## Roadmap

- [ ] Enhanced autonomous project management
- [ ] Plugin system for custom skills
- [ ] Multi-language support
- [ ] Browser-based interaction mode
- [ ] Advanced analytics dashboard

## License

MIT License — see [LICENSE](LICENSE) for details.

## About

Robin is built and maintained by [BLERBZ LLC](https://blerbz.com).
Based on the [Kait Intelligence Platform](https://github.com/blerbz/kait-intel).

Managed by [Kait OS Sidekick](https://github.com/blerbz/kait-intel) — BLERBZ's AI agent for open-source.
