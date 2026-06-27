"""PR Config tool — lists configuration options for the user.

Rewritten using the BaseTool pipeline pattern with dependency injection.
"""

from __future__ import annotations

from dynaconf import Dynaconf

from mergemate.config_loader import get_settings
from mergemate.log import get_logger
from mergemate.tools.base import BaseTool


class PRConfig(BaseTool):
    """Lists all available configuration options and publishes them as a PR comment.

    Pipeline:
        1. _prepare() — read config, build markdown
        2. _predict() — no AI call needed; returns the prepared content
        3. _publish() — publish the config comment to the PR
    """

    @property
    def tool_name(self) -> str:
        return "config"

    # ------------------------------------------------------------------
    # Pipeline phases
    # ------------------------------------------------------------------

    async def _prepare(self) -> None:
        """Read configuration and build the markdown output."""
        get_logger().info("Preparing configs...")
        self._pr_comment = self._prepare_pr_configs()

    async def _predict(self) -> str:
        """No AI call — return the prepared markdown directly."""
        return self._pr_comment

    async def _publish(self, result: str) -> None:
        """Publish the configuration listing as a PR comment."""
        if self.config.publish_output:
            get_logger().info("Pushing configs...")
            self.git_provider.publish_comment(result)
        else:
            get_logger().info(f"Config comment:\n{result}")

    # ------------------------------------------------------------------
    # Config-specific logic
    # ------------------------------------------------------------------

    def _prepare_pr_configs(self) -> str:
        try:
            conf_file = get_settings().find_file("configuration.toml")
            dynconf_kwargs = {
                "core_loaders": [],
                "loaders": ["mergemate.custom_merge_loader"],
                "merge_enabled": True,
            }
            conf_settings = Dynaconf(
                settings_files=[conf_file],
                load_dotenv=False,
                envvar_prefix=False,
                **dynconf_kwargs,
            )
        except Exception as e:
            get_logger().error(
                "Caught exception during Dynaconf loading. Returning empty dict",
                artifact={"exception": e},
            )
            conf_settings = {}

        configuration_headers = [header.lower() for header in conf_settings.keys()]
        relevant_configs = {
            header: configs
            for header, configs in get_settings().to_dict().items()
            if (header.lower().startswith("pr_") or header.lower().startswith("config"))
            and header.lower() in configuration_headers
        }

        skip_keys = [
            "ai_disclaimer",
            "ai_disclaimer_title",
            "ANALYTICS_FOLDER",
            "secret_provider",
            "skip_keys",
            "app_id",
            "redirect",
            "trial_prefix_message",
            "no_eligible_message",
            "identity_provider",
            "ALLOWED_REPOS",
            "APP_NAME",
            "PERSONAL_ACCESS_TOKEN",
            "shared_secret",
            "key",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "user_token",
            "private_key",
            "private_key_id",
            "client_id",
            "client_secret",
            "token",
            "bearer_token",
            "jira_api_token",
            "webhook_secret",
        ]
        partial_skip_keys = ["key", "secret", "token", "private"]
        extra_skip_keys = get_settings().config.get("config.skip_keys", [])
        if extra_skip_keys:
            skip_keys.extend(extra_skip_keys)
        skip_keys_lower = [key.lower() for key in skip_keys]

        markdown_text = "<details> <summary><strong>🛠️ MergeMate Configurations:</strong></summary> \n\n"
        markdown_text += "\n\n```yaml\n\n"
        for header, configs in relevant_configs.items():
            if configs:
                markdown_text += "\n\n"
                markdown_text += f"==================== {header} ===================="
            for key, value in configs.items():
                if key.lower() in skip_keys_lower:
                    continue
                if any(skip_key in key.lower() for skip_key in partial_skip_keys):
                    continue
                markdown_text += (
                    f"\n{header.lower()}.{key.lower()} = {repr(value) if isinstance(value, str) else value}"
                )
                markdown_text += "  "
        markdown_text += "\n```"
        markdown_text += "\n</details>\n"
        get_logger().info("Possible Configurations outputted to PR comment", artifact=markdown_text)
        return markdown_text


# ---------------------------------------------------------------------------
# Module-level helpers for the tool registry
# ---------------------------------------------------------------------------


def get_config_class() -> type:
    """Return the PRConfig class for the tool registry factory."""
    return PRConfig
