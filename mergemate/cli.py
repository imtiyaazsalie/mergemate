"""MergeMate CLI — command-line interface for PR review automation."""

from __future__ import annotations

import argparse
import asyncio
import os

from mergemate.core.config import AppConfig
from mergemate.core.logging import LogFormat, setup
from mergemate.log import get_logger


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="mergemate",
        description="AI-powered pull request review and automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Commands:
  init         AI-powered setup wizard — generates .mergemate.toml
  review       Comprehensive PR review with findings and suggestions
  describe     Generate or update PR title and description
  improve      Suggest code improvements as inline comments
  ask          Ask questions about the PR
  update_changelog  Update CHANGELOG based on PR changes
  add_docs     Generate documentation for changed code
  generate_labels   Auto-label PRs based on content
  similar_issue     Find issues similar to this PR

Examples:
  mergemate --pr_url https://github.com/owner/repo/pull/42 review
  mergemate --pr_url https://github.com/owner/repo/pull/42 describe
  mergemate --pr_url https://github.com/owner/repo/pull/42 ask "What changed in utils.py?"
""",
    )

    parser.add_argument("--pr_url", type=str, default=None, help="URL of the pull request to process")
    parser.add_argument("--issue_url", type=str, default=None, help="URL of the issue to process")
    parser.add_argument("--config", type=str, default=None, help="Path to .mergemate.toml config file")
    parser.add_argument("--model", type=str, default=None, help="Override the AI model (e.g., gpt-4o, claude-3-opus)")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--log-format", type=str, default="CONSOLE", choices=["CONSOLE", "JSON"])
    parser.add_argument("command", type=str, nargs="?", default="review", help="Command to run")
    parser.add_argument("rest", nargs=argparse.REMAINDER, default=[], help="Additional arguments for the command")

    return parser


def run(args: argparse.Namespace | None = None) -> int:
    """Run MergeMate from the command line.

    Returns exit code: 0 on success, 1 on failure.
    """
    if args is None:
        parser = build_parser()
        args = parser.parse_args()

    # Handle init command separately (no PR URL needed)
    if args.command == "init":
        from mergemate.setup import run as setup_run

        return setup_run()

    # Validate input
    if not args.pr_url and not args.issue_url:
        build_parser().print_help()
        return 1

    # Setup logging
    setup(level=args.log_level, fmt=LogFormat(args.log_format))

    # Load configuration
    try:
        config = _load_config(args)
    except Exception as exc:
        get_logger().error(f"Failed to load configuration: {exc}")
        return 1

    # Build and run the agent
    url = args.pr_url or args.issue_url
    request = [args.command] + (args.rest or [])

    return asyncio.run(_handle(url, request, config))


def _load_config(args: argparse.Namespace) -> AppConfig:
    """Load configuration from defaults, optional config file, and CLI overrides."""
    if args.config:
        config = AppConfig.from_settings_dir(os.path.dirname(args.config))
    else:
        config = AppConfig.load_default()

    # Apply CLI overrides
    if args.model:
        config = config.with_overrides(model=args.model)

    return config


async def _handle(url: str, request: list[str], config: AppConfig) -> int:
    """Run the agent and return exit code."""
    from mergemate.agent.mergemate import MergeMateAgent
    from mergemate.config_loader import get_settings

    # Sync model to legacy Dynaconf settings (tools still read from there)
    if config.model.model:
        get_settings().set("config.model", config.model.model)

    agent = MergeMateAgent(config=config)
    success = await agent.handle(url, request)

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(run())
