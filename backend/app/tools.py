import ast
import os
import re
from pathlib import Path


# Directories that should never be searched by the debugging agent.
IGNORED_DIRS = {
    ".git",
    "venv",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "htmlcov",
    "build",
    "dist",
}

IGNORED_FILES = {
    ".DS_Store",
    ".coverage",
}

SEARCHABLE_EXTENSIONS = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
}

MAX_SEARCH_FILE_BYTES = 1_000_000
MAX_RANKED_MATCHES = 2_000


def _repo_root(base_dir: str) -> Path:
    """Return the absolute repository root."""
    return Path(base_dir).resolve()


def _safe_path(
    base_dir: str,
    relative_path: str = ".",
) -> Path:
    """
    Resolve a path and ensure it stays inside base_dir.

    This prevents tools from reading or writing files outside the repository
    using paths such as ../../secret.txt.
    """
    root = _repo_root(base_dir)
    candidate = (
        root
        / relative_path
    ).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            f"Path '{relative_path}' "
            "is outside the repository."
        ) from exc

    return candidate


def _should_ignore(
    path: Path,
    root: Path,
) -> bool:
    """Return True when a path belongs to an ignored directory/file."""
    try:
        relative = path.relative_to(
            root
        )
    except ValueError:
        return True

    if (
        path.name in IGNORED_FILES
        or path.name.startswith(
            ".coverage."
        )
    ):
        return True

    return any(
        part in IGNORED_DIRS
        for part in relative.parts
    )


def _iter_repository_files(
    base_dir: str,
    start_path: str = ".",
):
    """
    Yield (absolute_path, repository_relative_path) for repository files.

    Generated dependency/cache directories are skipped automatically.
    Symlinks are not followed.
    """
    root = _repo_root(
        base_dir
    )
    start = _safe_path(
        base_dir,
        start_path,
    )

    if start.is_file():
        if not _should_ignore(
            start,
            root,
        ):
            yield (
                start,
                start.relative_to(
                    root
                ).as_posix(),
            )
        return

    if not start.exists():
        raise FileNotFoundError(
            f"Path '{start_path}' "
            "does not exist."
        )

    if not start.is_dir():
        raise ValueError(
            f"Path '{start_path}' "
            "is not a directory."
        )

    for (
        current_dir,
        dirnames,
        filenames,
    ) in os.walk(
        start,
        followlinks=False,
    ):
        current = Path(
            current_dir
        )

        dirnames[:] = [
            name
            for name in dirnames
            if (
                name
                not in IGNORED_DIRS
                and not (
                    current
                    / name
                ).is_symlink()
            )
        ]

        for filename in filenames:
            file_path = (
                current
                / filename
            )

            if file_path.is_symlink():
                continue

            if _should_ignore(
                file_path,
                root,
            ):
                continue

            yield (
                file_path,
                file_path.relative_to(
                    root
                ).as_posix(),
            )


def _is_test_path(
    relative_path: str,
) -> bool:
    path = Path(
        relative_path
    )

    parts = {
        part.lower()
        for part in path.parts[:-1]
    }

    filename = (
        path.name.lower()
    )

    return (
        "tests" in parts
        or "test" in parts
        or filename.startswith(
            "test_"
        )
        or filename.endswith(
            "_test.py"
        )
    )


def _is_documentation_path(
    relative_path: str,
) -> bool:
    path = Path(
        relative_path
    )

    parts = {
        part.lower()
        for part in path.parts
    }

    return bool(
        {
            "docs",
            "doc",
            "documentation",
        }
        & parts
    )


def read_file(
    filepath: str,
    base_dir: str,
) -> str:
    """
    Read a complete text file inside the repository.

    This function remains compatible with the existing BugPilot patching code.
    """
    full_path = _safe_path(
        base_dir,
        filepath,
    )

    if not full_path.exists():
        raise FileNotFoundError(
            f"File '{filepath}' "
            "does not exist."
        )

    if not full_path.is_file():
        raise ValueError(
            f"'{filepath}' "
            "is not a file."
        )

    with open(
        full_path,
        "r",
        encoding="utf-8",
        errors="replace",
    ) as file:
        return file.read()


