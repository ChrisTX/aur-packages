"""Running git: the paths it lists."""

import subprocess
from pathlib import Path

import pytest

from aur_packages import git


def test_paths_as_they_are(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    # core.quotePath would quote the first in the line-separated output, the others are lost to lines
    # and stripping
    names = ["café/PKGBUILD", "a b/PKGBUILD", "trailing /PKGBUILD", "new\nline/PKGBUILD"]
    for name in names:
        (tmp_path / name).parent.mkdir()
        (tmp_path / name).touch()
    subprocess.run(["git", "add", "--", *names], check=True)
    assert sorted(git.paths("diff", "--cached", "--name-only", "--", "*/PKGBUILD")) == sorted(names)
    assert sorted(git.paths("ls-files")) == sorted(names)
