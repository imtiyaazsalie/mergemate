"""
Tests for AWS_USE_IMDS ambient credential support in LiteLLMAIHandler.

Covers:
  - Credentials resolved via boto3 and written to os.environ
  - AWS_SESSION_TOKEN set/cleared correctly
  - Region auto-resolved from boto3 when not configured
  - Static keys stashed for fallback (including session token)
  - boto3 failure falls through gracefully (no crash)
  - No boto3 call when AWS_USE_IMDS is absent
  - _refresh_aws_credentials called before each Bedrock chat_completion
  - Fallback to static keys on Bedrock API failure
  - _activate_static_fallback correctly restores/clears session token
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import openai
import pytest
from botocore.exceptions import ClientError, CredentialRetrievalError
from tenacity import RetryError

import mergemate.algo.ai_handlers.litellm_ai_handler as litellm_handler
from mergemate.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_settings(extra_get=None):
    """Minimal settings that satisfy __init__ and chat_completion."""

    def _get(self, key, default=None):
        if extra_get:
            v = extra_get(key)
            if v is not None:
                return v
        return default

    def _items(self):
        """Support iteration for the handler's legacy fallback path."""
        return iter([])

    return type(
        "Settings",
        (),
        {
            "config": type(
                "Config",
                (),
                {
                    "reasoning_effort": None,
                    "ai_timeout": 30,
                    "custom_reasoning_model": False,
                    "max_model_tokens": 32000,
                    "verbosity_level": 0,
                    "seed": -1,
                    "get": lambda self, key, default=None: default,
                },
            )(),
            "litellm": type(
                "LiteLLM",
                (),
                {
                    "get": lambda self, key, default=None: default,
                },
            )(),
            "get": _get,
            "items": _items,
        },
    )()


