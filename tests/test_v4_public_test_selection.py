"""Public-test discovery & opt-in image settings (no Docker or LLM calls)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.swebench.current.public_test_selection import select_public_tests
from evaluation.swebench.current.public_test_config import (
    load_public_test_images, preflight_public_test_images,
)


@pytest.fixture
def project(tmp_path):
    for folder in ('pkg/widgets', 'pkg/widgets/tests', 'tests', 'other/tests'):
        (tmp_path / folder).mkdir(parents=True)
    (tmp_path / 'pkg/widgets/parser.py').write_text('def parse(): return 1\n')
    (tmp_path / 'pkg/widgets/tests/test_parser.py').write_text('def test_a(): pass\n')
    (tmp_path / 'tests/test_parser.py').write_text('def test_b(): pass\n')
    (tmp_path / 'other/tests/test_unrelated.py').write_text('def test_c(): pass\n')
    return tmp_path


def test_find_only_exact_existing_named_tests(project):
    found = select_public_tests(project, 'pkg/widgets/parser.py')
    assert found == ['pkg/widgets/tests/test_parser.py', 'tests/test_parser.py']
    assert all(Path(project / x).is_file() for x in found)


def test_no_match_reports_empty(project):
    (project / 'pkg/widgets/unsupported.py').write_text('pass\n')
    assert select_public_tests(project, 'pkg/widgets/unsupported.py') == []


def test_limit_is_respected(project):
    assert len(select_public_tests(project, 'pkg/widgets/parser.py', max_targets=1)) == 1


@pytest.mark.parametrize('source', ['../outside.py', '/etc/passwd', '', 'tests/test_nonexistent.py'])
def test_reject_outside_or_missing_source(project, source):
    with pytest.raises(ValueError):
        select_public_tests(project, source)


def test_symlink_test_outside_skipped(project, tmp_path):
    outside = tmp_path.parent / 'test_parser.py'
    outside.write_text('def test_bad(): pass\n')
    (project / 'pkg/widgets/tests/test_parser.py').unlink()
    (project / 'pkg/widgets/tests/test_parser.py').symlink_to(outside)
    assert select_public_tests(project, 'pkg/widgets/parser.py') == ['tests/test_parser.py']


def test_safe_large_tree_limit(project, monkeypatch):
    import evaluation.swebench.current.public_test_selection as selector
    monkeypatch.setattr(selector, '_MAX_VISITED_FILES', 1)
    assert select_public_tests(project, 'pkg/widgets/parser.py') == []


def test_load_manifest(tmp_path):
    path = tmp_path / 'public_images.json'
    path.write_text(json.dumps({'schema_version': 1, 'images': {
        'sympy/sympy': 'bugpilot-public-tests:sympy-local',
    }}))
    assert load_public_test_images(path)['sympy/sympy'] == 'bugpilot-public-tests:sympy-local'


@pytest.mark.parametrize('payload', [
    {'schema_version': 1, 'images': {}, 'test_patch': 'malicious'},
    {'schema_version': 2, 'images': {}},
    {'schema_version': 1, 'images': {'sympy/sympy': 'alpine:latest'}},
    {'schema_version': 1, 'images': {'../outside': 'bugpilot-public-tests:test'}},
    {'schema_version': 1, 'images': ['unexpected']},
])
def test_reject_untrusted_manifest_shape(tmp_path, payload):
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_public_test_images(path)


def test_preflight_does_not_pull_images(monkeypatch):
    import sys
    checked = []
    def get(image):
        checked.append(image)
    fake = SimpleNamespace(from_env=lambda: SimpleNamespace(
        ping=lambda: True, images=SimpleNamespace(get=get),
    ))
    monkeypatch.setitem(sys.modules, 'docker', fake)
    preflight_public_test_images({'sympy/sympy': 'bugpilot-public-tests:local'})
    assert checked == ['bugpilot-public-tests:local']
