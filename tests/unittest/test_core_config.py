"""Tests for mergemate.core.config — AppConfig and associated dataclasses."""

from __future__ import annotations

from pathlib import Path

import pytest

from mergemate.core.config import AppConfig, GitConfig, ModelConfig, ReviewConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def default_config() -> AppConfig:
    """Return a fresh AppConfig with all defaults."""
    return AppConfig()


@pytest.fixture
def sample_raw() -> dict:
    """Minimal raw dict that exercises the key config branches."""
    return {
        "configuration": {
            "model_provider": "azure",
            "model": "gpt-4o-mini",
            "temperature": 0.1,
            "max_model_tokens": 2048,
            "fallback_models": ["gpt-4"],
            "custom_model_max_tokens": 1024,
            "git_provider": "gitlab",
            "git_base_url": "https://gitlab.example.com",
            "deployment_type": "app",
            "ratelimit_retries": 3,
            "verbosity_level": 2,
            "publish_output": False,
            "cli_mode": True,
            "response_language": "fr-fr",
            "ai_timeout": 60,
        },
        "pr_reviewer": {
            "num_max_findings": 5,
            "extra_instructions": "Be strict",
            "require_score_review": True,
            "enable_review_labels_effort": False,
            "persistent_comment": False,
            "inline_code_comments": True,
        },
        ".secrets": {
            "openai": {"key": "sk-test-123"},
            "github": {"app_id": "42", "private_key": "---BEGIN---"},
        },
    }


@pytest.fixture
def minimal_settings_dir(tmp_path: Path) -> Path:
    """Create a temporary settings directory with TOML files."""
    settings_dir = tmp_path / "settings"
    settings_dir.mkdir()

    # _from_raw expects raw['configuration'] as a flat dict (no [config] wrapper).
    (settings_dir / "configuration.toml").write_text(
        'model = "gpt-5.5"\n'
        'git_provider = "gitlab"\n'
        "publish_output = false\n"
        "verbosity_level = 1\n"
        "cli_mode = true\n"
        "temperature = 0.5\n"
        "max_model_tokens = 8000\n"
        'fallback_models = ["gpt-5.4-mini"]\n'
        "ai_timeout = 90\n"
        'response_language = "en-us"\n'
    )

    # _from_raw reads raw['pr_reviewer'] as a flat dict (no [pr_reviewer] wrapper).
    (settings_dir / "pr_reviewer.toml").write_text(
        "num_max_findings = 7\n"
        'extra_instructions = "Focus on security"\n'
        "require_score_review = true\n"
        "enable_review_labels_effort = false\n"
        "persistent_comment = true\n"
        "inline_code_comments = false\n"
    )

    # Secrets file
    (settings_dir / ".secrets.toml").write_text('[openai]\nkey = "sk-test-secret"\n\n[github]\napp_id = "123456"\n')

    # Subdirectory with TOML
    sub = settings_dir / "code_suggestions"
    sub.mkdir()
    (sub / "pr_code_suggestions.toml").write_text(
        'commitable_code_suggestions = false\nextra_instructions = "Be thorough"\n'
    )

    return settings_dir


# ---------------------------------------------------------------------------
# test_load_default
# ---------------------------------------------------------------------------


def test_load_default_loads_from_settings_dir():
    """load_default() should load from the bundled settings directory."""
    config = AppConfig.load_default()
    assert isinstance(config, AppConfig)
    assert isinstance(config.model, ModelConfig)
    assert isinstance(config.git, GitConfig)
    assert isinstance(config.review, ReviewConfig)
    # The bundled config should have a reasonable model set.
    assert config.model.model
    assert config.model.provider


# ---------------------------------------------------------------------------
# test_merge_repo_config
# ---------------------------------------------------------------------------


def test_merge_repo_config_overrides_existing_sections():
    """Repo TOML should merge into existing sections, overriding specific keys."""
    config = AppConfig()
    toml_content = "[pr_reviewer]\nnum_max_findings = 3\n"
    merged = config.merge_repo_config(toml_content)

    assert merged.review.num_max_findings == 3
    # Other review defaults should be preserved.
    assert merged.review.extra_instructions == ""


def test_merge_repo_config_adds_new_section():
    """New sections in repo TOML should be added to _raw."""
    config = AppConfig()
    toml_content = "[custom_tool]\nkey = 'value'\n"
    merged = config.merge_repo_config(toml_content)

    assert merged.get_tool_config("custom_tool") == {"key": "value"}


def test_merge_repo_config_handles_invalid_toml():
    """Invalid TOML should return the same config instance unchanged."""
    config = AppConfig()
    merged = config.merge_repo_config("not valid {{{ toml")
    assert merged is config  # returns self on parse failure
    assert merged.verbosity_level == config.verbosity_level
    assert merged.model.model == config.model.model


