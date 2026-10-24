## Before any work in this directory

1. Plans must go into the [`docs/plans/`](docs/plans/) and specs must go into [`docs/specs/`](docs/specs/)
2. Read the slice spec for what you're working on, under [`docs/specs/`](docs/specs/).
3. Skim [`docs/`](docs/) for the architecture and failure-mode documents that anchor the design.

## Index

| Document | What it covers |
|---|---|
| [`docs/design-doc.html`](docs/design-doc.html) | Architecture: layers, constraints, decisions, build order, open questions |
| [`docs/tech-stack.md`](docs/tech-stack.md) | Every tool, its purpose, and what was rejected. Living: update it when a tool changes. |
| [`docs/project-structure.md`](docs/project-structure.md) | Folder layout, import direction, test layout. Living: update it when the tree moves. |
| [`docs/adrs/`](docs/adrs/) | Architectural decision records |
| [`docs/specs/`](docs/specs/) | Slice specs (dated) |
| [`docs/plans/`](docs/plans/) | Implementation plans (dated) |

**Paths in dated documents are as-of their date.** Everything under [`docs/specs/`](docs/specs/) and [`docs/plans/`](docs/plans/) is a record of a slice as it was designed and executed, so file paths there are whatever was true then — they aren't updated when the tree moves.