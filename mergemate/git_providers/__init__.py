"""Git provider registry — lazy-loaded at runtime with graceful degradation."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

from starlette_context import context

from mergemate.config_loader import get_settings
from mergemate.git_providers.git_provider import GitProvider

# ---------------------------------------------------------------------------
# Eager imports with graceful fallback for optional providers
# ---------------------------------------------------------------------------

try:
    from mergemate.git_providers.github_provider import GithubProvider
except ImportError:
    GithubProvider = None

try:
    from mergemate.git_providers.gitlab_provider import GitLabProvider
except ImportError:
    GitLabProvider = None

try:
    from mergemate.git_providers.bitbucket_provider import BitbucketProvider
except ImportError:
    BitbucketProvider = None

try:
    from mergemate.git_providers.bitbucket_server_provider import BitbucketServerProvider
except ImportError:
    BitbucketServerProvider = None

try:
    from mergemate.git_providers.azuredevops_provider import AzureDevopsProvider
except ImportError:
    AzureDevopsProvider = None

try:
    from mergemate.git_providers.codecommit_provider import CodeCommitProvider
except ImportError:
    CodeCommitProvider = None

try:
    from mergemate.git_providers.local_git_provider import LocalGitProvider
except ImportError:
    LocalGitProvider = None

try:
    from mergemate.git_providers.gerrit_provider import GerritProvider
except ImportError:
    GerritProvider = None

try:
    from mergemate.git_providers.gitea_provider import GiteaProvider
except ImportError:
    GiteaProvider = None

# Map provider IDs to lazy factory functions
_PROVIDER_FACTORIES: dict[str, Callable[[], type]] = {
    "github": lambda: GithubProvider or _import_provider("github_provider", "GithubProvider"),
    "gitlab": lambda: GitLabProvider or _import_provider("gitlab_provider", "GitLabProvider"),
    "bitbucket": lambda: BitbucketProvider or _import_provider("bitbucket_provider", "BitbucketProvider"),
    "bitbucket_server": lambda: (
        BitbucketServerProvider or _import_provider("bitbucket_server_provider", "BitbucketServerProvider")
    ),
    "azure": lambda: AzureDevopsProvider or _import_provider("azuredevops_provider", "AzureDevopsProvider"),
    "codecommit": lambda: CodeCommitProvider or _import_provider("codecommit_provider", "CodeCommitProvider"),
    "local": lambda: LocalGitProvider or _import_provider("local_git_provider", "LocalGitProvider"),
    "gerrit": lambda: GerritProvider or _import_provider("gerrit_provider", "GerritProvider"),
    "gitea": lambda: GiteaProvider or _import_provider("gitea_provider", "GiteaProvider"),
}

# Backwards compatibility — tests and some tools access this directly
_GIT_PROVIDERS = _PROVIDER_FACTORIES


def _import_provider(module_name: str, class_name: str) -> type:
    """Lazy-import a git provider class."""
    import importlib

    mod = importlib.import_module(f"mergemate.git_providers.{module_name}")
    return getattr(mod, class_name)


def get_git_provider() -> type:
    """Get the git provider class for the configured provider."""
    try:
        provider_id = get_settings().config.git_provider
    except AttributeError as e:
        raise ValueError("git_provider is a required attribute in the configuration file") from e
    if provider_id not in _PROVIDER_FACTORIES:
        raise ValueError(f"Unknown git provider: {provider_id}")
    return _PROVIDER_FACTORIES[provider_id]()


def get_git_provider_with_context(pr_url: str) -> GitProvider:
    """Get or create a GitProvider instance for the given PR URL."""
    is_context_env = None
    try:
        is_context_env = context.get("settings", None)
    except Exception:
        pass

    if is_context_env and context.get("git_provider", {}).get(pr_url):
        return context["git_provider"][pr_url]

    try:
        provider_id = get_settings().config.git_provider
        if provider_id not in _PROVIDER_FACTORIES:
            raise ValueError(f"Unknown git provider: {provider_id}")
        git_provider = _PROVIDER_FACTORIES[provider_id]()(pr_url)
        if is_context_env:
            context["git_provider"] = {pr_url: git_provider}
        return git_provider
    except Exception as e:
        raise ValueError(f"Failed to get git provider for {pr_url}") from e