def test_merge_repo_config_merges_nested_sections():
    """Deep override: only specified keys change; everything else stays."""
    config = AppConfig._from_raw(
        {
            "configuration": {
                "model": "gpt-4o",
                "verbosity_level": 0,
                "publish_output": True,
            },
            "pr_reviewer": {"num_max_findings": 10},
        }
    )

    toml = "[pr_reviewer]\nnum_max_findings = 5\n"
    merged = config.merge_repo_config(toml)

    assert merged.review.num_max_findings == 5
    assert merged.verbosity_level == 0  # unchanged
    assert merged.publish_output is True  # unchanged


# ---------------------------------------------------------------------------
# test_with_overrides
# ---------------------------------------------------------------------------


def test_with_overrides_model():
    """'model' key should override model.model."""
    config = AppConfig().with_overrides(model="gpt-5")
    assert config.model.model == "gpt-5"


def test_with_overrides_model_provider():
    """'model_provider' key should override model.provider."""
    config = AppConfig().with_overrides(model_provider="azure")
    assert config.model.provider == "azure"


def test_with_overrides_temperature():
    """'temperature' key should override model.temperature."""
    config = AppConfig().with_overrides(temperature="0.9")
    assert config.model.temperature == 0.9


def test_with_overrides_git_provider():
    """'git_provider' key should override git.provider."""
    config = AppConfig().with_overrides(git_provider="gitlab")
    assert config.git.provider == "gitlab"


def test_with_overrides_boolean_flags():
    """Boolean flags are cast with bool() — non-empty strings are truthy."""
    c1 = AppConfig().with_overrides(publish_output="false")
    assert c1.publish_output is True  # bool("false") == True (non-empty string)

    c2 = AppConfig().with_overrides(cli_mode="true")
    assert c2.cli_mode is True

    c3 = AppConfig().with_overrides(publish_output="")
    assert c3.publish_output is False  # bool("") == False


def test_with_overrides_verbosity():
    """verbosity_level override should be cast to int."""
    config = AppConfig().with_overrides(verbosity_level="2")
    assert config.verbosity_level == 2


def test_with_overrides_preserves_other_values():
    """Calling with_overrides should not mutate unrelated fields."""
    original = AppConfig()
    overridden = original.with_overrides(model="gpt-5")

    assert overridden.publish_output == original.publish_output
    assert overridden.response_language == original.response_language
    assert overridden.git.provider == original.git.provider


def test_with_overrides_ignores_unknown_keys():
    """Unknown override keys should be silently ignored."""
    config = AppConfig().with_overrides(foo="bar", baz="qux")
    assert isinstance(config, AppConfig)


# ---------------------------------------------------------------------------
# test_get_tool_config
# ---------------------------------------------------------------------------


def test_get_tool_config_returns_empty_for_unknown_tool():
    """Unknown tools return empty dict."""
    config = AppConfig()
    assert config.get_tool_config("nonexistent") == {}


def test_get_tool_config_returns_raw_section(sample_raw):
    """Known sections should return their raw dict."""
    config = AppConfig._from_raw(sample_raw)
    cfg = config.get_tool_config("pr_reviewer")
    assert cfg["num_max_findings"] == 5
    assert cfg["extra_instructions"] == "Be strict"


# ---------------------------------------------------------------------------
# test_get_secret
# ---------------------------------------------------------------------------


def test_get_secret_returns_none_when_no_secrets():
    """Without .secrets loaded, all lookups return None."""
    config = AppConfig()
    assert config.get_secret("openai.key") is None


def test_get_secret_returns_none_for_missing_key(sample_raw):
    """Missing keys return None."""
    config = AppConfig._from_raw(sample_raw)
    assert config.get_secret("openai.nonexistent") is None


def test_get_secret_returns_value(sample_raw):
    """Valid dot-notation path returns the secret."""
    config = AppConfig._from_raw(sample_raw)
    assert config.get_secret("openai.key") == "sk-test-123"
    assert config.get_secret("github.app_id") == "42"


def test_get_secret_handles_partial_path(sample_raw):
    """A path that goes through a non-dict value returns None."""
    config = AppConfig._from_raw(sample_raw)
    # "openai.key" is a string, so "openai.key.extra" should fail.
    assert config.get_secret("openai.key.extra") is None


# ---------------------------------------------------------------------------
# test_from_settings_dir
# ---------------------------------------------------------------------------