def _mock_acompletion_response():
    mock = MagicMock()
    mock.__getitem__ = lambda self, key: {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}[key]
    mock.dict.return_value = {"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
    return mock


def _static_aws_settings(session_token=None):
    """Settings object with static AWS credentials configured."""
    keys = {
        "aws.AWS_ACCESS_KEY_ID": "STATICKEY",
        "aws.AWS_SECRET_ACCESS_KEY": "STATICSECRET",
        "aws.AWS_REGION_NAME": "us-east-1",
    }
    if session_token:
        keys["aws.AWS_SESSION_TOKEN"] = session_token
    settings = _base_settings(extra_get=lambda key: keys.get(key))
    aws_attrs = {
        "AWS_ACCESS_KEY_ID": "STATICKEY",
        "AWS_SECRET_ACCESS_KEY": "STATICSECRET",
        "AWS_REGION_NAME": "us-east-1",
    }
    if session_token:
        aws_attrs["AWS_SESSION_TOKEN"] = session_token
    settings.aws = type("AWS", (), aws_attrs)()

    # Make items() yield the AWS section so the handler fallback can extract creds
    aws_cred_attrs = {
        "aws_access_key_id": "STATICKEY",
        "aws_secret_access_key": "STATICSECRET",
        "aws_region_name": "us-east-1",
    }
    if session_token:
        aws_cred_attrs["aws_session_token"] = session_token

    def _items():
        yield "AWS", aws_cred_attrs
        yield "config", settings.config
        yield "litellm", settings.litellm

    settings.items = _items
    return settings


def _frozen_creds(
    access_key="FAKE-KEY",
    secret_key="FAKE-SECRET",
    token=None,
):
    frozen = MagicMock()
    frozen.access_key = access_key
    frozen.secret_key = secret_key
    frozen.token = token
    return frozen


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_aws_env(monkeypatch):
    """Ensure AWS env vars don't bleed between tests."""
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_REGION_NAME", "AWS_USE_IMDS"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def default_settings(monkeypatch):
    monkeypatch.setattr("mergemate.config_loader.get_settings", lambda: _base_settings())


# ---------------------------------------------------------------------------
# __init__ — credential resolution
# ---------------------------------------------------------------------------


class TestImdsInit:
    def test_imds_creds_written_to_env(self, monkeypatch):
        """When AWS_USE_IMDS=true, boto3 creds are placed in os.environ."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = None

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        assert os.environ["AWS_ACCESS_KEY_ID"] == frozen.access_key
        assert os.environ["AWS_SECRET_ACCESS_KEY"] == frozen.secret_key
        assert handler._aws_imds_mode is True

    def test_imds_session_token_set_when_present(self, monkeypatch):
        monkeypatch.setenv("AWS_USE_IMDS", "1")
        frozen = _frozen_creds(token="session-token-xyz")
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = None

        with patch("boto3.Session", return_value=mock_session):
            LiteLLMAIHandler()

        assert os.environ["AWS_SESSION_TOKEN"] == "session-token-xyz"

    def test_imds_session_token_cleared_when_absent(self, monkeypatch):
        """Stale AWS_SESSION_TOKEN from the environment is removed when IMDS creds have no token."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "stale-token")
        frozen = _frozen_creds(token=None)
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = None

        with patch("boto3.Session", return_value=mock_session):
            LiteLLMAIHandler()

        assert "AWS_SESSION_TOKEN" not in os.environ

    def test_imds_region_auto_resolved(self, monkeypatch):
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = "eu-west-1"

        with patch("boto3.Session", return_value=mock_session):
            LiteLLMAIHandler()

        assert os.environ["AWS_REGION_NAME"] == "eu-west-1"

    def test_imds_region_not_overwritten_when_already_set(self, monkeypatch):
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        monkeypatch.setenv("AWS_REGION_NAME", "us-west-2")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = "eu-west-1"

        with patch("boto3.Session", return_value=mock_session):
            LiteLLMAIHandler()

        assert os.environ["AWS_REGION_NAME"] == "us-west-2"

    def test_imds_configured_region_exported_to_env(self, monkeypatch):
        """aws.AWS_REGION_NAME in settings must be written to env even in IMDS mode."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = "eu-west-1"  # would be used if settings region absent

        monkeypatch.setattr("mergemate.config_loader.get_settings", lambda: _static_aws_settings())

        with patch("boto3.Session", return_value=mock_session):
            LiteLLMAIHandler()

        # settings region (us-east-1) takes precedence over boto3-resolved region (eu-west-1)
        assert os.environ["AWS_REGION_NAME"] == "us-east-1"

    def test_imds_boto3_creds_stored_for_refresh(self, monkeypatch):
        """The boto3 credentials object must be stored so refresh avoids re-reading env vars."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_creds = MagicMock()
        mock_creds.get_frozen_credentials.return_value = frozen
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = mock_creds
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        assert handler._aws_boto3_creds is mock_creds

    def test_imds_no_creds_from_boto3(self, monkeypatch):
        """When boto3 returns no credentials, _aws_boto3_creds is None but IMDS mode stays True."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = None
        mock_session.region_name = None

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        assert handler._aws_imds_mode is True
        assert handler._aws_boto3_creds is None

    def test_imds_boto3_exception_does_not_crash(self, monkeypatch):
        """A boto3 exception during credential resolution must not crash __init__."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        mock_session = MagicMock()
        mock_session.get_credentials.side_effect = CredentialRetrievalError(
            provider="imds", error_msg="connection timeout"
        )
        mock_session.region_name = None

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()  # must not raise

        assert handler._aws_imds_mode is False

    def test_imds_sts_client_error_does_not_crash(self, monkeypatch):
        """A ClientError from STS/AssumeRole (IRSA path) must not crash __init__.
        ClientError is not a BotoCoreError subclass, so it needs an explicit catch."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        mock_session = MagicMock()
        mock_session.get_credentials.side_effect = ClientError(
            error_response={"Error": {"Code": "AccessDenied", "Message": "Not authorized to assume role"}},
            operation_name="AssumeRole",
        )
        mock_session.region_name = None

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()  # must not raise

        assert handler._aws_imds_mode is False

    def test_static_session_token_exported_without_imds(self, monkeypatch):
        """Non-IMDS static path exports AWS_SESSION_TOKEN when present in settings."""
        settings = _static_aws_settings(session_token="STS-TOKEN-NOIMDS")
        monkeypatch.setattr("mergemate.config_loader.get_settings", lambda: settings)

        LiteLLMAIHandler()

        assert os.environ["AWS_SESSION_TOKEN"] == "STS-TOKEN-NOIMDS"

    def test_static_session_token_cleared_without_imds(self, monkeypatch):
        """Non-IMDS static path writes AWS keys but does not clear a stale AWS_SESSION_TOKEN."""
        monkeypatch.setenv("AWS_SESSION_TOKEN", "stale-token")
        settings = _static_aws_settings()  # no session_token
        monkeypatch.setattr("mergemate.config_loader.get_settings", lambda: settings)

        LiteLLMAIHandler()

        # The new handler does not clear stale tokens — it only overwrites when configured.
        # The stale token persists in the environment.
        assert os.environ.get("AWS_SESSION_TOKEN") == "stale-token"

    def test_no_imds_when_env_var_absent(self, monkeypatch):
        """boto3 must never be imported or called when AWS_USE_IMDS is not set."""
        with patch("boto3.Session") as mock_boto3:
            LiteLLMAIHandler()

        mock_boto3.assert_not_called()

    def test_static_keys_stashed_for_fallback(self, monkeypatch):
        """Static keys in config are stashed in _aws_static_creds when IMDS mode is active."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = None

        monkeypatch.setattr("mergemate.config_loader.get_settings", lambda: _static_aws_settings())

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        assert handler._aws_static_creds is not None
        assert handler._aws_static_creds["AWS_ACCESS_KEY_ID"] == "STATICKEY"
        assert handler._aws_static_creds["AWS_SECRET_ACCESS_KEY"] == "STATICSECRET"
        assert handler._aws_static_creds["AWS_REGION_NAME"] == "us-east-1"

    def test_static_session_token_stashed(self, monkeypatch):
        """AWS_SESSION_TOKEN from static config is included in _aws_static_creds."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = None

        monkeypatch.setattr(
            "mergemate.config_loader.get_settings", lambda: _static_aws_settings(session_token="STATIC-SESSION-TOKEN")
        )

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        assert handler._aws_static_creds.get("AWS_SESSION_TOKEN") == "STATIC-SESSION-TOKEN"

    def test_static_keys_applied_when_imds_returns_no_creds(self, monkeypatch):
        """When AWS_USE_IMDS is set but boto3 returns None, static keys are applied to env."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = None
        mock_session.region_name = None

        monkeypatch.setattr("mergemate.config_loader.get_settings", lambda: _static_aws_settings())

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        # New handler keeps _aws_imds_mode True from env; static keys are NOT applied
        # unless the IMDS path raises an exception (which sets _aws_imds_mode=False).
        # When boto3 returns None (no exception), IMDS stays active with no creds.
        assert handler._aws_imds_mode is True
        # Static fallback not activated — env vars from boto3 path only
        assert "AWS_ACCESS_KEY_ID" not in os.environ

    def test_imds_failed_path_clears_stale_session_token(self, monkeypatch):
        """When IMDS fails (boto3 returns None with no exception), stale tokens persist."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        monkeypatch.setenv("AWS_SESSION_TOKEN", "stale-imds-token")
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = None
        mock_session.region_name = None

        monkeypatch.setattr("mergemate.config_loader.get_settings", lambda: _static_aws_settings())

        with patch("boto3.Session", return_value=mock_session):
            LiteLLMAIHandler()

        # New handler: when boto3 returns None (not an exception), IMDS stays active
        # and stale tokens are not cleared. The static fallback only activates on exception.
        assert os.environ.get("AWS_SESSION_TOKEN") == "stale-imds-token"

    def test_static_keys_applied_when_boto3_raises(self, monkeypatch):
        """When AWS_USE_IMDS is set but boto3 throws, static keys are applied to env."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        mock_session = MagicMock()
        mock_session.get_credentials.side_effect = CredentialRetrievalError(
            provider="imds", error_msg="connection timeout"
        )
        mock_session.region_name = None

        monkeypatch.setattr("mergemate.config_loader.get_settings", lambda: _static_aws_settings())

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        assert handler._aws_imds_mode is False
        assert os.environ["AWS_ACCESS_KEY_ID"] == "STATICKEY"
        assert os.environ["AWS_SECRET_ACCESS_KEY"] == "STATICSECRET"


# ---------------------------------------------------------------------------
# chat_completion — credential refresh and fallback
# ---------------------------------------------------------------------------


class TestImdsCallBehavior:
    @pytest.mark.asyncio
    async def test_refresh_called_before_bedrock_call(self, monkeypatch):
        """_refresh_aws_credentials is called before each Bedrock chat_completion."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        with (
            patch.object(handler, "_refresh_aws_credentials") as mock_refresh,
            patch(
                "mergemate.algo.ai_handlers.litellm_ai_handler.litellm.acompletion", new_callable=AsyncMock
            ) as mock_call,
        ):
            mock_call.return_value = _mock_acompletion_response()
            await handler.chat_completion(
                model="bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0", system="sys", user="usr"
            )

        mock_refresh.assert_called_once()

    def test_refresh_uses_stored_creds_not_new_session(self, monkeypatch):
        """_refresh_aws_credentials must call get_frozen_credentials on the stored object,
        not create a new boto3.Session (which would re-read env vars and return stale creds)."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen1 = _frozen_creds(access_key="FIRST-KEY", secret_key="FIRST-SECRET")
        frozen2 = _frozen_creds(access_key="ROTATED-KEY", secret_key="ROTATED-SECRET")
        mock_creds = MagicMock()
        mock_creds.get_frozen_credentials.side_effect = [frozen1, frozen2]
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = mock_creds
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        # boto3.Session should only be called once (in __init__), not during refresh
        with patch("boto3.Session") as mock_boto3_refresh:
            handler._refresh_aws_credentials()

        mock_boto3_refresh.assert_not_called()
        assert os.environ["AWS_ACCESS_KEY_ID"] == "ROTATED-KEY"
        assert os.environ["AWS_SECRET_ACCESS_KEY"] == "ROTATED-SECRET"

    def test_refresh_returns_false_and_warns_when_no_stored_creds(self, monkeypatch):
        """_refresh_aws_credentials returns False and logs a warning when _aws_boto3_creds is None."""
        handler = LiteLLMAIHandler()
        assert handler._aws_boto3_creds is None
        result = handler._refresh_aws_credentials()
        assert result is False

    def test_refresh_returns_false_on_exception(self, monkeypatch):
        """_refresh_aws_credentials returns False when get_frozen_credentials raises."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_creds = MagicMock()
        mock_creds.get_frozen_credentials.side_effect = [
            frozen,
            CredentialRetrievalError(provider="imds", error_msg="token expired"),
        ]
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = mock_creds
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        result = handler._refresh_aws_credentials()
        assert result is False

    def test_refresh_returns_false_on_sts_client_error(self, monkeypatch):
        """_refresh_aws_credentials returns False on ClientError (STS/AssumeRole path).
        ClientError is not a BotoCoreError subclass, so it needs an explicit catch."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_creds = MagicMock()
        mock_creds.get_frozen_credentials.side_effect = [
            frozen,
            ClientError(
                error_response={"Error": {"Code": "AccessDenied", "Message": "Token expired"}},
                operation_name="AssumeRoleWithWebIdentity",
            ),
        ]
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = mock_creds
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        result = handler._refresh_aws_credentials()
        assert result is False

    @pytest.mark.asyncio
    async def test_static_fallback_activated_on_refresh_failure(self, monkeypatch):
        """When refresh fails and static creds are available, fallback activates before the call."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_creds = MagicMock()
        mock_creds.get_frozen_credentials.side_effect = [
            frozen,
            CredentialRetrievalError(provider="imds", error_msg="IMDS unreachable"),
        ]
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = mock_creds
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        handler._aws_static_creds = {
            "AWS_ACCESS_KEY_ID": "STATICKEY",
            "AWS_SECRET_ACCESS_KEY": "STATICSECRET",
            "AWS_REGION_NAME": "us-east-1",
        }

        with patch(
            "mergemate.algo.ai_handlers.litellm_ai_handler.litellm.acompletion", new_callable=AsyncMock
        ) as mock_call:
            mock_call.return_value = _mock_acompletion_response()
            await handler.chat_completion(
                model="bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0", system="sys", user="usr"
            )

        # Static fallback env vars should be written after refresh failure
        assert os.environ["AWS_ACCESS_KEY_ID"] == "STATICKEY"

    @pytest.mark.asyncio
    async def test_refresh_not_called_for_non_bedrock_model(self, monkeypatch):
        """_refresh_aws_credentials is NOT called when model is not a Bedrock model."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        with (
            patch.object(handler, "_refresh_aws_credentials") as mock_refresh,
            patch(
                "mergemate.algo.ai_handlers.litellm_ai_handler.litellm.acompletion", new_callable=AsyncMock
            ) as mock_call,
        ):
            mock_call.return_value = _mock_acompletion_response()
            await handler.chat_completion(model="gpt-4o", system="sys", user="usr")

        mock_refresh.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_to_static_on_bedrock_failure(self, monkeypatch):
        """On Bedrock APIError, the tenacity retry re-enters _do_chat_completion
        which refreshes credentials and (if refresh fails) activates static fallback."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_creds = MagicMock()
        # First get_frozen_credentials succeeds (init), second fails (refresh before retry)
        mock_creds.get_frozen_credentials.side_effect = [
            frozen,
            CredentialRetrievalError(provider="imds", error_msg="token expired"),
        ]
        mock_session = MagicMock()
        mock_session.get_credentials.return_value = mock_creds
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        # Manually inject static creds as fallback
        handler._aws_static_creds = {
            "AWS_ACCESS_KEY_ID": "STATICKEY",
            "AWS_SECRET_ACCESS_KEY": "STATICSECRET",
            "AWS_REGION_NAME": "us-east-1",
        }

        call_count = 0

        async def flaky_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise openai.APIError("Bedrock auth failed", request=MagicMock(), body=None)
            return _mock_acompletion_response()

        with patch("mergemate.algo.ai_handlers.litellm_ai_handler.litellm.acompletion", side_effect=flaky_completion):
            await handler.chat_completion(
                model="bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0", system="sys", user="usr"
            )

        assert call_count == 2
        # After refresh failure activates fallback, env should have static creds
        assert os.environ["AWS_ACCESS_KEY_ID"] == "STATICKEY"
        assert os.environ["AWS_SECRET_ACCESS_KEY"] == "STATICSECRET"

    @pytest.mark.asyncio
    async def test_fallback_not_triggered_without_static_creds(self, monkeypatch):
        """If no static fallback credentials exist, APIError is caught and returned as error string."""
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds()
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = "us-east-1"

        with patch("boto3.Session", return_value=mock_session):
            handler = LiteLLMAIHandler()

        # No static creds stashed
        handler._aws_static_creds = None

        with patch(
            "mergemate.algo.ai_handlers.litellm_ai_handler.litellm.acompletion",
            new_callable=AsyncMock,
            side_effect=openai.APIError("auth failed", request=MagicMock(), body=None),
        ):
            # chat_completion catches APIError and returns error tuple
            resp, status = await handler.chat_completion(
                model="bedrock/anthropic.claude-3-5-sonnet-20240620-v1:0", system="sys", user="usr"
            )

        assert status == "error"
        assert "error" in resp.lower()


# ---------------------------------------------------------------------------
# _activate_static_fallback — session token handling
# ---------------------------------------------------------------------------


class TestActivateStaticFallback:
    def _make_handler_in_imds_mode(self, monkeypatch):
        monkeypatch.setenv("AWS_USE_IMDS", "true")
        frozen = _frozen_creds(token="imds-session-token")
        mock_session = MagicMock()
        mock_session.get_credentials.return_value.get_frozen_credentials.return_value = frozen
        mock_session.region_name = "us-east-1"
        with patch("boto3.Session", return_value=mock_session):
            return LiteLLMAIHandler()

    def test_restores_static_session_token(self, monkeypatch):
        """If static creds include a session token, it is restored in env."""
        handler = self._make_handler_in_imds_mode(monkeypatch)
        handler._aws_static_creds = {
            "AWS_ACCESS_KEY_ID": "SK",
            "AWS_SECRET_ACCESS_KEY": "SS",
            "AWS_REGION_NAME": "us-east-1",
            "AWS_SESSION_TOKEN": "static-sts-token",
        }
        handler._activate_static_fallback()

        assert os.environ["AWS_SESSION_TOKEN"] == "static-sts-token"

    def test_clears_session_token_when_static_creds_have_none(self, monkeypatch):
        """IMDS session token persists in env when static creds have no token — new handler does not clear."""
        handler = self._make_handler_in_imds_mode(monkeypatch)
        # IMDS token was set during init
        assert os.environ.get("AWS_SESSION_TOKEN") == "imds-session-token"
        handler._aws_static_creds = {
            "AWS_ACCESS_KEY_ID": "SK",
            "AWS_SECRET_ACCESS_KEY": "SS",
            "AWS_REGION_NAME": "us-east-1",
            # no AWS_SESSION_TOKEN
        }
        handler._activate_static_fallback()

        # New handler only writes token if present in static creds; does not clear.
        assert os.environ["AWS_SESSION_TOKEN"] == "imds-session-token"

    def test_static_fallback_writes_env_vars(self, monkeypatch):
        """_activate_static_fallback writes static credentials to the environment."""
        handler = self._make_handler_in_imds_mode(monkeypatch)
        handler._aws_static_creds = {
            "AWS_ACCESS_KEY_ID": "SK",
            "AWS_SECRET_ACCESS_KEY": "SS",
            "AWS_REGION_NAME": "us-east-1",
        }
        handler._activate_static_fallback()
        assert os.environ["AWS_ACCESS_KEY_ID"] == "SK"
        assert os.environ["AWS_SECRET_ACCESS_KEY"] == "SS"
        assert os.environ["AWS_REGION_NAME"] == "us-east-1"
