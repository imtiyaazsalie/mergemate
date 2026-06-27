"""MergeMate setup wizard — AI-powered project initialization.

Generates .mergemate.toml and GitHub Actions workflow based on your project.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from mergemate.core.config import AppConfig
from mergemate.log import get_logger

SETUP_SYSTEM_PROMPT = """You are a MergeMate configuration expert. Your job is to analyze a user's project
description and generate the optimal .mergemate.toml configuration file.

Based on the project description, determine:
- Which AI model would work best (consider cost, speed, quality)
- What review strictness level is appropriate
- Whether to enable auto-approval
- Whether inline code suggestions make sense for this project
- Any language-specific configurations needed
- Whether to auto-describe, auto-review, auto-improve on every PR

Output ONLY valid TOML — nothing else. No markdown fences, no explanation."""

SETUP_USER_PROMPT = """Generate a .mergemate.toml for this project:

Project description: {description}

Git provider: {provider}
Language(s): {languages}
Team size: {team_size}
Project type: {project_type} (library, web app, mobile, CLI tool, etc.)
Open source: {is_open_source}

Include settings for:
- [config] — model, git_provider, publish_output
- [pr_reviewer] — review strictness, inline comments, auto-approval
- [pr_code_suggestions] — number of suggestions, committable suggestions
- [pr_description] — auto-describe settings
- [github_app] or [github_action_config] — automation settings

Use {model} as the AI model. Make it practical and production-ready."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mergemate init",
        description="AI-powered setup wizard for MergeMate",
    )
    parser.add_argument("--output", "-o", type=str, default=".", help="Directory to write config files to")
    parser.add_argument("--provider", type=str, default="github", help="Git provider (github, gitlab, bitbucket)")
    parser.add_argument("--model", type=str, default="deepseek/deepseek-v4-flash", help="AI model for the wizard")
    parser.add_argument("--description", "-d", type=str, help="Brief description of your project")
    parser.add_argument("--language", "-l", type=str, default="", help="Primary programming language")
    parser.add_argument("--team-size", type=str, default="small", choices=["solo", "small", "medium", "large"])
    parser.add_argument("--project-type", type=str, default="web", help="library, web, mobile, cli, etc.")
    parser.add_argument("--open-source", action="store_true", default=True)
    parser.add_argument("--no-open-source", dest="open_source", action="store_false")
    return parser


def detect_project(output_dir: Path) -> dict:
    """Auto-detect project details from the repo."""
    info = {
        "description": "",
        "languages": "",
        "provider": "github",
        "team_size": "small",
        "project_type": "web",
        "is_open_source": True,
    }

    # Detect language from common files
    language_indicators = {
        "package.json": "JavaScript/TypeScript",
        "tsconfig.json": "TypeScript",
        "requirements.txt": "Python",
        "pyproject.toml": "Python",
        "Cargo.toml": "Rust",
        "go.mod": "Go",
        "Gemfile": "Ruby",
        "composer.json": "PHP",
        "pom.xml": "Java",
        "build.gradle": "Java/Kotlin",
        "CMakeLists.txt": "C/C++",
        "Package.swift": "Swift",
        "mix.exs": "Elixir",
    }
    detected = []
    for filename, lang in language_indicators.items():
        if (output_dir / filename).exists():
            detected.append(lang)
    if detected:
        info["languages"] = ", ".join(detected)

    # Detect project type
    if (output_dir / "package.json").exists():
        info["project_type"] = "web"
    elif (output_dir / "Cargo.toml").exists():
        info["project_type"] = "cli"
    elif (output_dir / "requirements.txt" or output_dir / "pyproject.toml").exists():
        info["project_type"] = "library"

    # Read existing description
    readme = output_dir / "README.md"
    if readme.exists():
        first_line = readme.read_text().split("\n")[0].strip("# ").strip()
        if first_line:
            info["description"] = first_line

    # Detect git remote for provider
    git_config = output_dir / ".git" / "config"
    if git_config.exists():
        content = git_config.read_text()
        if "gitlab" in content:
            info["provider"] = "gitlab"
        elif "bitbucket" in content:
            info["provider"] = "bitbucket"

    return info