def test_from_settings_dir_loads_configuration(minimal_settings_dir):
    """Settings directory TOML should populate AppConfig fields.

    _from_raw expects raw['configuration'] (or raw['config']) as a flat dict
    of config keys — no [config] wrapper section.
    """
    config = AppConfig.from_settings_dir(minimal_settings_dir)

    assert config.model.model == "gpt-5.5"
    assert config.model.temperature == 0.5
    assert config.model.max_tokens == 8000
    assert config.model.fallback_models == ["gpt-5.4-mini"]
    assert config.git.provider == "gitlab"
    assert config.verbosity_level == 1
    assert config.publish_output is False
    assert config.cli_mode is True
    assert config.ai_timeout == 90


def test_from_settings_dir_loads_pr_reviewer(minimal_settings_dir):
    """pr_reviewer.toml should populate ReviewConfig.

    _from_raw reads raw['pr_reviewer'] directly as a flat dict (no section wrapper).
    """
    config = AppConfig.from_settings_dir(minimal_settings_dir)
    assert config.review.num_max_findings == 7
    assert config.review.extra_instructions == "Focus on security"
    assert config.review.require_score_review is True
    assert config.review.enable_review_labels_effort is False


def test_from_settings_dir_loads_subdirectory(minimal_settings_dir):
    """TOML files in subdirectories should also be loaded into _raw."""
    config = AppConfig.from_settings_dir(minimal_settings_dir)
    cfg = config.get_tool_config("pr_code_suggestions")
    assert cfg["commitable_code_suggestions"] is False
    assert cfg["extra_instructions"] == "Be thorough"


def test_from_settings_dir_loads_secrets(minimal_settings_dir):
    """Secrets file should be loaded into _raw['.secrets']."""
    config = AppConfig.from_settings_dir(minimal_settings_dir)
    assert config.get_secret("openai.key") == "sk-test-secret"
    assert config.get_secret("github.app_id") == "123456"


def test_from_settings_dir_defaults_when_no_toml_files(tmp_path):
    """Empty settings directory should produce a default-filled AppConfig."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    config = AppConfig.from_settings_dir(empty_dir)

    assert config.model.model == "gpt-4o"
    assert config.git.provider == "github"
    assert config.verbosity_level == 0


def test_from_settings_dir_handles_corrupt_toml(tmp_path):
    """Corrupt TOML files should be skipped gracefully."""
    settings_dir = tmp_path / "corrupt"
    settings_dir.mkdir()
    (settings_dir / "configuration.toml").write_text("{{{ invalid toml")

    config = AppConfig.from_settings_dir(settings_dir)
    assert config.model.model == "gpt-4o"  # default fallback


def test_from_settings_dir_handles_missing_secrets(tmp_path):
    """If .secrets.toml is absent, loading should still succeed."""
    settings_dir = tmp_path / "no_secrets"
    settings_dir.mkdir()
    (settings_dir / "configuration.toml").write_text('model = "test-model"\n')

    config = AppConfig.from_settings_dir(settings_dir)
    assert config.model.model == "test-model"
    assert config.get_secret("any.key") is None


def test_from_settings_dir_custom_secrets_path(tmp_path):
    """A separate secrets directory should be supported."""
    settings_dir = tmp_path / "settings"
    secrets_dir = tmp_path / "secrets"
    settings_dir.mkdir()
    secrets_dir.mkdir()

    (settings_dir / "configuration.toml").write_text('model = "custom"\n')
    (secrets_dir / ".secrets.toml").write_text('[api]\nkey = "custom-secret"\n')

    config = AppConfig.from_settings_dir(settings_dir, secrets_dir=secrets_dir)
    assert config.model.model == "custom"
    assert config.get_secret("api.key") == "custom-secret"


# ---------------------------------------------------------------------------
# get_prompts
# ---------------------------------------------------------------------------


def test_get_prompts_returns_empty_for_unknown_tool():
    """Unknown tools return empty prompt dict."""
    config = AppConfig()
    prompts = config.get_prompts("unknown")
    assert prompts == {"system": "", "user": ""}


def test_get_prompts_resolves_prefixed_tool_name():
    """When pr_{tool}_prompts section exists, it should be preferred."""
    raw = {
        "pr_review_prompts": {
            "system": "You are a reviewer",
            "user": "Review this PR",
        },
    }
    config = AppConfig._from_raw(raw)
    prompts = config.get_prompts("review")
    assert prompts["system"] == "You are a reviewer"
    assert prompts["user"] == "Review this PR"


def test_get_prompts_falls_back_to_raw_tool():
    """If no prompts section exists, fall back to tool_name raw section."""
    raw = {
        "pr_reviewer": {
            "system": "Fallback system",
            "user": "Fallback user",
        },
    }
    config = AppConfig._from_raw(raw)
    # get_prompts looks for f"pr_{tool_name}_prompts" first, then tool_name directly.
    # With tool_name="pr_reviewer" it matches the raw key directly.
    prompts = config.get_prompts("pr_reviewer")
    assert prompts["system"] == "Fallback system"
    assert prompts["user"] == "Fallback user"
