"""
Tests for provider credential forwarding in LiteLLMAIHandler.

The rewritten handler stores credentials in a ProviderCredentials dataclass
and selects the right credentials per-model via to_litellm_kwargs().
No global state mutation on the litellm module.

Verifies:
  - No api_key forwarded when no credentials are configured.
  - Real provider keys ARE forwarded for the correct model prefixes.
  - Multiple providers coexist — the right key is used per model.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import litellm
import pytest

from mergemate.algo.ai_handlers.litellm_ai_handler import DUMMY_LITELLM_API_KEY, LiteLLMAIHandler, ProviderCredentials


def _make_creds(**kwargs):
    """Build a ProviderCredentials with the given fields set."""
    creds = ProviderCredentials()
    for k, v in kwargs.items():
        setattr(creds, k, v)
    return creds


def _mock_response():
    """Minimal litellm.acompletion response for non-streaming path."""
    choice = MagicMock()
    choice.message.content = "ok"
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    return response


def _assert_api_key(kwargs, expected_value):
    """Assert api_key is present and equals expected_value in litellm.acompletion kwargs."""
    actual = kwargs.get("api_key")
    assert actual == expected_value, (
        f"Expected api_key={expected_value!r} in acompletion kwargs, got {actual!r}. Full kwargs: {kwargs}"
    )


def _assert_no_api_key(kwargs):
    """Assert api_key is NOT present in litellm.acompletion kwargs."""
    assert "api_key" not in kwargs, (
        f"api_key should NOT be present in acompletion kwargs, "
        f"but got: {kwargs.get('api_key')!r}. Full kwargs: {kwargs}"
    )


class TestApiKeyGuard:
    # ── no-credential cases ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_dummy_key_not_forwarded(self):
        """No api_key forwarded when no credentials are configured (regardless of model)."""
        handler = LiteLLMAIHandler(credentials=ProviderCredentials())

        with patch.object(litellm, "acompletion", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _mock_response()
            await handler.chat_completion(model="gpt-4o", system="sys", user="usr")

        _assert_no_api_key(mock_call.call_args[1])

    @pytest.mark.asyncio
    async def test_none_api_key_not_forwarded(self):
        """No api_key forwarded when openai_key is explicitly None."""
        handler = LiteLLMAIHandler(credentials=_make_creds(openai_key=None))

        with patch.object(litellm, "acompletion", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _mock_response()
            await handler.chat_completion(model="gpt-4o", system="sys", user="usr")

        _assert_no_api_key(mock_call.call_args[1])

    # ── openai_key forwarding ─────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_real_key_forwarded(self):
        """OpenAI key is forwarded as api_key for default (OpenAI-compatible) models."""
        real_key = "test-provider-key-67890"
        handler = LiteLLMAIHandler(credentials=_make_creds(openai_key=real_key))

        with patch.object(litellm, "acompletion", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _mock_response()
            await handler.chat_completion(model="gpt-4o", system="sys", user="usr")

        _assert_api_key(mock_call.call_args[1], real_key)

    # ── anthropic (claude) ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_anthropic_key_not_shadowed_by_dummy_key(self):
        """Anthropic key is forwarded for Claude models, even without OpenAI configured.

        Original bug (GitHub #2042): when ANTHROPIC.KEY was set but OPENAI.KEY was not,
        the dummy placeholder key was forwarded instead of the real Anthropic key.
        The new handler selects credentials per-model, so the Anthropic key is used
        correctly for Claude/Anthropic model prefixes.
        """
        anthropic_key = "test-anthropic-key-12345"
        handler = LiteLLMAIHandler(credentials=_make_creds(anthropic_key=anthropic_key))

        with patch.object(litellm, "acompletion", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _mock_response()
            await handler.chat_completion(model="claude-3-5-sonnet-20241022", system="sys", user="usr")

        _assert_api_key(mock_call.call_args[1], anthropic_key)

    # ── groq ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_groq_key_forwarded_for_non_ollama_model(self):
        """Groq key is forwarded for groq/ prefixed models.

        Regression check for PR #2288: the old guard only forwarded api_key
        when model.startswith('ollama'), silently dropping Groq keys.
        The new handler selects credentials based on model prefix, so this
        is handled naturally.
        """
        groq_key = "test-groq-key-12345"
        handler = LiteLLMAIHandler(credentials=_make_creds(groq_key=groq_key))

        with patch.object(litellm, "acompletion", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _mock_response()
            await handler.chat_completion(model="groq/llama-3.1-70b", system="sys", user="usr")

        _assert_api_key(mock_call.call_args[1], groq_key)

    # ── xAI ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_xai_key_forwarded_for_non_ollama_model(self):
        """xAI key is forwarded for xai/ prefixed models.

        Same regression as Groq (PR #2288): the old guard's model-scoped
        approach would break xAI. The new per-model credential selection
        handles this correctly.
        """
        xai_key = "xai-test-key-67890"
        handler = LiteLLMAIHandler(credentials=_make_creds(xai_key=xai_key))

        with patch.object(litellm, "acompletion", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _mock_response()
            await handler.chat_completion(model="xai/grok-2-latest", system="sys", user="usr")

        _assert_api_key(mock_call.call_args[1], xai_key)

    # ── sambanova ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_sambanova_key_forwarded_for_non_ollama_model(self):
        """SambaNova key is forwarded for sambanova/ prefixed models."""
        sambanova_key = "sambanova-test-key-67890"
        handler = LiteLLMAIHandler(credentials=_make_creds(sambanova_key=sambanova_key))

        with patch.object(litellm, "acompletion", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _mock_response()
            await handler.chat_completion(model="sambanova/MiniMax-M3", system="sys", user="usr")

        _assert_api_key(mock_call.call_args[1], sambanova_key)

    # ── multiple providers coexisting ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_ollama_and_groq_coexist(self):
        """Multiple providers configured: the right key is used per model.

        When both Groq and Ollama are configured, each call gets the
        correct credential based on the model prefix.
        """
        groq_key = "gsk-groq-key"
        ollama_key = "ollama-key"

        handler = LiteLLMAIHandler(
            credentials=_make_creds(
                groq_key=groq_key,
                ollama_api_key=ollama_key,
                ollama_api_base="http://localhost:11434",
            )
        )

        with patch.object(litellm, "acompletion", new_callable=AsyncMock) as mock_call:
            mock_call.return_value = _mock_response()

            # Ollama model → Ollama key + api_base
            await handler.chat_completion(model="ollama/mistral", system="sys", user="usr")
            _assert_api_key(mock_call.call_args[1], ollama_key)
            assert mock_call.call_args[1].get("api_base") == "http://localhost:11434"

            # Groq model → Groq key
            await handler.chat_completion(model="groq/llama-3.1-70b", system="sys", user="usr")
            _assert_api_key(mock_call.call_args[1], groq_key)
            # api_base should NOT leak from Ollama
            assert "api_base" not in mock_call.call_args[1], (
                f"api_base should not be present for Groq call. Full kwargs: {mock_call.call_args[1]}"
            )
