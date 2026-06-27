"""Idempotent registration of DiffInputProvider into mergemate's provider registry.

Importing this module inserts the "mosaico_diff" provider via setdefault (never
clobbers existing keys). Only the MOSAICO server imports it, so the registry is
untouched on every other code path."""
from mergemate.git_providers import _GIT_PROVIDERS
from mergemate.mosaico.diff_provider import DiffInputProvider

_GIT_PROVIDERS.setdefault("mosaico_diff", DiffInputProvider)