def read_file_range(
    filepath: str,
    base_dir: str,
    start_line: int = 1,
    end_line: int | None = None,
    max_lines: int = 250,
) -> str:
    """
    Read a bounded line range from a repository file.

    Returned lines include line numbers so the agent can reason about exact
    source locations without loading an entire large file into context.
    """
    if start_line < 1:
        raise ValueError(
            "start_line must be >= 1."
        )

    full_path = _safe_path(
        base_dir,
        filepath,
    )

    if not full_path.exists():
        raise FileNotFoundError(
            f"File '{filepath}' "
            "does not exist."
        )

    if not full_path.is_file():
        raise ValueError(
            f"'{filepath}' "
            "is not a file."
        )

    with open(
        full_path,
        "r",
        encoding="utf-8",
        errors="replace",
    ) as file:
        lines = file.readlines()

    if end_line is None:
        end_line = min(
            len(lines),
            start_line
            + max_lines
            - 1,
        )
    else:
        end_line = min(
            end_line,
            start_line
            + max_lines
            - 1,
            len(lines),
        )

    if start_line > len(
        lines
    ):
        return (
            "File has only "
            f"{len(lines)} lines."
        )

    selected = lines[
        start_line - 1:
        end_line
    ]

    return "".join(
        f"{line_number:>5}: "
        f"{line}"
        for (
            line_number,
            line,
        ) in enumerate(
            selected,
            start=start_line,
        )
    )


def write_file(
    filepath: str,
    new_contents: str,
    base_dir: str,
) -> None:
    """Overwrite an existing repository file with new contents."""
    full_path = _safe_path(
        base_dir,
        filepath,
    )

    if not full_path.exists():
        raise FileNotFoundError(
            f"File '{filepath}' "
            "does not exist."
        )

    if not full_path.is_file():
        raise ValueError(
            f"'{filepath}' "
            "is not a file."
        )

    with open(
        full_path,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(
            new_contents
        )


def list_directory(
    base_dir: str,
    path: str = ".",
    recursive: bool = False,
    max_depth: int = 2,
    max_entries: int = 200,
):
    """
    List repository files/directories.

    With recursive=False, lists one directory level.
    With recursive=True, returns a bounded repository tree.

    Paths are always returned relative to base_dir.
    """
    root = _repo_root(
        base_dir
    )
    target = _safe_path(
        base_dir,
        path,
    )

    if not target.exists():
        raise FileNotFoundError(
            f"Path '{path}' "
            "does not exist."
        )

    if not target.is_dir():
        raise ValueError(
            f"'{path}' "
            "is not a directory."
        )

    entries = []

    if not recursive:
        for item in sorted(
            target.iterdir(),
            key=lambda candidate: (
                candidate.name.lower()
            ),
        ):
            if (
                item.is_symlink()
                or _should_ignore(
                    item,
                    root,
                )
            ):
                continue

            relative = (
                item.relative_to(
                    root
                ).as_posix()
            )

            if item.is_dir():
                relative += "/"

            entries.append(
                relative
            )

            if len(
                entries
            ) >= max_entries:
                break

        return entries

    for (
        current_dir,
        dirnames,
        filenames,
    ) in os.walk(
        target,
        followlinks=False,
    ):
        current = Path(
            current_dir
        )

        depth = len(
            current.relative_to(
                target
            ).parts
        )

        dirnames[:] = [
            name
            for name in sorted(
                dirnames
            )
            if (
                name
                not in IGNORED_DIRS
                and not (
                    current
                    / name
                ).is_symlink()
            )
        ]

        if depth >= max_depth:
            dirnames[:] = []

        for dirname in dirnames:
            directory = (
                current
                / dirname
            )

            if _should_ignore(
                directory,
                root,
            ):
                continue

            entries.append(
                directory.relative_to(
                    root
                ).as_posix()
                + "/"
            )

            if len(
                entries
            ) >= max_entries:
                return entries

        for filename in sorted(
            filenames
        ):
            file_path = (
                current
                / filename
            )

            if (
                file_path.is_symlink()
                or _should_ignore(
                    file_path,
                    root,
                )
            ):
                continue

            entries.append(
                file_path.relative_to(
                    root
                ).as_posix()
            )

            if len(
                entries
            ) >= max_entries:
                return entries

    return entries


def _search_match_score(
    keyword: str,
    relative_path: str,
    line_text: str,
) -> int:
    keyword_lower = (
        keyword.lower()
    )
    path_lower = (
        relative_path.lower()
    )
    line_lower = (
        line_text.lower()
    )

    suffix = Path(
        relative_path
    ).suffix.lower()

    score = 0

    if suffix in SOURCE_EXTENSIONS:
        score += 8
    else:
        score += 2

    if _is_test_path(
        relative_path
    ):
        score -= 4

    if _is_documentation_path(
        relative_path
    ):
        score -= 5

    stem = Path(
        relative_path
    ).stem.lower()

    if keyword_lower in stem:
        score += 8

    if keyword_lower in path_lower:
        score += 4

    identifier_pattern = re.compile(
        r"(?<![A-Za-z0-9_])"
        + re.escape(
            keyword_lower
        )
        + r"(?![A-Za-z0-9_])"
    )

    if identifier_pattern.search(
        line_lower
    ):
        score += 10
    else:
        score += 4

    stripped = (
        line_lower.strip()
    )

    if (
        stripped.startswith(
            "def "
        )
        or stripped.startswith(
            "async def "
        )
        or stripped.startswith(
            "class "
        )
    ):
        score += 6

    return score


def search_code(
    base_dir: str,
    keyword: str,
    path: str = ".",
    max_results: int = 50,
):
    """
    Recursively search repository source/text files for a keyword.

    Results are ranked so likely implementation matches appear before
    documentation/test-only matches.

    The public return shape remains backwards-compatible.
    """
    keyword = (
        keyword.strip()
    )

    if not keyword:
        raise ValueError(
            "Search keyword "
            "cannot be empty."
        )

    ranked_matches = []

    for (
        file_path,
        relative_path,
    ) in _iter_repository_files(
        base_dir,
        path,
    ):
        if (
            file_path.suffix.lower()
            not in SEARCHABLE_EXTENSIONS
        ):
            continue

        try:
            if (
                file_path.stat().st_size
                > MAX_SEARCH_FILE_BYTES
            ):
                continue
        except OSError:
            continue

        try:
            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore",
            ) as file:
                for (
                    line_number,
                    line,
                ) in enumerate(
                    file,
                    start=1,
                ):
                    if (
                        keyword.lower()
                        not in line.lower()
                    ):
                        continue

                    line_text = (
                        line.strip()
                    )

                    score = (
                        _search_match_score(
                            keyword,
                            relative_path,
                            line_text,
                        )
                    )

                    ranked_matches.append(
                        (
                            -score,
                            relative_path,
                            line_number,
                            {
                                "file": (
                                    relative_path
                                ),
                                "line_number": (
                                    line_number
                                ),
                                "line_text": (
                                    line_text
                                ),
                            },
                        )
                    )

                    if (
                        len(
                            ranked_matches
                        )
                        >= MAX_RANKED_MATCHES
                    ):
                        break

        except (
            OSError,
            UnicodeError,
        ):
            continue

        if (
            len(
                ranked_matches
            )
            >= MAX_RANKED_MATCHES
        ):
            break

    ranked_matches.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
        )
    )

    return [
        item[3]
        for item in ranked_matches[
            :max_results
        ]
    ]


