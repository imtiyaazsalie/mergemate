"""LiteLLM AI handler — clean, no global state mutation.

Rewritten to store provider credentials in instance state and pass them
as kwargs to litellm.acompletion(), rather than mutating the litellm module globals.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from dataclasses import dataclass, field
from typing import Any, Optional

import litellm
import openai
import requests
from tenacity import retry, retry_if_exception_type, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from mergemate.algo import (
    CLAUDE_EXTENDED_THINKING_MODELS,
    NO_SUPPORT_TEMPERATURE_MODELS,
    STREAMING_REQUIRED_MODELS,
    SUPPORT_REASONING_EFFORT_MODELS,
    USER_MESSAGE_ONLY_MODELS,
)
from mergemate.algo.ai_handlers.litellm_helpers import (
    _get_azure_ad_token,
    _handle_streaming_response,
    _process_litellm_extra_body,
)
from mergemate.algo.utils import ReasoningEffort
from mergemate.core.config import ModelConfig
from mergemate.core.errors import AIHandlerError
from mergemate.log import get_logger

# ---------------------------------------------------------------------------
# Connection pooling — configure httpx for production-grade throughput
# ---------------------------------------------------------------------------
try:
    import httpx

    _httpx_limits = httpx.Limits(max_connections=100, max_keepalive_connections=20)
    _httpx_timeout = httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0)
    # Use a module-level client so all handler instances share the connection pool.
    _shared_http_client: httpx.AsyncClient | None = None

    def _get_http_client() -> httpx.AsyncClient:
        global _shared_http_client
        if _shared_http_client is None:
            _shared_http_client = httpx.AsyncClient(limits=_httpx_limits, timeout=_httpx_timeout)
        return _shared_http_client
except ImportError:
    _get_http_client = None  # type: ignore[assignment]

MODEL_RETRIES = 2
AI_TIMEOUT_SECONDS = 180  # 3-minute timeout for AI calls
DUMMY_LITELLM_API_KEY = "dummy_key"  # placeholder set when no OpenAI key is configured


# ---------------------------------------------------------------------------
# Provider credential store
# ---------------------------------------------------------------------------


@dataclass
class ProviderCredentials:
    """Holds API keys and endpoints for all supported AI providers.

    Stored per-instance — no global state mutation on litellm module.
    """

    openai_key: Optional[str] = None
    openai_org: Optional[str] = None
    openai_api_type: Optional[str] = None
    openai_api_version: Optional[str] = None
    openai_api_base: Optional[str] = None
    openai_deployment_id: Optional[str] = None

    anthropic_key: Optional[str] = None
    cohere_key: Optional[str] = None
    groq_key: Optional[str] = None
    sambanova_key: Optional[str] = None
    replicate_key: Optional[str] = None
    xai_key: Optional[str] = None
    huggingface_key: Optional[str] = None
    huggingface_api_base: Optional[str] = None
    huggingface_repetition_penalty: Optional[float] = None

    ollama_api_base: Optional[str] = None
    ollama_api_key: Optional[str] = None

    vertex_project: Optional[str] = None
    vertex_location: Optional[str] = None

    gemini_api_key: Optional[str] = None
    deepseek_key: Optional[str] = None
    deepinfra_key: Optional[str] = None
    mistral_key: Optional[str] = None
    codestral_key: Optional[str] = None

    openrouter_key: Optional[str] = None
    openrouter_api_base: Optional[str] = None

    azure_ad_client_id: Optional[str] = None
    azure_ad_api_base: Optional[str] = None
    azure: bool = False

    # AWS / Bedrock
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region_name: Optional[str] = None
    aws_session_token: Optional[str] = None

    # LiteLLM config
    drop_params: bool = False
    success_callback: Optional[list] = None
    failure_callback: Optional[list] = None
    service_callback: Optional[list] = None
    disable_aiohttp: bool = False

    # Extra fields from settings
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_raw_settings(cls, raw: dict[str, Any]) -> ProviderCredentials:
        """Build credentials from raw Dynaconf-style settings dict.

        Args:
            raw: Dict with uppercase section keys like 'OPENAI', 'ANTHROPIC', etc.
        """

        def _get(section: str, key: str, default=None):
            sec = raw.get(section.upper(), {})
            # Try original case, then lowercase, then uppercase
            return sec.get(key) or sec.get(key.lower()) or sec.get(key.upper()) or default

        creds = cls()

        # OpenAI
        creds.openai_key = _get("OPENAI", "KEY")
        creds.openai_org = _get("OPENAI", "ORG")
        creds.openai_api_type = _get("OPENAI", "API_TYPE")
        creds.openai_api_version = _get("OPENAI", "API_VERSION")
        creds.openai_api_base = _get("OPENAI", "API_BASE")
        creds.openai_deployment_id = _get("OPENAI", "DEPLOYMENT_ID")

        # Anthropic
        creds.anthropic_key = _get("ANTHROPIC", "KEY")

        # Cohere
        creds.cohere_key = _get("COHERE", "KEY")

        # Groq
        creds.groq_key = _get("GROQ", "KEY")

        # SambaNova
        creds.sambanova_key = _get("SAMBANOVA", "KEY")

        # Replicate
        creds.replicate_key = _get("REPLICATE", "KEY")

        # xAI
        creds.xai_key = _get("XAI", "KEY")

        # HuggingFace
        creds.huggingface_key = _get("HUGGINGFACE", "KEY")
        creds.huggingface_api_base = _get("HUGGINGFACE", "API_BASE")
        creds.huggingface_repetition_penalty = _get("HUGGINGFACE", "REPETITION_PENALTY")

        # Ollama
        creds.ollama_api_base = _get("OLLAMA", "API_BASE")
        creds.ollama_api_key = _get("OLLAMA", "API_KEY")

        # Vertex AI
        creds.vertex_project = _get("VERTEXAI", "VERTEX_PROJECT")
        creds.vertex_location = _get("VERTEXAI", "VERTEX_LOCATION")

        # Google AI Studio
        creds.gemini_api_key = _get("GOOGLE_AI_STUDIO", "GEMINI_API_KEY")

        # DeepSeek
        creds.deepseek_key = _get("DEEPSEEK", "KEY")

        # DeepInfra
        creds.deepinfra_key = _get("DEEPINFRA", "KEY")

        # Mistral
        creds.mistral_key = _get("MISTRAL", "KEY")

        # Codestral
        creds.codestral_key = _get("CODESTRAL", "KEY")

        # OpenRouter
        creds.openrouter_key = _get("OPENROUTER", "KEY")
        creds.openrouter_api_base = _get("OPENROUTER", "API_BASE", "https://openrouter.ai/api/v1")

        # Azure AD
        creds.azure_ad_client_id = _get("AZURE_AD", "CLIENT_ID")
        creds.azure_ad_api_base = _get("AZURE_AD", "API_BASE")
        if creds.openai_api_type == "azure":
            creds.azure = True

        # AWS
        creds.aws_access_key_id = _get("AWS", "AWS_ACCESS_KEY_ID")
        creds.aws_secret_access_key = _get("AWS", "AWS_SECRET_ACCESS_KEY")
        creds.aws_region_name = _get("AWS", "AWS_REGION_NAME")
        creds.aws_session_token = _get("AWS", "AWS_SESSION_TOKEN")

        # LiteLLM config
        creds.drop_params = _get("LITELLM", "DROP_PARAMS", False)
        creds.success_callback = _get("LITELLM", "SUCCESS_CALLBACK")
        creds.failure_callback = _get("LITELLM", "FAILURE_CALLBACK")
        creds.service_callback = _get("LITELLM", "SERVICE_CALLBACK")
        creds.disable_aiohttp = _get("LITELLM", "DISABLE_AIOHTTP", False)

        return creds

    def to_litellm_kwargs(self, model: str) -> dict[str, Any]:
        """Build litellm kwargs for the given model, selecting the right credentials.

        Uses provider-specific keys based on the model prefix.
        """
        kwargs: dict[str, Any] = {}

        if self.drop_params:
            kwargs["drop_params"] = True

        # Select the right API key based on model provider
        if model.startswith("bedrock/"):
            if self.aws_access_key_id:
                kwargs["aws_access_key_id"] = self.aws_access_key_id
            if self.aws_secret_access_key:
                kwargs["aws_secret_access_key"] = self.aws_secret_access_key
            if self.aws_region_name:
                kwargs["aws_region_name"] = self.aws_region_name
            if self.aws_session_token:
                kwargs["aws_session_token"] = self.aws_session_token
        elif model.startswith("azure/"):
            kwargs["api_key"] = self.openai_key
            if self.openai_api_base:
                kwargs["api_base"] = self.openai_api_base
            if self.openai_api_version:
                kwargs["api_version"] = self.openai_api_version
        elif model.startswith("claude") or model.startswith("anthropic/"):
            if self.anthropic_key:
                kwargs["api_key"] = self.anthropic_key
        elif model.startswith("command") or model.startswith("cohere/"):
            if self.cohere_key:
                kwargs["api_key"] = self.cohere_key
        elif model.startswith("groq/"):
            if self.groq_key:
                kwargs["api_key"] = self.groq_key
        elif model.startswith("vertex_ai/"):
            if self.vertex_project:
                kwargs["vertex_project"] = self.vertex_project
            if self.vertex_location:
                kwargs["vertex_location"] = self.vertex_location
        elif model.startswith("gemini/"):
            if self.gemini_api_key:
                kwargs["api_key"] = self.gemini_api_key
        elif model.startswith("deepseek/"):
            if self.deepseek_key:
                kwargs["api_key"] = self.deepseek_key
        elif model.startswith("mistral/"):
            if self.mistral_key:
                kwargs["api_key"] = self.mistral_key
        elif model.startswith("sambanova/"):
            if self.sambanova_key:
                kwargs["api_key"] = self.sambanova_key
        elif model.startswith("xai/"):
            if self.xai_key:
                kwargs["api_key"] = self.xai_key
        elif model.startswith("replicate/"):
            if self.replicate_key:
                kwargs["api_key"] = self.replicate_key
        elif model.startswith("ollama/"):
            if self.ollama_api_base:
                kwargs["api_base"] = self.ollama_api_base
            if self.ollama_api_key:
                kwargs["api_key"] = self.ollama_api_key
        elif model.startswith("huggingface/"):
            if self.huggingface_key:
                kwargs["api_key"] = self.huggingface_key
            if self.huggingface_api_base:
                kwargs["api_base"] = self.huggingface_api_base
        elif model.startswith("openrouter/"):
            if self.openrouter_key:
                kwargs["api_key"] = self.openrouter_key
            if self.openrouter_api_base:
                kwargs["api_base"] = self.openrouter_api_base
        elif model.startswith("codestral/"):
            if self.codestral_key:
                kwargs["api_key"] = self.codestral_key
        elif model.startswith("deepinfra/"):
            if self.deepinfra_key:
                kwargs["api_key"] = self.deepinfra_key
        else:
            # Default: OpenAI-compatible
            if self.openai_key:
                kwargs["api_key"] = self.openai_key
            if self.openai_api_base:
                kwargs["api_base"] = self.openai_api_base

        if self.openai_org:
            kwargs["organization"] = self.openai_org

        return kwargs


# ---------------------------------------------------------------------------
# LiteLLM AI Handler
# ---------------------------------------------------------------------------


class LiteLLMAIHandler:
    """AI handler using LiteLLM for multi-provider support.

    No global state mutation. All provider credentials are stored per-instance
    and passed as kwargs to litellm.acompletion().
    """

    def __init__(
        self, credentials: Optional[ProviderCredentials] = None, raw_settings: Optional[dict[str, Any]] = None
    ) -> None:
        """Initialize with provider credentials.

        Args:
            credentials: Pre-built ProviderCredentials. If None, built from raw_settings.
            raw_settings: Dict of raw settings (e.g., from AppConfig._raw). Used if credentials is None.
        """
        if credentials is not None:
            self.credentials = credentials
        elif raw_settings is not None:
            self.credentials = ProviderCredentials.from_raw_settings(raw_settings)
        else:
            # Fallback: try legacy config loader
            from mergemate.config_loader import get_settings

            raw = {
                k.upper(): dict(v) if hasattr(v, "items") else v
                for k, v in get_settings().items()
                if isinstance(k, str)
            }
            self.credentials = ProviderCredentials.from_raw_settings(raw)

        # Model capability lists (these are module-level constants, fine to reference)
        self.user_message_only_models = USER_MESSAGE_ONLY_MODELS
        self.no_support_temperature_models = NO_SUPPORT_TEMPERATURE_MODELS
        self.support_reasoning_models = SUPPORT_REASONING_EFFORT_MODELS
        self.claude_extended_thinking_models = CLAUDE_EXTENDED_THINKING_MODELS
        self.streaming_required_models = STREAMING_REQUIRED_MODELS

        # AWS Bedrock state (needs env var management for litellm internals)
        self._aws_imds_mode = os.environ.get("AWS_USE_IMDS", "").strip().lower() in ("1", "true", "yes")
        self._aws_boto3_creds = None
        self._aws_static_creds = None
        self._aws_bedrock_lock = asyncio.Lock()
        self._setup_aws_if_needed()

    def _setup_aws_if_needed(self) -> None:
        """Initialize AWS credentials using IMDS or static keys."""
        if not self._aws_imds_mode and not self.credentials.aws_access_key_id:
            return

        if self._aws_imds_mode:
            try:
                import boto3

                session = boto3.Session()
                creds = session.get_credentials()
                if creds:
                    self._aws_boto3_creds = creds
                    self._write_aws_creds(creds.get_frozen_credentials())
                    if not os.environ.get("AWS_REGION_NAME"):
                        if self.credentials.aws_region_name:
                            os.environ["AWS_REGION_NAME"] = self.credentials.aws_region_name
                        elif session.region_name:
                            os.environ["AWS_REGION_NAME"] = session.region_name
                    # Stash static creds for fallback
                    if self.credentials.aws_access_key_id and self.credentials.aws_secret_access_key:
                        self._aws_static_creds = {
                            "AWS_ACCESS_KEY_ID": self.credentials.aws_access_key_id,
                            "AWS_SECRET_ACCESS_KEY": self.credentials.aws_secret_access_key,
                            "AWS_REGION_NAME": self.credentials.aws_region_name
                            or os.environ.get("AWS_REGION_NAME", ""),
                        }
                        if self.credentials.aws_session_token:
                            self._aws_static_creds["AWS_SESSION_TOKEN"] = self.credentials.aws_session_token
            except Exception as exc:
                get_logger().warning(f"AWS IMDS init failed: {exc}")
                self._aws_imds_mode = False

        if not self._aws_imds_mode and self.credentials.aws_access_key_id:
            os.environ["AWS_ACCESS_KEY_ID"] = self.credentials.aws_access_key_id
            os.environ["AWS_SECRET_ACCESS_KEY"] = self.credentials.aws_secret_access_key
            if self.credentials.aws_region_name:
                os.environ["AWS_REGION_NAME"] = self.credentials.aws_region_name
            if self.credentials.aws_session_token:
                os.environ["AWS_SESSION_TOKEN"] = self.credentials.aws_session_token

    @staticmethod
    def _write_aws_creds(frozen) -> None:
        """Write botocore frozen credentials into os.environ."""
        os.environ["AWS_ACCESS_KEY_ID"] = frozen.access_key
        os.environ["AWS_SECRET_ACCESS_KEY"] = frozen.secret_key
        if frozen.token:
            os.environ["AWS_SESSION_TOKEN"] = frozen.token
        elif "AWS_SESSION_TOKEN" in os.environ:
            del os.environ["AWS_SESSION_TOKEN"]

    def _refresh_aws_credentials(self) -> bool:
        """Refresh AWS credentials for Bedrock calls."""
        if self._aws_boto3_creds is None:
            return False
        try:
            self._write_aws_creds(self._aws_boto3_creds.get_frozen_credentials())
            return True
        except Exception:
            get_logger().exception("AWS credential refresh failed")
            return False

    @property
    def deployment_id(self) -> Optional[str]:
        return self.credentials.openai_deployment_id

    async def chat_completion(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        img_path: Optional[str] = None,
    ) -> tuple[str, str]:
        """Send a chat completion request.

        Returns:
            Tuple of (response_text, status) where status is 'ok' or 'error'.
        """
        try:
            return await self._do_chat_completion(model, system, user, temperature, img_path)
        except openai.RateLimitError:
            return "Rate limit exceeded. Please try again later.", "error"
        except openai.APIError as exc:
            return f"API error: {exc}", "error"
        except Exception as exc:
            return f"Unexpected error: {exc}", "error"

    @retry(
        retry=retry_if_exception_type((openai.APIError, ConnectionError, TimeoutError, asyncio.TimeoutError))
        & retry_if_not_exception_type(openai.RateLimitError),
        stop=stop_after_attempt(MODEL_RETRIES + 1),  # 3 total attempts
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _do_chat_completion(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float,
        img_path: Optional[str],
    ) -> tuple[str, str]:
        """Core chat completion with retry logic."""
        is_bedrock = "bedrock/" in model
        async with self._aws_bedrock_lock if is_bedrock else contextlib.nullcontext():
            if is_bedrock and self._aws_imds_mode:
                if not self._refresh_aws_credentials() and self._aws_static_creds:
                    self._activate_static_fallback()

            # Azure model prefix
            if self.credentials.azure:
                model = "azure/" + model

            # Claude requires a non-empty system prompt
            if "claude" in model and not system:
                system = "No system prompt provided"

            # Build messages
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

            # Handle image input
            if img_path:
                result = self._handle_image(img_path, messages)
                if result:
                    return result

            # Strip temperature for models that don't support it
            if model in self.no_support_temperature_models:
                temperature = None

            # Build litellm kwargs with provider credentials
            kwargs = self.credentials.to_litellm_kwargs(model)
            kwargs["temperature"] = temperature if temperature is not None else 0.2

            # Configure reasoning effort for supported models
            if model in self.support_reasoning_models:
                kwargs["reasoning_effort"] = ReasoningEffort.HIGH.value

            # Handle streaming-required models
            if model in self.streaming_required_models:
                kwargs["stream"] = True

            # Process extra body parameters
            kwargs = _process_litellm_extra_body(kwargs)

            # Make the API call with timeout
            kwargs["timeout"] = AI_TIMEOUT_SECONDS
            if model in self.streaming_required_models:
                response = await _handle_streaming_response(
                    await litellm.acompletion(model=model, messages=messages, **kwargs)
                )
                resp = response
                finish_reason = "stop"
            else:
                response = await litellm.acompletion(model=model, messages=messages, **kwargs)
                resp = response.choices[0].message.content
                finish_reason = response.choices[0].finish_reason

            return resp, "ok"

    def _handle_image(self, img_path: str, messages: list) -> Optional[tuple[str, str]]:
        """Validate and attach image to the message. Returns error tuple if image is invalid."""
        try:
            r = requests.head(img_path, allow_redirects=True, timeout=10)
            if r.status_code == 404:
                error_msg = (
                    f"The image link is not accessible: {img_path}. "
                    "Please repost the original image as a comment and try again."
                )
                get_logger().error(error_msg)
                return error_msg, "error"
        except Exception as exc:
            get_logger().error(f"Error fetching image: {img_path}", exc)
            return f"Error fetching image: {img_path}", "error"

        messages[1]["content"] = [
            {"type": "text", "text": messages[1]["content"]},
            {"type": "image_url", "image_url": {"url": img_path}},
        ]
        return None

    def _activate_static_fallback(self) -> None:
        """Switch to static AWS credentials after IMDS failure."""
        if not self._aws_static_creds:
            return
        os.environ["AWS_ACCESS_KEY_ID"] = self._aws_static_creds["AWS_ACCESS_KEY_ID"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = self._aws_static_creds["AWS_SECRET_ACCESS_KEY"]
        os.environ["AWS_REGION_NAME"] = self._aws_static_creds["AWS_REGION_NAME"]
        if "AWS_SESSION_TOKEN" in self._aws_static_creds:
            os.environ["AWS_SESSION_TOKEN"] = self._aws_static_creds["AWS_SESSION_TOKEN"]
        get_logger().warning("Bedrock call failed with IMDS credentials; retrying with static credentials")
