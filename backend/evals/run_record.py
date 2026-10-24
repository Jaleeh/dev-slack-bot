"""What every eval run records about itself, and how it is saved and shown."""

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

EVALS_DIR = Path(__file__).parent
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


class RepoCommitError(RuntimeError):
    pass


def git_commit() -> str:
    commit = _git("rev-parse", "HEAD")

    # A run from uncommitted code can't be reproduced from the commit alone.
    return f"{commit}-dirty" if _git("status", "--porcelain") else commit


def _git(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args], cwd=EVALS_DIR, check=True, capture_output=True, text=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RepoCommitError(f"could not read this repo's commit: {error}") from error

    return completed.stdout.strip()


def write_record(record: BaseModel, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")

    return path


def format_rows(rows: Sequence[tuple[str, str]]) -> str:
    """Lines up labels and values in two columns for a run's printed summary."""
    width = max(len(label) for label, _ in rows)

    return "\n".join(f"{label:<{width}}  {value}".rstrip() for label, value in rows)


def stop(command: str, reason: object) -> int:
    """Prints why a run stopped and returns the process exit code."""
    print(f"{command} stopped: {reason}", file=sys.stderr)

    return 1
