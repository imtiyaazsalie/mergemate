"""Configuration system for MergeMate.

Replaces the Dynaconf global singleton with an injectable Config class.
Settings are loaded from TOML files and can be overridden per-invocation.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


@dataclass
class ModelConfig:
    """AI model configuration."""

    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.2
    max_tokens: int = 4096
    fallback_models: list[str] = field(default_factory=list)
    custom_max_tokens: Optional[int] = None


@dataclass
class GitConfig:
    """Git provider configuration."""

    provider: str = "github"
    base_url: str = ""
    deployment_type: str = "user"
    ratelimit_retries: int = 5


@dataclass
class ReviewConfig:
    """PR review tool configuration."""

    num_max_findings: int = 10
    extra_instructions: str = ""
    require_score_review: bool = False
    enable_review_labels_effort: bool = True
    persistent_comment: bool = True
    inline_code_comments: bool = False


@dataclass
class AppConfig:
    """Top-level application configuration."""

    model: ModelConfig = field(default_factory=ModelConfig)
    git: GitConfig = field(default_factory=GitConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    verbosity_level: int = 0
    publish_output: bool = True
    cli_mode: bool = False
    response_language: str = "en-us"
    ai_timeout: int = 120

    # Raw settings loaded from TOML files (for tool-specific sections)
    _raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_settings_dir(cls, settings_dir: Path | str, secrets_dir: Optional[Path | str] = None) -> AppConfig:
        """Load configuration from a settings directory containing TOML files.

        Args:
            settings_dir: Path to directory containing .toml settings files.
            secrets_dir: Optional path to directory containing .secrets.toml.

        Returns:
            Configured AppConfig instance.
        """
        settings_dir = Path(settings_dir)
        raw: dict[str, Any] = {}

        # Load all TOML files from the settings directory
        for toml_file in sorted(settings_dir.glob("*.toml")):
            if toml_file.name.endswith(".secrets.toml"):
                continue
            section = toml_file.stem
            try:
                with open(toml_file, "rb") as f:
                    raw[section] = tomllib.load(f)
            except Exception:
                raw[section] = {}

        # Load subdirectories (e.g., code_suggestions/)
        for subdir in settings_dir.iterdir():
            if subdir.is_dir():
                for toml_file in sorted(subdir.glob("*.toml")):
                    section = toml_file.stem
                    try:
                        with open(toml_file, "rb") as f:
                            raw[section] = tomllib.load(f)
                    except Exception:
                        raw[section] = {}

        # Load secrets if available
        secrets_path = secrets_dir or settings_dir
        secrets_path = Path(secrets_path)
        secrets_file = secrets_path / ".secrets.toml"
        if secrets_file.exists():
            try:
                with open(secrets_file, "rb") as f:
                    raw[".secrets"] = tomllib.load(f)
            except Exception:
                pass

        return cls._from_raw(raw)

    @classmethod
    def _from_raw(cls, raw: dict[str, Any]) -> AppConfig:
        """Build AppConfig from raw settings dict."""
        config_section = raw.get("configuration", raw.get("config", {}))
        # configuration.toml uses a [config] header, creating double-nesting
        # with the filename section. Unwrap one level if needed.
        if "config" in config_section and isinstance(config_section["config"], dict):
            config_section = config_section["config"]

        return cls(
            model=ModelConfig(
                provider=config_section.get("model_provider", "openai"),
                model=config_section.get("model", "gpt-4o"),
                temperature=float(config_section.get("temperature", 0.2)),
                max_tokens=int(config_section.get("max_model_tokens", 4096)),
                fallback_models=config_section.get("fallback_models", []),
                custom_max_tokens=config_section.get("custom_model_max_tokens"),
            ),
            git=GitConfig(
                provider=config_section.get("git_provider", "github"),
                base_url=config_section.get("git_base_url", ""),
                deployment_type=config_section.get("deployment_type", "user"),
                ratelimit_retries=int(config_section.get("ratelimit_retries", 5)),
            ),
            review=ReviewConfig(
                num_max_findings=int(raw.get("pr_reviewer", {}).get("num_max_findings", 10)),
                extra_instructions=str(raw.get("pr_reviewer", {}).get("extra_instructions", "")),
                require_score_review=bool(raw.get("pr_reviewer", {}).get("require_score_review", False)),
                enable_review_labels_effort=bool(raw.get("pr_reviewer", {}).get("enable_review_labels_effort", True)),
                persistent_comment=bool(raw.get("pr_reviewer", {}).get("persistent_comment", True)),
                inline_code_comments=bool(raw.get("pr_reviewer", {}).get("inline_code_comments", False)),
            ),
            verbosity_level=int(config_section.get("verbosity_level", 0)),
            publish_output=bool(config_section.get("publish_output", True)),
            cli_mode=bool(config_section.get("cli_mode", False)),
            response_language=str(config_section.get("response_language", "en-us")),
            ai_timeout=int(config_section.get("ai_timeout", 120)),
            _raw=raw,
        )

    def merge_repo_config(self, toml_content: str) -> AppConfig:
        """Merge settings from a repository-level .mergemate.toml file.

        Repository settings override the defaults but don't replace entire sections.
        """
        try:
            repo_raw = tomllib.loads(toml_content)
        except Exception:
            return self

        merged = dict(self._raw)
        for section, values in repo_raw.items():
            if section in merged and isinstance(merged[section], dict) and isinstance(values, dict):
                merged[section] = {**merged[section], **values}
            else:
                merged[section] = values

        return self._from_raw(merged)

    def get_tool_config(self, tool_name: str) -> dict[str, Any]:
        """Get raw configuration for a specific tool."""
        return self._raw.get(tool_name, {})

    def get_prompts(self, tool_name: str) -> dict[str, str]:
        """Get system/user prompt templates for a tool."""
        prompts = self._raw.get(f"pr_{tool_name}_prompts", self._raw.get(tool_name, {}))
        return {
            "system": prompts.get("system", ""),
            "user": prompts.get("user", ""),
        }

    def get_secret(self, key_path: str) -> Optional[str]:
        """Get a secret value by dot-notation path (e.g., 'openai.key')."""
        current = self._raw.get(".secrets", {})
        for part in key_path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return str(current) if current else None

    @classmethod
    def load_default(cls) -> AppConfig:
        """Load the default configuration bundled with MergeMate."""
        settings_dir = Path(__file__).parent.parent / "settings"
        return cls.from_settings_dir(settings_dir)

    def with_overrides(self, **overrides: Any) -> AppConfig:
        """Return a new Config with overridden values.

        Accepts dot-notation keys like 'model.model=gpt-4'.
        """
        result = AppConfig(
            model=self.model,
            git=self.git,
            review=self.review,
            verbosity_level=self.verbosity_level,
            publish_output=self.publish_output,
            cli_mode=self.cli_mode,
            response_language=self.response_language,
            ai_timeout=self.ai_timeout,
            _raw=dict(self._raw),
        )

        for key, value in overrides.items():
            if key == "model":
                result.model.model = value
            elif key == "model_provider":
                result.model.provider = value
            elif key == "temperature":
                result.model.temperature = float(value)
            elif key == "git_provider":
                result.git.provider = value
            elif key == "publish_output":
                result.publish_output = bool(value)
            elif key == "cli_mode":
                result.cli_mode = bool(value)
            elif key == "verbosity_level":
                result.verbosity_level = int(value)

        return result
