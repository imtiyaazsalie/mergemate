"""Pytest configuration — prevents circular imports during test collection.

The ``mergemate.config_loader`` module triggers Dynaconf initialisation at import
time, which in turn tries to import ``mergemate.custom_merge_loader`` while
``mergemate.log`` is still being initialised, causing a circular import.

This conftest pre-registers a simplified custom merge loader that loads TOML
settings directly (using loguru instead of the project's logger) so that the
Dynaconf bootstrap can complete without the circular dependency.
"""

import sys
import types
from pathlib import Path

import tomllib
from jinja2.exceptions import SecurityError
from loguru import logger

# ---------------------------------------------------------------------------
# validate_file_security — exact copy from mergemate/custom_merge_loader.py
# (does not import mergemate.log, so no circular-import risk)
# ---------------------------------------------------------------------------

FORBIDDEN_KEYS_TO_REASONS = {
    "dynaconf_include": "allows including other config files dynamically",
    "dynaconf_includes": "allows including other config files dynamically",
    "includes": "allows including other config files dynamically",
    "preload": "allows preloading files with potential code execution",
    "preload_for_dynaconf": "allows preloading files with potential code execution",
    "preloads": "allows preloading files with potential code execution",
    "dynaconf_merge": "allows manipulating merge behavior",
    "dynaconf_merge_enabled": "allows manipulating merge behavior",
    "merge_enabled": "allows manipulating merge behavior",
    "loaders_for_dynaconf": "allows overriding loaders to execute arbitrary code",
    "loaders": "allows overriding loaders to execute arbitrary code",
    "core_loaders": "allows overriding core loaders",
    "core_loaders_for_dynaconf": "allows overriding core loaders",
    "settings_module": "allows loading Python modules with code execution",
    "settings_file_for_dynaconf": "could override settings file location",
    "settings_files_for_dynaconf": "could override settings file location",
    "envvar_prefix": "allows changing environment variable prefix",
    "envvar_prefix_for_dynaconf": "allows changing environment variable prefix",
}

MAX_TOML_DEPTH = 50
MAX_TOML_SIZE_IN_BYTES = 100 * 1024 * 1024  # 100 MB


def validate_file_security(file_data: dict, filename: str) -> None:
    """Validate that the config file does not contain security-sensitive directives.

    This is a faithful copy of the real ``validate_file_security`` from
    ``mergemate.custom_merge_loader`` — it does not import ``mergemate.log``,
    so it can live in this conftest without circular-import issues.
    """

    def _check(data, path: str = "", max_depth: int = MAX_TOML_DEPTH) -> None:
        if max_depth <= 0:
            raise SecurityError(f"Maximum nesting depth exceeded at {path}. Possible attempt to cause stack overflow.")
        for key, value in data.items():
            full_path = f"{path}.{key}" if path else key
            if key.lower() in FORBIDDEN_KEYS_TO_REASONS:
                raise SecurityError(
                    f"Security error in {filename}: "
                    f"Forbidden directive '{key}' found at {full_path}. "
                    f"Reason: {FORBIDDEN_KEYS_TO_REASONS[key.lower()]}"
                )
            if isinstance(value, dict):
                _check(value, path=full_path, max_depth=max_depth - 1)

    _check(file_data, max_depth=MAX_TOML_DEPTH)


# ---------------------------------------------------------------------------
# load — simplified TOML loader (same merge semantics as the real loader)
# ---------------------------------------------------------------------------


def load(obj, env=None, silent=True, key=None, filename=None):
    """Simplified TOML loader — same merge semantics as the real loader but
    avoids importing ``mergemate.log`` (the source of the circular import)."""
    settings_files = (
        obj.settings_files
        if hasattr(obj, "settings_files")
        else (obj.settings_file if hasattr(obj, "settings_file") else [])
    )
    if not settings_files or not isinstance(settings_files, list):
        logger.warning("No settings files specified; skipping loader")
        return

    # Security: Check for forbidden configuration options (matching real loader)
    if hasattr(obj, "includes") and obj.includes:
        if not silent:
            raise SecurityError("Configuration includes forbidden option: 'includes'. Skipping loading.")
        logger.error("Configuration includes forbidden option: 'includes'. Skipping loading.")
        return
    if hasattr(obj, "preload") and obj.preload:
        if not silent:
            raise SecurityError("Configuration includes forbidden option: 'preload'. Skipping loading.")
        logger.error("Configuration includes forbidden option: 'preload'. Skipping loading.")
        return

    accumulated: dict[str, dict] = {}
    for settings_file in settings_files:
        try:
            file_path = Path(settings_file)
            if file_path.suffix.lower() != ".toml":
                logger.warning(f"Only .toml files are allowed. Skipping: {settings_file}")
                continue
            if not file_path.exists():
                logger.warning(f"Settings file not found: {settings_file}. Skipping it.")
                continue
            if file_path.stat().st_size > MAX_TOML_SIZE_IN_BYTES:
                logger.warning(
                    f"Settings file too large (> {MAX_TOML_SIZE_IN_BYTES} bytes): {settings_file}. Skipping it."
                )
                continue

            with open(file_path, "rb") as f:
                file_data = tomllib.load(f)

            if not isinstance(file_data, dict):
                logger.warning(f"TOML root is not a table in '{settings_file}'. Skipping.")
                continue

            # Security check
            validate_file_security(file_data, str(settings_file))

            for section_name, section_data in file_data.items():
                if not isinstance(section_data, dict):
                    logger.warning(f"Section '{section_name}' in '{settings_file}' is not a table. Skipping.")
                    continue
                accumulated.setdefault(section_name, {})
                for field, field_value in section_data.items():
                    accumulated[section_name][field] = field_value

        except Exception:
            if not silent:
                raise
            logger.exception(f"Exception loading settings file: {settings_file}. Skipping.")

    for section, values in accumulated.items():
        if key is None or key.upper() == section.upper():
            obj.set(section, values)


# ---------------------------------------------------------------------------
# Register the fake module before any mergemate imports trigger Dynaconf
# ---------------------------------------------------------------------------

if "mergemate.custom_merge_loader" not in sys.modules:
    _fake = types.ModuleType("mergemate.custom_merge_loader")
    _fake.load = load
    _fake.validate_file_security = validate_file_security
    sys.modules["mergemate.custom_merge_loader"] = _fake