def rank_repository_files(
    base_dir: str,
    terms,
    path: str = ".",
    max_files: int = 10,
    max_samples_per_file: int = 3,
):
    """
    Rank likely implementation files for a collection of public issue terms.

    This helper performs one repository scan and is intended for automatic
    pre-localization before the LLM begins tool-driven investigation.

    It uses repository contents plus caller-provided terms only.
    """

    if not isinstance(
        terms,
        (
            list,
            tuple,
        ),
    ):
        raise ValueError(
            "terms must be a list "
            "or tuple."
        )

    normalized_terms = []

    for term in terms:
        if not isinstance(
            term,
            str,
        ):
            continue

        cleaned = (
            term.strip()
        )

        if len(
            cleaned
        ) < 2:
            continue

        lowered = (
            cleaned.lower()
        )

        if lowered not in {
            existing.lower()
            for existing
            in normalized_terms
        }:
            normalized_terms.append(
                cleaned
            )

        if len(
            normalized_terms
        ) >= 16:
            break

    if not normalized_terms:
        return []

    candidates = []

    for (
        file_path,
        relative_path,
    ) in _iter_repository_files(
        base_dir,
        path,
    ):
        suffix = (
            file_path.suffix.lower()
        )

        if (
            suffix
            not in SEARCHABLE_EXTENSIONS
        ):
            continue

        try:
            if (
                file_path.stat().st_size
                > MAX_SEARCH_FILE_BYTES
            ):
                continue

            source = (
                file_path.read_text(
                    encoding="utf-8",
                    errors="ignore",
                )
            )
        except (
            OSError,
            UnicodeError,
        ):
            continue

        relative_lower = (
            relative_path.lower()
        )
        lines = (
            source.splitlines()
        )

        score = 0
        matched_terms = set()
        samples = []

        if suffix in SOURCE_EXTENSIONS:
            score += 8
        else:
            score += 1

        if _is_test_path(
            relative_path
        ):
            score -= 5

        if _is_documentation_path(
            relative_path
        ):
            score -= 6

        for term_index, term in enumerate(
            normalized_terms
        ):
            term_lower = (
                term.lower()
            )

            term_weight = max(
                2,
                10 - term_index,
            )

            if (
                term_lower
                in relative_lower
            ):
                score += (
                    term_weight
                    + 6
                )
                matched_terms.add(
                    term_lower
                )

            term_hit_count = 0

            for (
                line_number,
                line,
            ) in enumerate(
                lines,
                start=1,
            ):
                line_lower = (
                    line.lower()
                )

                if (
                    term_lower
                    not in line_lower
                ):
                    continue

                term_hit_count += 1
                matched_terms.add(
                    term_lower
                )

                match_score = (
                    _search_match_score(
                        term,
                        relative_path,
                        line,
                    )
                )

                score += (
                    term_weight
                    + min(
                        match_score,
                        16,
                    )
                )

                if (
                    len(samples)
                    < max_samples_per_file
                ):
                    samples.append(
                        {
                            "term": term,
                            "line_number": (
                                line_number
                            ),
                            "line_text": (
                                line.strip()
                            ),
                        }
                    )

                if (
                    term_hit_count
                    >= 4
                ):
                    break

        if not matched_terms:
            continue

        score += (
            len(
                matched_terms
            )
            * 5
        )

        candidates.append(
            {
                "file": (
                    relative_path
                ),
                "score": score,
                "matched_terms": sorted(
                    matched_terms
                ),
                "matches": samples,
            }
        )

    candidates.sort(
        key=lambda item: (
            -item["score"],
            item["file"],
        )
    )

    return candidates[
        :max_files
    ]


