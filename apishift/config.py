"""Settings, read from environment variables or a `.env` file. Everything has a default."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


for _p in (Path.cwd() / ".env", PROJECT_ROOT / ".env"):
    _load_dotenv(_p)


def _env(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


@dataclass
class Settings:
    # auto = Groq if GROQ_API_KEY is set, else Claude if ANTHROPIC_API_KEY is set, else none (codemods only)
    provider: str = field(default_factory=lambda: _env("APISHIFT_PROVIDER", "auto").lower())
    groq_model: str = field(default_factory=lambda: _env("APISHIFT_GROQ_MODEL", "openai/gpt-oss-120b"))
    claude_model: str = field(default_factory=lambda: _env("APISHIFT_CLAUDE_MODEL", "claude-opus-5-5"))
    effort: str = field(default_factory=lambda: _env("APISHIFT_EFFORT", "medium"))
    max_attempts: int = field(default_factory=lambda: int(_env("APISHIFT_MAX_ATTEMPTS", "3")))
    test_timeout: int = field(default_factory=lambda: int(_env("APISHIFT_TEST_TIMEOUT", "300")))

    @property
    def resolved_provider(self) -> str:
        if self.provider in ("groq", "claude", "none"):
            return self.provider
        if os.environ.get("GROQ_API_KEY"):
            return "groq"
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return "claude"
        return "none"

    @property
    def model(self) -> str:
        return {"groq": self.groq_model, "claude": self.claude_model}.get(self.resolved_provider, "none")
