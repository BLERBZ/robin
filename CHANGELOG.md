# Changelog

All notable changes to Robin will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-25

### Added
- **LLM Circuit Breakers** — Per-provider automatic failover with configurable thresholds
- **LLM Observability** — Full telemetry: latency, tokens, cost tracking per call
- **Olla Integration** — Local multi-Ollama load balancing for local inference
- **LiteLLM Gateway** — 100+ cloud provider access through universal proxy
- **Unified LLM Gateway** — Intelligent routing across local and cloud backends
- **OpenAI Bridge** — GPT models as a routing target alongside Claude
- **LLM Router** — ML-based classification to route queries to optimal backend
- **LLM Cost Tracker** — Per-session and per-provider cost aggregation
- **LLM Learning Bridge** — Connect LLM outcomes back to the intelligence loop
- **Vault Viewer** — Obsidian brain panel integration for GUI
- **Archive Worker** — Background data management for sidekick

### Changed
- Enhanced `.env.example` with all LLM architecture config options
- Improved bridge cycle with circuit breaker integration
- Updated diagnostics with LLM health monitoring
- Refined service control with new backend lifecycle management

### Infrastructure
- 11 new test files covering all LLM modules
- Install scripts for Olla and LiteLLM setup
- Architecture documentation for LLM subsystem

## [0.1.0] - 2026-02-23

### Added
- Initial release of Robin — BLERBZ's Own Open Source Sidekick
- Self-evolving intelligence runtime (event queue, bridge cycle, cognitive learner)
- EIDOS system — prediction-outcome loops with distillation engine
- Advisory engine for pre-tool guidance with quality gating
- Multi-backend TTS (ElevenLabs, OpenAI, Piper, macOS Say)
- Intelligent LLM routing (local Ollama + cloud Claude/OpenAI)
- Importance scoring at ingestion (semantic + rule-based)
- Domain chips — pluggable expertise modules
- Cognitive learner with contradiction detection
- Memory banks with semantic retrieval
- GitHub integration for OS project management
- Release pipeline with SemVer and changelog generation
- OS learning engine for self-improvement
- CLI commands for all operations
- Obsidian Observatory integration (465+ page vault)
- Hot-reloadable tuneables with schema validation
- Comprehensive test suite (136+ tests)
- GitHub Actions workflows (CI, sync, release, health checks)
- Full documentation suite
- Community health files (README, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY)
