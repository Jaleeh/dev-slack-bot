from pathlib import Path

import pytest

from app.retrieval.direct.scope import open_scope
from app.retrieval.direct.search import DirectSearch

BASKET = '''"""Basket rules."""

class Basket:
    def merge(self, other):
        merge_lines = other.lines
        return merge_lines

def apply_voucher(basket):
    return basket
'''

OFFER = """// Offers can stack with a voucher.
export class Offer {
  apply(total: number): number {
    return total
  }
}
"""

LONG_FILE_LINES = 450


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A small repository with code, docs, noise, a binary, and symlinks to hidden places."""
    root = tmp_path / "repo"
    files = {
        ".gitignore": "build/\n",
        "src/shop/basket.py": BASKET,
        "src/shop/offer.ts": OFFER,
        "src/shop/long.py": "".join(f"line {n}\n" for n in range(1, LONG_FILE_LINES + 1)),
        "src/shop/migrations/0001.py": "# voucher table\n",
        "docs/vouchers.md": "Vouchers apply after offers.\n",
        "build/out.py": "voucher = 1\n",
        "node_modules/lib/index.js": "const voucher = 1\n",
        ".git/config": "url = https://token@example.com/voucher\n",
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)

    (root / "assets").mkdir()
    (root / "assets/logo.png").write_bytes(b"\x89PNG\x00voucher")

    secret = tmp_path / "outside/secret.txt"
    secret.parent.mkdir()
    secret.write_text("voucher secret\n")
    (root / "docs/link.txt").symlink_to(secret)
    (root / "docs/built.py").symlink_to(root / "build/out.py")
    (root / "docs/gitconfig").symlink_to(root / ".git/config")

    return root


@pytest.fixture
def search(repo: Path) -> DirectSearch:
    return DirectSearch(open_scope(repo))
