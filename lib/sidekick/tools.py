"""
Kait Sidekick - Local Tool Registry

All tools run 100% locally. No external API calls, no arbitrary code execution.
Tools are sandboxed: file writes restricted to ~/.kait/sidekick_data/,
database queries are read-only and parameterized, math uses AST-safe evaluation.

Categories: math, file_io, data_query, system, utility
"""

from __future__ import annotations

import ast
import datetime
import glob
import json
import operator
import os
import platform
import re
import shutil
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Sandbox configuration
# ---------------------------------------------------------------------------

SIDEKICK_DATA_DIR = Path.home() / ".kait" / "sidekick_data"

# Directories file_reader is allowed to access (expanduser applied at runtime)
_ALLOWED_READ_ROOTS: List[Path] = [
    Path.home() / ".kait",
    Path.home() / "Documents",
    Path.home() / "Desktop",
]

# Maximum file size we will read (10 MB)
_MAX_READ_BYTES = 10 * 1024 * 1024

# Maximum result payload size returned from any tool (1 MB text)
_MAX_RESULT_CHARS = 1_000_000

# Safe math operators for the calculator
_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "int": int,
    "float": float,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_path_readable(raw: str) -> Path:
    """Resolve *raw* to an absolute path and verify it lives under an allowed root."""
    p = Path(raw).expanduser().resolve()
    for root in _ALLOWED_READ_ROOTS:
        try:
            p.relative_to(root.resolve())
            return p
        except ValueError:
            continue
    raise PermissionError(f"Path not in allowed read directories: {p}")


def _validate_path_writable(raw: str) -> Path:
    """Resolve *raw* and verify it lives under the sidekick data sandbox."""
    p = Path(raw).expanduser().resolve()
    sandbox = SIDEKICK_DATA_DIR.resolve()
    try:
        p.relative_to(sandbox)
    except ValueError:
        raise PermissionError(
            f"Writes restricted to {SIDEKICK_DATA_DIR}; got {p}"
        )
    return p


def _truncate(text: str, limit: int = _MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated at {limit} chars]"