async def generate_config(info: dict, model: str) -> str:
    """Use AI to generate a .mergemate.toml based on project info."""
    from mergemate.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler, ProviderCredentials
    from mergemate.config_loader import get_settings

    raw = {k.upper(): dict(v) if hasattr(v, "items") else v for k, v in get_settings().items() if isinstance(k, str)}
    creds = ProviderCredentials.from_raw_settings(raw)
    handler = LiteLLMAIHandler(credentials=creds)

    prompt = SETUP_USER_PROMPT.format(
        description=info["description"] or "A software project",
        provider=info["provider"],
        languages=info["languages"] or "unknown",
        team_size=info["team_size"],
        project_type=info["project_type"],
        is_open_source="yes" if info["is_open_source"] else "no",
        model=model,
    )

    response, status = await handler.chat_completion(
        model=model,
        system=SETUP_SYSTEM_PROMPT,
        user=prompt,
        temperature=0.1,
    )

    if status != "ok":
        raise RuntimeError(f"AI setup failed: {response}")

    # Strip any markdown fences
    toml = response.strip()
    if toml.startswith("```"):
        toml = toml.split("\n", 1)[1] if "\n" in toml else toml[3:]
    if toml.endswith("```"):
        toml = toml.rsplit("\n", 1)[0] if "\n" in toml else toml[:-3]

    return toml.strip()


def generate_github_action(output_dir: Path, info: dict) -> str:
    """Generate a GitHub Actions workflow file."""
    model_env = "DEEPSEEK_API_KEY" if "deepseek" in str(info.get("model", "")).lower() else "OPENAI_KEY"

    return f"""\
name: MergeMate

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  issue_comment:
    types: [created]

jobs:
  review:
    if: ${{{{ github.event.sender.type != 'Bot' }}}}
    runs-on: ubuntu-latest
    permissions:
      issues: write
      pull-requests: write
      contents: write
    steps:
      - uses: mergemate/mergemate@main
        env:
          {model_env}: ${{{{ secrets.{model_env} }}}}
          GITHUB_TOKEN: ${{{{ secrets.GITHUB_TOKEN }}}}
"""


def run(args: argparse.Namespace | None = None) -> int:
    if args is None:
        parser = build_parser()
        args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    get_logger().info(f"Initializing MergeMate in {output_dir}")

    # Detect project info
    info = detect_project(output_dir)

    # Override with CLI args
    if args.description:
        info["description"] = args.description
    if args.language:
        info["languages"] = args.language
    info["provider"] = args.provider
    info["team_size"] = args.team_size
    info["project_type"] = args.project_type
    info["is_open_source"] = args.open_source
    info["model"] = args.model

    get_logger().info(f"Detected: {info['languages'] or 'unknown language'} {info['project_type']} project")

    # Generate config with AI
    print(f"\n🤖 Generating optimal config for your {info['project_type']} project...")
    try:
        toml_content = asyncio.run(generate_config(info, args.model))
    except Exception as e:
        get_logger().error(f"AI setup failed: {e}")
        print(f"\n❌ AI setup failed: {e}")
        print("Falling back to interactive setup...\n")
        toml_content = _interactive_setup(info)

    # Write .mergemate.toml
    config_path = output_dir / ".mergemate.toml"
    config_path.write_text(toml_content)
    print(f"\n✅ Created {config_path}")

    # Generate GitHub Action if applicable
    if info["provider"] == "github":
        workflow_dir = output_dir / ".github" / "workflows"
        workflow_dir.mkdir(parents=True, exist_ok=True)
        workflow_path = workflow_dir / "mergemate.yml"
        workflow_content = generate_github_action(output_dir, info)
        workflow_path.write_text(workflow_content)
        print(f"✅ Created {workflow_path}")

    # Print next steps
    model_key = "DEEPSEEK_API_KEY" if "deepseek" in args.model.lower() else "OPENAI_KEY"
    print(f"""
🚀 Next steps:

1. Add your API key as a GitHub secret:
   Settings → Secrets and variables → Actions → New repository secret
   Name: {model_key}
   Value: <your API key>

2. Commit and push:
   git add .mergemate.toml .github/workflows/mergemate.yml
   git commit -m "Add MergeMate AI code review"
   git push

3. Open a pull request — MergeMate will review it automatically!

Or run locally:
   mergemate --pr_url <url> --model {args.model} review
""")

    return 0


def _interactive_setup(info: dict) -> str:
    """Fallback: generate a sensible default config without AI."""
    return f"""\
# MergeMate configuration
# Generated for a {info["project_type"]} project ({info.get("languages", "unknown")})

[config]
model = "{info.get("model", "deepseek/deepseek-v4-flash")}"
git_provider = "{info["provider"]}"
publish_output = true

[pr_reviewer]
num_max_findings = 10
enable_review_labels_effort = true
persistent_comment = true
inline_code_comments = true

[pr_code_suggestions]
num_code_suggestions = 4
commitable_code_suggestions = true
"""


if __name__ == "__main__":
    raise SystemExit(run())
