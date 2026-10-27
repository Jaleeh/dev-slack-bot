"""Search failures, each worded so the model can act on it."""


class SearchError(Exception):
    pass


class PathOutsideRepo(SearchError):
    def __init__(self, path: str) -> None:
        super().__init__(f"{path} is outside the repository; use a path relative to its root")
        self.path = path


class PathNotFound(SearchError):
    def __init__(self, path: str) -> None:
        super().__init__(f"no such file or folder: {path}; try list_files on its parent folder")
        self.path = path


class NotAFolder(SearchError):
    def __init__(self, path: str) -> None:
        super().__init__(f"{path} is a file, not a folder; use read_file or outline on it")
        self.path = path


class BadPattern(SearchError):
    def __init__(self, pattern: str, reason: str) -> None:
        super().__init__(f"bad pattern {pattern!r}: {reason}; fix the regex and try again")
        self.pattern = pattern
        self.reason = reason


class BadLineRange(SearchError):
    def __init__(self, path: str, start_line: int, end_line: int, line_count: int) -> None:
        if line_count == 0:
            reason = "the file is empty"
        elif end_line < start_line:
            reason = "the end line is before the start line"
        else:
            reason = f"it has {line_count} lines"

        super().__init__(f"cannot read lines {start_line}-{end_line} of {path}: {reason}")
        self.path = path
        self.start_line = start_line
        self.end_line = end_line
        self.line_count = line_count


class CannotOutline(SearchError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"cannot outline {path}: {reason}; use read_file instead")
        self.path = path
        self.reason = reason


class NotText(SearchError):
    def __init__(self, path: str) -> None:
        super().__init__(f"{path} is binary or cannot be read, so it can't be shown")
        self.path = path
