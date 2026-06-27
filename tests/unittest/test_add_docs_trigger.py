import pytest

pytestmark = pytest.mark.skip(reason="Server trigger integration test — needs GitHub App setup refactored")


@pytest.mark.asyncio
async def test_placeholder():
    """This file is skipped until the GitHub App server is refactored."""
    pass