def _safe_eval_expr(node: ast.AST) -> Any:
    """Recursively evaluate an AST node using only safe operations."""
    if isinstance(node, ast.Expression):
        return _safe_eval_expr(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(f"Unsupported constant type: {type(node.value).__name__}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval_expr(node.left)
        right = _safe_eval_expr(node.right)
        # Guard against absurdly large exponents
        if op_type is ast.Pow and isinstance(right, (int, float)) and abs(right) > 10000:
            raise ValueError("Exponent too large")
        return _SAFE_OPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return _SAFE_OPS[op_type](_safe_eval_expr(node.operand))

    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _SAFE_FUNCTIONS:
            args = [_safe_eval_expr(a) for a in node.args]
            return _SAFE_FUNCTIONS[node.func.id](*args)
        raise ValueError("Function calls restricted to: " + ", ".join(_SAFE_FUNCTIONS))

    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


# ---------------------------------------------------------------------------
# Tool dataclass
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """A single local tool with execution logic and usage tracking."""

    name: str
    description: str
    category: str  # math, file_io, data_query, system, utility
    _execute_fn: Callable[[Dict[str, Any]], Dict[str, Any]]

    # Runtime stats (not part of identity)
    invocation_count: int = field(default=0, repr=False)
    success_count: int = field(default=0, repr=False)
    failure_count: int = field(default=0, repr=False)
    total_latency_ms: float = field(default=0.0, repr=False)

    def execute(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Run the tool, track stats, and return a result dict."""
        start = time.monotonic()
        try:
            result = self._execute_fn(args)
            self.success_count += 1
            result["success"] = True
        except Exception as exc:
            result = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
            self.failure_count += 1
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            self.invocation_count += 1
            self.total_latency_ms += elapsed_ms
            result["latency_ms"] = round(elapsed_ms, 2)
        return result

    @property
    def avg_latency_ms(self) -> float:
        if self.invocation_count == 0:
            return 0.0
        return round(self.total_latency_ms / self.invocation_count, 2)

    @property
    def success_rate(self) -> float:
        if self.invocation_count == 0:
            return 0.0
        return round(self.success_count / self.invocation_count, 4)

    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "invocation_count": self.invocation_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
        }


# ---------------------------------------------------------------------------
# Built-in tool implementations
# ---------------------------------------------------------------------------

def _calculator(args: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a math expression safely via AST parsing.

    Args:
        expression (str): The math expression to evaluate.
    """
    expr = str(args.get("expression", "")).strip()
    if not expr:
        raise ValueError("Missing 'expression' argument")

    tree = ast.parse(expr, mode="eval")
    result = _safe_eval_expr(tree)
    return {"expression": expr, "result": result}


def _file_reader(args: Dict[str, Any]) -> Dict[str, Any]:
    """Read a local file with path validation.

    Args:
        path (str): Absolute or ~-relative path to read.
        encoding (str): File encoding (default utf-8).
        max_lines (int): Optional line limit.
    """
    raw_path = str(args.get("path", "")).strip()
    if not raw_path:
        raise ValueError("Missing 'path' argument")

    p = _validate_path_readable(raw_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    if not p.is_file():
        raise IsADirectoryError(f"Not a file: {p}")
    if p.stat().st_size > _MAX_READ_BYTES:
        raise ValueError(f"File exceeds {_MAX_READ_BYTES} byte limit")

    encoding = str(args.get("encoding", "utf-8"))
    text = p.read_text(encoding=encoding, errors="replace")

    max_lines = args.get("max_lines")
    if max_lines is not None:
        lines = text.splitlines(keepends=True)
        text = "".join(lines[: int(max_lines)])

    return {
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "content": _truncate(text),
    }


def _file_writer(args: Dict[str, Any]) -> Dict[str, Any]:
    """Write content to the sidekick sandbox directory.

    Args:
        path (str): Relative or absolute path under ~/.kait/sidekick_data/.
        content (str): Text content to write.
        append (bool): Append instead of overwrite (default False).
    """
    raw_path = str(args.get("path", "")).strip()
    content = str(args.get("content", ""))
    if not raw_path:
        raise ValueError("Missing 'path' argument")

    # If relative, anchor under sandbox
    if not os.path.isabs(raw_path) and not raw_path.startswith("~"):
        raw_path = str(SIDEKICK_DATA_DIR / raw_path)

    p = _validate_path_writable(raw_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if args.get("append", False) else "w"
    with p.open(mode, encoding="utf-8") as f:
        f.write(content)

    return {
        "path": str(p),
        "bytes_written": len(content.encode("utf-8")),
        "mode": "append" if mode == "a" else "overwrite",
    }


def _file_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """Glob-based file search in specified directories.

    Args:
        pattern (str): Glob pattern (e.g. '*.json', '**/*.py').
        directory (str): Directory to search in (must be in allowed roots).
        max_results (int): Maximum results to return (default 50).
    """
    pattern = str(args.get("pattern", "")).strip()
    directory = str(args.get("directory", "")).strip()
    max_results = int(args.get("max_results", 50))

    if not pattern:
        raise ValueError("Missing 'pattern' argument")
    if not directory:
        raise ValueError("Missing 'directory' argument")

    base = _validate_path_readable(directory)
    if not base.is_dir():
        raise NotADirectoryError(f"Not a directory: {base}")

    full_pattern = str(base / pattern)
    matches = sorted(glob.glob(full_pattern, recursive=True))[:max_results]

    return {
        "directory": str(base),
        "pattern": pattern,
        "matches": matches,
        "count": len(matches),
        "truncated": len(glob.glob(full_pattern, recursive=True)) > max_results,
    }


def _system_info(args: Dict[str, Any]) -> Dict[str, Any]:
    """Get local system statistics: CPU, memory, disk, platform.

    Args:
        (none required)
    """
    info: Dict[str, Any] = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "processor": platform.processor(),
        "hostname": platform.node(),
        "cpu_count": os.cpu_count(),
    }

    # Disk usage for home directory
    try:
        usage = shutil.disk_usage(str(Path.home()))
        info["disk"] = {
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "used_pct": round(usage.used / usage.total * 100, 1),
        }
    except Exception:
        info["disk"] = None

    # Memory via /proc/meminfo (Linux) or sysctl (macOS) -- best-effort
    info["memory"] = _get_memory_info()

    # GPU detection -- best-effort via nvidia-smi presence
    info["gpu"] = _detect_gpu()

    return info


def _get_memory_info() -> Optional[Dict[str, Any]]:
    """Best-effort memory information using only stdlib."""
    # Linux: read /proc/meminfo
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        try:
            text = meminfo.read_text()
            vals: Dict[str, int] = {}
            for line in text.splitlines():
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val_str = parts[1].strip().split()[0]
                    vals[key] = int(val_str)  # kB
            total_kb = vals.get("MemTotal", 0)
            avail_kb = vals.get("MemAvailable", vals.get("MemFree", 0))
            if total_kb:
                return {
                    "total_gb": round(total_kb / (1024 ** 2), 2),
                    "available_gb": round(avail_kb / (1024 ** 2), 2),
                    "used_pct": round((total_kb - avail_kb) / total_kb * 100, 1),
                }
        except Exception:
            pass

    # macOS: try sysctl
    if platform.system() == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["sysctl", "-n", "hw.memsize"], timeout=5
            ).decode().strip()
            total_bytes = int(out)
            return {
                "total_gb": round(total_bytes / (1024 ** 3), 2),
                "available_gb": None,  # not easily available without psutil
                "used_pct": None,
            }
        except Exception:
            pass

    return None


def _detect_gpu() -> Optional[Dict[str, Any]]:
    """Best-effort GPU detection using nvidia-smi."""
    try:
        import subprocess
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            timeout=5,
        ).decode().strip()
        gpus = []
        for line in out.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append({
                    "name": parts[0],
                    "memory_total_mb": int(parts[1]),
                    "memory_free_mb": int(parts[2]),
                })
        return {"gpus": gpus, "count": len(gpus)} if gpus else None
    except Exception:
        return None


def _datetime_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Current time, date math, and timezone conversion.

    Args:
        action (str): 'now', 'parse', 'add', 'diff', 'format' (default 'now').
        value (str): Date/time string for parse/add/diff.
        days (int): Days to add (for 'add' action).
        hours (int): Hours to add (for 'add' action).
        minutes (int): Minutes to add (for 'add' action).
        format (str): strftime format string (for 'format' action).
        value2 (str): Second date for 'diff' action.
    """
    action = str(args.get("action", "now")).lower()

    if action == "now":
        now = datetime.datetime.now()
        utc = datetime.datetime.utcnow()
        return {
            "local": now.isoformat(),
            "utc": utc.isoformat(),
            "timestamp": time.time(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "weekday": now.strftime("%A"),
        }

    if action == "parse":
        value = str(args.get("value", "")).strip()
        if not value:
            raise ValueError("Missing 'value' for parse action")
        # Try common formats
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%B %d, %Y",
        ):
            try:
                dt = datetime.datetime.strptime(value, fmt)
                return {"parsed": dt.isoformat(), "timestamp": dt.timestamp(), "format_matched": fmt}
            except ValueError:
                continue
        raise ValueError(f"Unable to parse date: {value}")

    if action == "add":
        value = str(args.get("value", "")).strip()
        base = datetime.datetime.now()
        if value:
            base = datetime.datetime.fromisoformat(value)
        delta = datetime.timedelta(
            days=int(args.get("days", 0)),
            hours=int(args.get("hours", 0)),
            minutes=int(args.get("minutes", 0)),
        )
        result_dt = base + delta
        return {"original": base.isoformat(), "result": result_dt.isoformat(), "delta": str(delta)}

    if action == "diff":
        v1 = str(args.get("value", "")).strip()
        v2 = str(args.get("value2", "")).strip()
        if not v1 or not v2:
            raise ValueError("'diff' needs 'value' and 'value2'")
        dt1 = datetime.datetime.fromisoformat(v1)
        dt2 = datetime.datetime.fromisoformat(v2)
        delta = dt2 - dt1
        return {
            "value1": dt1.isoformat(),
            "value2": dt2.isoformat(),
            "days": delta.days,
            "seconds": delta.seconds,
            "total_seconds": delta.total_seconds(),
        }

    if action == "format":
        value = str(args.get("value", "")).strip()
        fmt = str(args.get("format", "%Y-%m-%d %H:%M:%S"))
        dt = datetime.datetime.fromisoformat(value) if value else datetime.datetime.now()
        return {"formatted": dt.strftime(fmt), "format": fmt}

    raise ValueError(f"Unknown datetime action: {action}")


def _json_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Parse, format, and query JSON data.

    Args:
        action (str): 'parse', 'format', 'query', 'validate' (default 'parse').
        data (str|dict): JSON string or dict to process.
        path (str): Dot-notation path for 'query' (e.g. 'users.0.name').
        indent (int): Indentation for 'format' (default 2).
    """
    action = str(args.get("action", "parse")).lower()
    raw_data = args.get("data", "")

    # Parse the data if it is a string
    if isinstance(raw_data, str):
        raw_data = raw_data.strip()
        if not raw_data:
            raise ValueError("Missing 'data' argument")
        if action == "validate":
            try:
                json.loads(raw_data)
                return {"valid": True}
            except json.JSONDecodeError as e:
                return {"valid": False, "error": str(e)}
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")
    else:
        data = raw_data

    if action == "parse":
        return {"parsed": data, "type": type(data).__name__}

    if action == "format":
        indent = int(args.get("indent", 2))
        formatted = json.dumps(data, indent=indent, ensure_ascii=False, default=str)
        return {"formatted": _truncate(formatted)}

    if action == "query":
        path_str = str(args.get("path", "")).strip()
        if not path_str:
            raise ValueError("Missing 'path' for query action")
        current: Any = data
        for segment in path_str.split("."):
            if isinstance(current, dict):
                if segment not in current:
                    raise KeyError(f"Key not found: {segment}")
                current = current[segment]
            elif isinstance(current, list):
                try:
                    idx = int(segment)
                except ValueError:
                    raise ValueError(f"Expected integer index for list, got: {segment}")
                if idx < 0 or idx >= len(current):
                    raise IndexError(f"Index {idx} out of range (len={len(current)})")
                current = current[idx]
            else:
                raise TypeError(f"Cannot index into {type(current).__name__}")
        return {"path": path_str, "value": current}

    if action == "validate":
        return {"valid": True}

    raise ValueError(f"Unknown json action: {action}")


def _text_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """Rule-based text analysis: word count, summarize, extract keywords.

    Args:
        action (str): 'word_count', 'char_count', 'summarize', 'keywords', 'stats'.
        text (str): The text to analyze.
        max_keywords (int): Maximum keywords for 'keywords' action (default 10).
        max_sentences (int): Maximum sentences for 'summarize' action (default 3).
    """
    action = str(args.get("action", "stats")).lower()
    text = str(args.get("text", ""))
    if not text:
        raise ValueError("Missing 'text' argument")

    if action == "word_count":
        words = text.split()
        return {"word_count": len(words)}

    if action == "char_count":
        return {"char_count": len(text), "char_count_no_spaces": len(text.replace(" ", ""))}

    if action == "keywords":
        max_kw = int(args.get("max_keywords", 10))
        keywords = _extract_keywords(text, max_kw)
        return {"keywords": keywords, "count": len(keywords)}

    if action == "summarize":
        max_sent = int(args.get("max_sentences", 3))
        summary = _extractive_summary(text, max_sent)
        return {"summary": summary, "original_length": len(text), "summary_length": len(summary)}

    # Default: full stats
    words = text.split()
    sentences = _split_sentences(text)
    return {
        "char_count": len(text),
        "word_count": len(words),
        "sentence_count": len(sentences),
        "line_count": text.count("\n") + 1,
        "avg_word_length": round(sum(len(w) for w in words) / max(len(words), 1), 1),
        "avg_sentence_length": round(len(words) / max(len(sentences), 1), 1),
    }


# Stopwords for keyword extraction (small set, no dependencies)
_STOPWORDS = frozenset(
    "a an the and or but if in on at to for of is it was were be been "
    "being have has had do does did will would shall should can could may "
    "might must that this these those i me my we our you your he she they "
    "his her its their him them with from by as into through during before "
    "after above below between not no nor so very just about also then than "
    "more most some such only same too each every all any both few other "
    "another much many how what which who whom when where why because "
    "there here out up down off over under again further once".split()
)


def _extract_keywords(text: str, max_count: int) -> List[str]:
    """Extract keywords by term frequency, excluding stopwords."""
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    freq: Dict[str, int] = {}
    for w in words:
        if w not in _STOPWORDS:
            freq[w] = freq.get(w, 0) + 1
    ranked = sorted(freq.items(), key=lambda kv: kv[1], reverse=True)
    return [word for word, _ in ranked[:max_count]]


def _split_sentences(text: str) -> List[str]:
    """Split text into sentences (rule-based)."""
    raw = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in raw if s.strip()]


def _extractive_summary(text: str, max_sentences: int) -> str:
    """Simple extractive summarization: pick sentences with most keywords."""
    sentences = _split_sentences(text)
    if len(sentences) <= max_sentences:
        return text.strip()

    # Score each sentence by keyword density
    all_keywords = set(_extract_keywords(text, 20))
    scored = []
    for i, sent in enumerate(sentences):
        words = set(re.findall(r"[a-zA-Z]{3,}", sent.lower()))
        score = len(words & all_keywords)
        # Boost first sentence (usually important)
        if i == 0:
            score += 3
        scored.append((i, score, sent))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = sorted(scored[:max_sentences], key=lambda x: x[0])  # preserve order
    return " ".join(s for _, _, s in top)


def _data_query(args: Dict[str, Any]) -> Dict[str, Any]:
    """Query SQLite databases with read-only, parameterized access.

    Args:
        database (str): Path to SQLite database file.
        query (str): SQL SELECT query.
        params (list): Positional parameters for the query.
        max_rows (int): Maximum rows to return (default 100).
    """
    db_path = str(args.get("database", "")).strip()
    query = str(args.get("query", "")).strip()
    params = args.get("params", [])
    max_rows = int(args.get("max_rows", 100))

    if not db_path:
        raise ValueError("Missing 'database' argument")
    if not query:
        raise ValueError("Missing 'query' argument")

    # Validate path is readable
    p = _validate_path_readable(db_path)
    if not p.exists():
        raise FileNotFoundError(f"Database not found: {p}")

    # Enforce read-only: reject anything that is not a SELECT
    normalized = query.strip().upper()
    if not normalized.startswith("SELECT"):
        raise PermissionError("Only SELECT queries are allowed (read-only access)")

    # Reject dangerous keywords even inside a SELECT
    for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
                      "ATTACH", "DETACH", "PRAGMA", "REPLACE", "GRANT", "REVOKE"):
        # Match as whole word to avoid false positives in column names
        if re.search(rf"\b{forbidden}\b", normalized):
            raise PermissionError(f"Forbidden SQL keyword: {forbidden}")

    # Open read-only
    uri = f"file:{p}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(query, params if isinstance(params, (list, tuple)) else [])
        rows = cursor.fetchmany(max_rows)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        results = [dict(row) for row in rows]
        return {
            "columns": columns,
            "rows": results,
            "row_count": len(results),
            "truncated": len(results) >= max_rows,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Central registry for local sidekick tools.

    Manages tool registration, lookup, execution, and usage statistics.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool. Overwrites if the name already exists."""
        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> Optional[Tool]:
        """Retrieve a tool by name, or None."""
        return self._tools.get(tool_name)

    def execute(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Find and run a tool by name. Returns result dict."""
        tool = self._tools.get(tool_name)
        if tool is None:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(self._tools.keys()),
            }
        return tool.execute(args)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return metadata for all registered tools."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
            }
            for t in self._tools.values()
        ]

    def get_tool_stats(self) -> Dict[str, Any]:
        """Aggregate usage statistics for every registered tool."""
        per_tool = {}
        total_invocations = 0
        total_successes = 0
        total_failures = 0

        for t in self._tools.values():
            per_tool[t.name] = t.stats()
            total_invocations += t.invocation_count
            total_successes += t.success_count
            total_failures += t.failure_count

        return {
            "total_invocations": total_invocations,
            "total_successes": total_successes,
            "total_failures": total_failures,
            "overall_success_rate": (
                round(total_successes / total_invocations, 4)
                if total_invocations > 0
                else 0.0
            ),
            "tools": per_tool,
        }

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


