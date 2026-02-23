"""
Kait AI Intel: Personal Intelligent AI Sidekick

The Sidekick layer transforms the existing Kait Intelligence platform
into a self-evolving text+audio AI sidekick with hybrid local + cloud
intelligence.

Modules:
- reasoning_bank: SQLite-backed persistent memory for contexts, corrections, evolutions
- local_llm: Ollama integration for local model inference
- agents: Multi-agent sub-system (reflection, creativity, logic, tools, sentiment, claude_code)
- mood_tracker: Pure-data mood/state tracker (energy, warmth, confidence, kait, evolution)
- claude_code_ops: Autonomous Claude CLI operations (code generation, research, building)
- tts_engine: Multi-backend text-to-speech (ElevenLabs, OpenAI, Piper, macOS Say)
- ui_module: PyQt6 GUI with dark theme, chat, observatory, and processing monitor
- resonance: User preference tracking and sentiment analysis
- reflection: Periodic self-reflection and behavior evolution cycles
- tools: Local tool registry (math, file I/O, data query, system info)
- evolution: Self-evolution engine for progressive improvement
- claude_bridge: Cloud escalation to Claude API
- web_browser: Autonomous web browsing and research
- file_processor: Multi-format file processing (PDF, DOCX, images, etc.)
- matrix_bridge: Matrix protocol integration for external messaging
"""

__version__ = "4.0.0"
