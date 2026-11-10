"""Conservative, no-oracle discovery of pre-existing public pytest test files.

Only the proposed *source path* and the public repository checkout are inspected.
SWE-bench dataset tests, gold patches and oracle targets are never inputs.
A missing match is reported as unverified; it must not be treated as a pass.
"""

from __future__ import annotations

import os
from pathlib import Path

from .public_test_verifier import _validate_test_targets

_SKIP_DIRS = frozenset({
    '.git', '.tox', '.venv', 'venv', 'node_modules', 'build', 'dist',
    '__pycache__', '.mypy_cache', '.pytest_cache', '.nox',
})
_MAX_VISITED_FILES = 30000


def select_public_tests(repository_path, changed_file, *, max_targets=3):
    """Find only exact conventional pytest filename matches for a source module.

    Returns [] if no reliable existing test file matches. No model input, issue
    text, hidden test metadata, or shell command is used for selection.
    """
    root = Path(repository_path).resolve()
    if not root.is_dir():
        raise ValueError('Missing repository')
    if not isinstance(changed_file, str) or not changed_file or '\x00' in changed_file:
        raise ValueError('Invalid changed source path')
    source = (root / changed_file).resolve()
    if not source.is_relative_to(root) or not source.is_file() or source.suffix != '.py':
        raise ValueError('Source must be an existing Python file in checkout')
    if type(max_targets) is not int or not 1 <= max_targets <= 8:
        raise ValueError('max_targets must be between 1 and 8')

    stem = source.stem
    if stem in {'__init__', '__main__', 'conftest', 'setup'}:
        return []
    names = {f'test_{stem}.py', f'{stem}_test.py'}
    matching = []
    visited = 0
    rel_source = source.relative_to(root)
    source_parts = set(rel_source.parts[:-1])

    for directory, subdirs, filenames in os.walk(root, followlinks=False):
        subdirs[:] = sorted(d for d in subdirs if d not in _SKIP_DIRS and not d.startswith('.'))
        filenames = sorted(filenames)
        visited += len(filenames)
        if visited > _MAX_VISITED_FILES:
            # Do not silently select an arbitrary subset of a very large tree.
            return []
        for name in filenames:
            if name not in names:
                continue
            test_file = Path(directory) / name
            if test_file.is_symlink() or not test_file.is_file():
                continue
            relative = test_file.relative_to(root)
            # Must live within a tests or test directory, or beside source
            # with the conventional pytest test_*.py naming scheme.
            if not ({'tests', 'test'} & set(relative.parts[:-1])) and test_file.parent != source.parent:
                continue
            candidate = relative.as_posix()
            try:
                _validate_test_targets(root, [candidate])
            except ValueError:
                continue
            test_parts = set(relative.parts[:-1])
            common = len(source_parts & test_parts)
            near_source = int(test_file.parent == source.parent)
            score = common * 10 + near_source * 5
            matching.append((-score, candidate))

    matching.sort()
    return [path for _, path in matching[:max_targets]]
