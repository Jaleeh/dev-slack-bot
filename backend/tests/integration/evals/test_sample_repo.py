import shutil
from pathlib import Path

import pytest

from evals.sample_repo import SampleRepo, SampleRepoError, fetch_sample_repo
from tests.integration.evals.conftest import commit_and_tag, git


def a_repo(origin: Path, ref: str = "v1") -> SampleRepo:
    return SampleRepo(name="tiny", url=origin.as_uri(), ref=ref)


def test_fetch_clones_the_ref(origin_repo: Path, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"

    clone = fetch_sample_repo(a_repo(origin_repo), cache_dir)

    assert clone == cache_dir / "tiny@v1"
    assert (clone / "src" / "a.py").is_file()


def test_fetch_reuses_the_cached_clone(origin_repo: Path, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    first = fetch_sample_repo(a_repo(origin_repo), cache_dir)
    shutil.rmtree(origin_repo)

    second = fetch_sample_repo(a_repo(origin_repo), cache_dir)

    assert second == first


def test_fetch_uses_a_new_clone_for_a_new_ref(origin_repo: Path, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    first = fetch_sample_repo(a_repo(origin_repo), cache_dir)
    (origin_repo / "src" / "c.py").write_text("c = 3\n")
    commit_and_tag(origin_repo, "v2")

    second = fetch_sample_repo(a_repo(origin_repo, "v2"), cache_dir)

    assert (second / "src" / "c.py").is_file()
    assert not (first / "src" / "c.py").exists()


def test_fetch_fails_clearly_for_an_unknown_ref(origin_repo: Path, tmp_path: Path) -> None:
    with pytest.raises(SampleRepoError, match="nope"):
        fetch_sample_repo(a_repo(origin_repo, "nope"), tmp_path / "cache")


def test_failed_fetch_leaves_nothing_in_the_cache(origin_repo: Path, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"

    with pytest.raises(SampleRepoError):
        fetch_sample_repo(a_repo(origin_repo, "nope"), cache_dir)

    assert list(cache_dir.iterdir()) == []


def test_fetch_fails_clearly_without_git(
    origin_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")

    with pytest.raises(SampleRepoError, match="git"):
        fetch_sample_repo(a_repo(origin_repo), tmp_path / "cache")


def test_fetch_handles_a_ref_with_a_slash(origin_repo: Path, tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    git(origin_repo, "tag", "release/v1")

    clone = fetch_sample_repo(a_repo(origin_repo, "release/v1"), cache_dir)

    assert clone == cache_dir / "tiny@release%2Fv1"
    assert (clone / "src" / "a.py").is_file()


def test_a_cached_ref_with_a_slash_is_not_mistaken_for_a_shorter_ref(
    origin_repo: Path, tmp_path: Path
) -> None:
    cache_dir = tmp_path / "cache"
    git(origin_repo, "tag", "release/v1")
    fetch_sample_repo(a_repo(origin_repo, "release/v1"), cache_dir)
    git(origin_repo, "tag", "--delete", "release/v1")
    git(origin_repo, "tag", "release")

    clone = fetch_sample_repo(a_repo(origin_repo, "release"), cache_dir)

    assert (clone / "src" / "a.py").is_file()
