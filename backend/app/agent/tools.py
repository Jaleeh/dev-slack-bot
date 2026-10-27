"""The search tools as LangChain tools, described for the model."""

from langchain_core.tools import StructuredTool

from app.retrieval.direct.search import MAX_READ_LINES, DirectSearch


def search_tools(search: DirectSearch) -> tuple[StructuredTool, ...]:
    described = (
        (
            search.list_files,
            "List the files and folders directly inside a folder. "
            "Paths are relative to the repository root, which is '.'.",
        ),
        (
            search.grep,
            "Search every text file under a path for a case-insensitive regular expression. "
            "Hits are grouped by file, each with one line of context.",
        ),
        (
            search.read_file,
            f"Read numbered lines of a file, at most {MAX_READ_LINES} per call. Lines start at 1.",
        ),
        (search.outline, "List a file's classes, functions and methods with their line numbers."),
    )

    return tuple(
        StructuredTool.from_function(method, description=description)
        for method, description in described
    )
