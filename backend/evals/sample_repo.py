"""A cached shallow clone of the repository the evals run against."""

import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from evals.question_set import QuestionSet

REPO_URLS: Mapping[str, str] = {
    "django-oscar": "https://github.com/django-oscar/django-oscar.git",
}


class SampleRepoError(RuntimeError):
    pass


@dataclass(frozen=True)
class SampleRepo:
    name: str
    url: str
    ref: str


def sample_repo_for(
    question_set: QuestionSet, repo_urls: Mapping[str, str] = REPO_URLS
) -> SampleRepo:
    """The repository and ref a question set was written against."""
    url = repo_urls.get(question_set.repo)
    if url is None:
        raise SampleRepoError(f"no URL known for repo {question_set.repo}")

    return SampleRepo(name=question_set.repo, url=url, ref=question_set.ref)


def fetch_sample_repo(repo: SampleRepo, cache_dir: Path) -> Path:
    """Returns the clone folder, cloning on first use. Raises SampleRepoError if the fetch fails."""
    # Encoding keeps a ref like release/v1 to one folder that can't clash with another ref.
    clone = cache_dir / f"{repo.name}@{quote(repo.ref, safe='')}"
    if clone.exists():
        return clone

    cache_dir.mkdir(parents=True, exist_ok=True)
    # Cloning beside the final folder and renaming means a fetch that dies halfway
    # never leaves something a later run would mistake for a good clone.
    staging = Path(tempfile.mkdtemp(dir=cache_dir))
    try:
        _clone(repo, staging)
        staging.rename(clone)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    return clone


def _clone(repo: SampleRepo, destination: Path) -> None:
    command = ["git", "clone", "--quiet", "--depth", "1", "--branch", repo.ref, repo.url]

    try:
        subprocess.run([*command, str(destination)], check=True, capture_output=True, text=True)
    except FileNotFoundError as error:
        raise SampleRepoError("git is not installed or not on PATH") from error
    except subprocess.CalledProcessError as error:
        message = f"could not fetch {repo.url} at {repo.ref}: {error.stderr.strip()}"
        raise SampleRepoError(message) from error
