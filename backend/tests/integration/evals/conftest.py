import subprocess
from pathlib import Path

import pytest

GIT_IDENTITY = ("-c", "user.name=test", "-c", "user.email=test@example.com")


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *GIT_IDENTITY, *args], cwd=repo, check=True, capture_output=True)


def commit_and_tag(repo: Path, tag: str) -> None:
    git(repo, "add", ".")
    git(repo, "commit", "-m", tag)
    git(repo, "tag", tag)


@pytest.fixture
def origin_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "origin"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.py").write_text("a = 1\n")

    git(repo, "init", "--quiet")
    commit_and_tag(repo, "v1")

    return repo
