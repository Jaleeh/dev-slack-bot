import subprocess
from pathlib import Path

import pytest

from tests.support import UNREACHABLE_URL

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


@pytest.fixture
def offline_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default models at an unreachable Ollama, ignoring any agent settings in `.env`."""
    monkeypatch.setenv("CHAT_MODEL", "ollama:ornith:9b")
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "")
    monkeypatch.setenv("OLLAMA_BASE_URL", UNREACHABLE_URL)
    monkeypatch.delenv("RETRIEVAL", raising=False)
    monkeypatch.delenv("SEARCH_SKIP", raising=False)


@pytest.fixture
def sample_cache(tmp_path: Path) -> Path:
    """A cache folder that already holds the sample repo, so no test needs the network."""
    cache = tmp_path / "cache"
    clone = cache / "django-oscar@4.2.1"
    clone.mkdir(parents=True)
    (clone / "README.md").write_text("Oscar\n")

    return cache