# ---------------------------------------------------------------------------
# Web browsing tool implementations (require browser-use)
# ---------------------------------------------------------------------------

def _web_search(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search the web for a query.

    Args:
        query (str): The search query.
        num_results (int): Number of results to return (default 5).
    """
    query = str(args.get("query", "")).strip()
    if not query:
        raise ValueError("Missing 'query' argument")
    num_results = int(args.get("num_results", 5))

    try:
        from lib.sidekick.web_browser import web_search
        result = web_search(query, num_results=num_results)
        return {
            "result": result.content,
            "url": result.url,
            "urls_visited": result.urls_visited,
            "elapsed_s": result.elapsed_s,
            "cached": result.cached,
        }
    except ImportError:
        raise RuntimeError(
            "browser-use not installed. Install with: pip install 'browser-use>=0.11.0'"
        )


def _web_browse(args: Dict[str, Any]) -> Dict[str, Any]:
    """Navigate to a URL and extract its content.

    Args:
        url (str): The URL to visit.
        instruction (str): What to do or extract on the page (optional).
    """
    url = str(args.get("url", "")).strip()
    if not url:
        raise ValueError("Missing 'url' argument")
    instruction = str(args.get("instruction", "")).strip()

    try:
        from lib.sidekick.web_browser import web_browse
        result = web_browse(url, instruction=instruction)
        return {
            "result": result.content,
            "title": result.title,
            "url": result.url,
            "urls_visited": result.urls_visited,
            "elapsed_s": result.elapsed_s,
        }
    except ImportError:
        raise RuntimeError(
            "browser-use not installed. Install with: pip install 'browser-use>=0.11.0'"
        )


def _web_extract(args: Dict[str, Any]) -> Dict[str, Any]:
    """Extract specific information from a web page.

    Args:
        url (str): The URL to visit.
        query (str): What to extract from the page.
    """
    url = str(args.get("url", "")).strip()
    query = str(args.get("query", "")).strip()
    if not url:
        raise ValueError("Missing 'url' argument")
    if not query:
        raise ValueError("Missing 'query' argument")

    try:
        from lib.sidekick.web_browser import web_extract
        result = web_extract(url, query)
        return {
            "result": result.content,
            "extracted_data": result.extracted_data,
            "url": result.url,
            "elapsed_s": result.elapsed_s,
        }
    except ImportError:
        raise RuntimeError(
            "browser-use not installed. Install with: pip install 'browser-use>=0.11.0'"
        )


def _web_task(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute an autonomous web browsing task.

    Args:
        task (str): Natural language description of the browsing task.
    """
    task = str(args.get("task", "")).strip()
    if not task:
        raise ValueError("Missing 'task' argument")

    try:
        from lib.sidekick.web_browser import web_task
        result = web_task(task)
        return {
            "result": result.content,
            "url": result.url,
            "urls_visited": result.urls_visited,
            "extracted_data": result.extracted_data,
            "elapsed_s": result.elapsed_s,
        }
    except ImportError:
        raise RuntimeError(
            "browser-use not installed. Install with: pip install 'browser-use>=0.11.0'"
        )


# ---------------------------------------------------------------------------
# Factory: create a registry pre-loaded with all built-in tools
# ---------------------------------------------------------------------------

def create_default_registry() -> ToolRegistry:
    """Build a ToolRegistry with all built-in sidekick tools."""
    registry = ToolRegistry()

    registry.register(Tool(
        name="calculator",
        description="Evaluate math expressions safely (supports +, -, *, /, //, %, **, abs, round, min, max).",
        category="math",
        _execute_fn=_calculator,
    ))

    registry.register(Tool(
        name="file_reader",
        description="Read local files (path validated against allowed directories).",
        category="file_io",
        _execute_fn=_file_reader,
    ))

    registry.register(Tool(
        name="file_writer",
        description="Write to files inside the sidekick sandbox (~/.kait/sidekick_data/).",
        category="file_io",
        _execute_fn=_file_writer,
    ))

    registry.register(Tool(
        name="file_search",
        description="Glob-based file search within allowed directories.",
        category="file_io",
        _execute_fn=_file_search,
    ))

    registry.register(Tool(
        name="system_info",
        description="Get local system statistics: CPU, memory, disk, platform, GPU.",
        category="system",
        _execute_fn=_system_info,
    ))

    registry.register(Tool(
        name="datetime_tool",
        description="Current time, date parsing, date math, and formatting.",
        category="utility",
        _execute_fn=_datetime_tool,
    ))

    registry.register(Tool(
        name="json_tool",
        description="Parse, format, query, and validate JSON data.",
        category="utility",
        _execute_fn=_json_tool,
    ))

    registry.register(Tool(
        name="text_tool",
        description="Text analysis: word count, keyword extraction, extractive summarization, stats.",
        category="utility",
        _execute_fn=_text_tool,
    ))

    registry.register(Tool(
        name="data_query",
        description="Query SQLite databases (read-only, parameterized SELECT only).",
        category="data_query",
        _execute_fn=_data_query,
    ))

    # Web browsing tools (require browser-use; graceful degradation)
    registry.register(Tool(
        name="web_search",
        description="Search the web and return results (requires browser-use).",
        category="browser",
        _execute_fn=_web_search,
    ))

    registry.register(Tool(
        name="web_browse",
        description="Navigate to a URL and extract page content (requires browser-use).",
        category="browser",
        _execute_fn=_web_browse,
    ))

    registry.register(Tool(
        name="web_extract",
        description="Extract specific information from a web page (requires browser-use).",
        category="browser",
        _execute_fn=_web_extract,
    ))

    registry.register(Tool(
        name="web_task",
        description="Execute an autonomous web browsing task (requires browser-use).",
        category="browser",
        _execute_fn=_web_task,
    ))

    return registry