class _FunctionFinder(
    ast.NodeVisitor
):
    """AST visitor used to locate functions and class methods."""

    def __init__(
        self,
        target_name: str,
    ):
        self.target_name = (
            target_name
        )
        self.class_stack = []
        self.matches = []

    def visit_ClassDef(
        self,
        node,
    ):
        self.class_stack.append(
            node.name
        )
        self.generic_visit(
            node
        )
        self.class_stack.pop()

    def _record_function(
        self,
        node,
    ):
        if (
            node.name
            == self.target_name
        ):
            if self.class_stack:
                qualified_name = ".".join(
                    self.class_stack
                    + [
                        node.name
                    ]
                )
            else:
                qualified_name = (
                    node.name
                )

            self.matches.append(
                {
                    "qualified_name": (
                        qualified_name
                    ),
                    "line_number": (
                        node.lineno
                    ),
                }
            )

        self.generic_visit(
            node
        )

    def visit_FunctionDef(
        self,
        node,
    ):
        self._record_function(
            node
        )

    def visit_AsyncFunctionDef(
        self,
        node,
    ):
        self._record_function(
            node
        )


def get_function_signature(
    base_dir: str,
    function_name: str,
    path: str = ".",
):
    """
    Find functions/methods by name recursively using Python's AST.

    This discovers functions inside nested packages and methods defined
    inside classes.
    """
    found = []

    for (
        file_path,
        relative_path,
    ) in _iter_repository_files(
        base_dir,
        path,
    ):
        if (
            file_path.suffix
            != ".py"
        ):
            continue

        try:
            source = (
                file_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            )
            tree = ast.parse(
                source
            )
        except (
            OSError,
            SyntaxError,
            UnicodeError,
        ):
            continue

        finder = (
            _FunctionFinder(
                function_name
            )
        )
        finder.visit(
            tree
        )

        source_lines = (
            source.splitlines()
        )

        for match in finder.matches:
            line_number = (
                match[
                    "line_number"
                ]
            )

            signature_line = (
                source_lines[
                    line_number - 1
                ].strip()
                if (
                    0
                    < line_number
                    <= len(
                        source_lines
                    )
                )
                else ""
            )

            found.append(
                f"{relative_path}:"
                f"{line_number}: "
                f"{match['qualified_name']}"
                " -> "
                f"{signature_line}"
            )

    if not found:
        return (
            f"Function "
            f"'{function_name}' "
            "not found."
        )

    return "\n".join(
        found
    )


def detect_requirements(
    base_dir: str,
):
    """
    Detect the repository's Python dependency configuration.

    Returns an install command or None.
    """
    root = _repo_root(
        base_dir
    )

    if (
        root
        / "requirements.txt"
    ).exists():
        return (
            "pip install "
            "-r requirements.txt"
        )

    if (
        root
        / "pyproject.toml"
    ).exists():
        return "pip install ."

    if (
        root
        / "setup.py"
    ).exists():
        return "pip install ."

    return None
