from argparse import Namespace
from unittest.mock import MagicMock, patch

from mergemate import cli


def test_build_parser_supports_config_flag():
    parser = cli.build_parser()
    args = parser.parse_args(
        ["--pr_url=https://github.com/a/b/pull/1", "--config", "/path/to/.mergemate.toml", "review"]
    )
    assert args.config == "/path/to/.mergemate.toml"


def test_run_passes_config_flag_to_load_config():
    """When --config is supplied, _load_config is called with the path."""
    fake_config = MagicMock()

    with (
        patch.object(cli, "_load_config", return_value=fake_config) as mock_load,
        patch.object(cli, "_handle", return_value=0),
    ):
        cli.run(
            args=Namespace(
                pr_url="https://github.com/a/b/pull/1",
                issue_url=None,
                config="/path/to/.mergemate.toml",
                model=None,
                log_level="INFO",
                log_format="CONSOLE",
                command="review",
                rest=[],
            )
        )

    mock_load.assert_called_once()
    assert mock_load.call_args[0][0].config == "/path/to/.mergemate.toml"


def test_run_loads_default_config_when_no_flag():
    """Without --config, _load_config receives None for config attribute."""
    fake_config = MagicMock()

    with (
        patch.object(cli, "_load_config", return_value=fake_config) as mock_load,
        patch.object(cli, "_handle", return_value=0),
    ):
        cli.run(
            args=Namespace(
                pr_url="https://github.com/a/b/pull/1",
                issue_url=None,
                config=None,
                model=None,
                log_level="INFO",
                log_format="CONSOLE",
                command="review",
                rest=[],
            )
        )

    mock_load.assert_called_once()
    assert mock_load.call_args[0][0].config is None


def test_run_applies_model_override():
    """When --model is supplied, _load_config includes it."""
    fake_config = MagicMock()

    with (
        patch.object(cli, "_load_config", return_value=fake_config) as mock_load,
        patch.object(cli, "_handle", return_value=0),
    ):
        cli.run(
            args=Namespace(
                pr_url="https://github.com/a/b/pull/1",
                issue_url=None,
                config=None,
                model="gpt-4o",
                log_level="INFO",
                log_format="CONSOLE",
                command="review",
                rest=[],
            )
        )

    mock_load.assert_called_once()
    assert mock_load.call_args[0][0].model == "gpt-4o"


def test_run_forwards_request_to_handle():
    """The assembled url and request list are forwarded to _handle."""
    fake_config = MagicMock()

    with (
        patch.object(cli, "_load_config", return_value=fake_config),
        patch.object(cli, "_handle", return_value=0) as mock_handle,
    ):
        cli.run(
            args=Namespace(
                pr_url="https://github.com/a/b/pull/1",
                issue_url=None,
                config=None,
                model=None,
                log_level="INFO",
                log_format="CONSOLE",
                command="review",
                rest=["--verbose"],
            )
        )

    mock_handle.assert_called_once_with(
        "https://github.com/a/b/pull/1",
        ["review", "--verbose"],
        fake_config,
    )
