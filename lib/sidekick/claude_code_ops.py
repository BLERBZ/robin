"""Claude Code autonomous operations for the Kait AI sidekick.

Enables the sidekick to invoke the ``claude`` CLI for code generation,
research, and project building.  All operations run as subprocesses with
configurable timeouts and working directories.

Usage::

    ops = ClaudeCodeOps()
    if ops.is_available():
        result = ops.execute("Write a Python hello world script")
        print(result.output)
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("kait.sidekick.claude_code")


# ===================================================================
# Result dataclass
# ===================================================================

@dataclass
class ClaudeCodeResult:
    """Result of a Claude Code CLI operation.

    Attributes
    ----------
    success:
        Whether the operation completed without errors.
    output:
        Full text output from the claude CLI.
    files_created:
        List of file paths created/modified during the operation.
    duration_s:
        Wall-clock time in seconds.
    error:
        Error message if the operation failed.
    """

    success: bool
    output: str
    files_created: List[str] = field(default_factory=list)
    duration_s: float = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output[:2000],
            "files_created": self.files_created,
            "duration_s": round(self.duration_s, 2),
            "error": self.error,
        }


# ===================================================================
# ClaudeCodeOps
# ===================================================================

class ClaudeCodeOps:
    """Interface to the ``claude`` CLI for autonomous code operations.

    Methods
    -------
    is_available()
        Check if the ``claude`` CLI binary exists on PATH.
    execute(prompt, workdir, timeout)
        Run an arbitrary prompt through ``claude --print``.
    generate_code(description, language, output_path)
        Generate code for a given description and optionally save it.
    research(topic)
        Research a topic using Claude's knowledge.
    build_project(spec, workdir)
        Build a project from a specification.
    """

    _DEFAULT_TIMEOUT = 120  # seconds

    def __init__(self) -> None:
        self._claude_path: Optional[str] = shutil.which("claude")
        if self._claude_path:
            logger.info("Claude CLI found at %s", self._claude_path)
        else:
            logger.info("Claude CLI not found on PATH")

    # ---- availability ------------------------------------------------------

    @staticmethod
    def is_available() -> bool:
        """Check if the ``claude`` CLI exists on PATH."""
        return shutil.which("claude") is not None

    # ---- core execution ----------------------------------------------------

    def execute(
        self,
        prompt: str,
        workdir: Optional[str] = None,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> ClaudeCodeResult:
        """Run a prompt through ``claude --print`` and return the result.

        Parameters
        ----------
        prompt:
            The instruction/prompt to send to Claude CLI.
        workdir:
            Working directory for the subprocess. Defaults to cwd.
        timeout:
            Maximum seconds to wait for completion.
        """
        if not self._claude_path:
            return ClaudeCodeResult(
                success=False,
                output="",
                error="Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
            )

        start = time.monotonic()
        cwd = workdir or os.getcwd()

        try:
            proc = subprocess.run(
                [self._claude_path, "--print", prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd,
            )
            elapsed = time.monotonic() - start

            if proc.returncode != 0:
                return ClaudeCodeResult(
                    success=False,
                    output=proc.stdout,
                    error=proc.stderr.strip() or f"Exit code {proc.returncode}",
                    duration_s=elapsed,
                )

            return ClaudeCodeResult(
                success=True,
                output=proc.stdout,
                duration_s=elapsed,
            )

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            return ClaudeCodeResult(
                success=False,
                output="",
                error=f"Timed out after {timeout}s",
                duration_s=elapsed,
            )
        except OSError as exc:
            elapsed = time.monotonic() - start
            return ClaudeCodeResult(
                success=False,
                output="",
                error=f"OS error: {exc}",
                duration_s=elapsed,
            )

    # ---- high-level operations ---------------------------------------------

    def generate_code(
        self,
        description: str,
        language: str = "python",
        output_path: Optional[str] = None,
    ) -> ClaudeCodeResult:
        """Generate code for a given description.

        Parameters
        ----------
        description:
            What the code should do.
        language:
            Target programming language.
        output_path:
            If provided, save the generated code to this file.
        """
        prompt = (
            f"Generate {language} code for the following:\n\n"
            f"{description}\n\n"
            f"Output only the code, no explanations."
        )

        result = self.execute(prompt)

        if result.success and output_path:
            try:
                path = Path(output_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(result.output, encoding="utf-8")
                result.files_created.append(str(path))
                logger.info("Generated code saved to %s", path)
            except OSError as exc:
                logger.warning("Failed to save generated code: %s", exc)

        return result

    def research(self, topic: str) -> ClaudeCodeResult:
        """Research a topic using Claude CLI.

        Parameters
        ----------
        topic:
            The topic to research.
        """
        prompt = (
            f"Research the following topic and provide a comprehensive summary:\n\n"
            f"{topic}\n\n"
            f"Include key concepts, current state of the art, and practical applications."
        )
        return self.execute(prompt, timeout=180)

    def build_project(
        self,
        spec: str,
        workdir: Optional[str] = None,
    ) -> ClaudeCodeResult:
        """Build a project from a specification.

        Parameters
        ----------
        spec:
            Project specification describing what to build.
        workdir:
            Directory to build the project in.
        """
        prompt = (
            f"Build a project based on this specification:\n\n"
            f"{spec}\n\n"
            f"Create all necessary files and provide setup instructions."
        )
        return self.execute(prompt, workdir=workdir, timeout=300)


# ===================================================================
# Module exports
# ===================================================================

__all__ = [
    "ClaudeCodeOps",
    "ClaudeCodeResult",
]
