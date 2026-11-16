"""Shared settings of the tests."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep git in the tests away from the repository the tests run in.

    The hooks run pytest from git commit, which exports GIT_DIR, GIT_INDEX_FILE and the like to them:
    inherited, they'd make the git of a test's temporary repository write to the real one's config
    and index instead.
    """
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
