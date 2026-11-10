"""Test optional public-test wiring without Docker or LLM calls."""
import ast
from pathlib import Path

import pytest

from evaluation.swebench.current import public_test_verifier


class FakeIssueInvestigationError(Exception):
    def __init__(self, message, **kwargs):
        super().__init__(message)
        self.stop_reason = kwargs.get('stop_reason')
        self.details = kwargs.get('details', {})
        self.usage = kwargs.get('usage', {})


@pytest.fixture
def harness(tmp_path):
    repo = tmp_path / 'repo'
    (repo / 'tests').mkdir(parents=True)
    (repo / 'tests' / 'test_public.py').write_text('def test_public(): pass\n')

    source_path = Path('evaluation/swebench/current/agent_adapter.py')
    tree = ast.parse(source_path.read_text(encoding='utf-8'))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'solve_issue']
    assert len(functions) == 1

    calls, rollbacks = [], []

    def diagnose_issue(problem, repository_path, **kwargs):
        calls.append(problem)
        return {
            'file_path': 'package/module.py',
            'function_name': 'fix',
            'usage': {'input_tokens': 5},
            'tool_trace': [],
        }

    def apply_issue_fix(repository_path, result):
        return {'file_path': 'package/module.py'}

    def verify_issue_patch(repository_path, result):
        return {'passed': True, 'reason': 'local_checks_passed'}

    ns = {
        'Path': Path,
        'IssueInvestigationError': FakeIssueInvestigationError,
        'diagnose_issue': diagnose_issue,
        'apply_issue_fix': apply_issue_fix,
        'verify_issue_patch': verify_issue_patch,
        '_rollback_issue_patch': lambda repository_path, relative_path: rollbacks.append(relative_path),
        '_merge_usage': lambda a, b: {
            k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)
        },
    }
    isolated = ast.Module(body=functions, type_ignores=[])
    exec(compile(ast.fix_missing_locations(isolated), str(source_path), 'exec'), ns)
    return ns['solve_issue'], repo, calls, rollbacks


def test_disabled_default_keeps_existing_behavior(harness, monkeypatch):
    solve, repo, calls, rollback = harness
    monkeypatch.setattr(public_test_verifier, 'run_public_tests',
                        lambda *a, **kw: pytest.fail('should not invoke public tests'))
    result = solve(repo, 'An issue report')
    assert result['verification']['passed'] is True
    assert 'public_tests' not in result['verification']
    assert len(calls) == 1 and not rollback


def test_public_test_pass_allows_patch(harness, monkeypatch):
    solve, repo, calls, rollback = harness
    monkeypatch.setattr(public_test_verifier, 'run_public_tests',
                        lambda *a, **kw: {'status': 'passed', 'reason': 'public_tests_passed'})
    result = solve(repo, 'An issue report', public_test_targets=['tests/test_public.py'],
                   public_test_image='bugpilot-public-tests:unit')
    assert result['verification']['passed'] is True
    assert result['verification']['public_tests']['status'] == 'passed'
    assert len(calls) == 1 and not rollback


def test_public_test_failure_retries_with_feedback(harness, monkeypatch):
    solve, repo, calls, rollbacks = harness
    outcomes = iter([
        {'status': 'failed', 'reason': 'public_tests_failed', 'feedback': '1 failed'},
        {'status': 'passed', 'reason': 'public_tests_passed', 'feedback': '1 passed'},
    ])
    monkeypatch.setattr(public_test_verifier, 'run_public_tests', lambda *a, **kw: next(outcomes))
    result = solve(repo, 'An issue report', public_test_targets=['tests/test_public.py'],
                   public_test_image='bugpilot-public-tests:unit')
    assert result['verification']['passed'] is True
    assert len(calls) == 2
    assert '1 failed' in calls[1]
    assert rollbacks == ['package/module.py']


def test_infrastructure_error_rolls_back_and_aborts(harness, monkeypatch):
    solve, repo, calls, rollbacks = harness
    monkeypatch.setattr(public_test_verifier, 'run_public_tests',
                        lambda *a, **kw: {'status': 'infrastructure_error',
                                          'reason': 'missing_image', 'feedback': 'not found'})
    with pytest.raises(FakeIssueInvestigationError) as exc:
        solve(repo, 'An issue report', public_test_targets=['tests/test_public.py'],
              public_test_image='bugpilot-public-tests:unit')
    assert exc.value.stop_reason == 'public_test_infrastructure_error'
    assert len(calls) == 1
    assert rollbacks == ['package/module.py']


def test_misconfigured_mode_rejected_before_model_call(harness):
    solve, repo, calls, rollbacks = harness
    with pytest.raises(ValueError):
        solve(repo, 'issue', public_test_targets=['tests/test_public.py'])
    with pytest.raises(ValueError):
        solve(repo, 'issue', public_test_image='bugpilot-public-tests:unit')
    with pytest.raises(ValueError):
        solve(repo, 'issue', public_test_targets=['tests/nonexistent.py'],
              public_test_image='bugpilot-public-tests:unit')
    assert not calls and not rollbacks


def test_auto_selection_uses_changed_public_source_only(harness, monkeypatch):
    solve, repo, calls, rollbacks = harness
    (repo / 'package').mkdir()
    (repo / 'package/module.py').write_text('def fix(): pass\n')
    (repo / 'tests/test_module.py').write_text('def test_fix(): pass\n')
    seen = []
    def simulate(repo_path, targets, **kwargs):
        seen.append(targets)
        return {'status': 'passed', 'reason': 'public_tests_passed', 'test_targets': targets}
    monkeypatch.setattr(public_test_verifier, 'run_public_tests', simulate)
    result = solve(repo, 'public issue', public_test_image='bugpilot-public-tests:unit',
                   auto_select_public_tests=True)
    assert result['verification']['public_tests']['status'] == 'passed'
    assert seen == [['tests/test_module.py']]
    assert len(calls) == 1 and rollbacks == []


def test_auto_selection_does_not_claim_tests_passed_when_none_found(harness, monkeypatch):
    solve, repo, calls, rollbacks = harness
    (repo / 'package').mkdir()
    (repo / 'package/module.py').write_text('def fix(): pass\n')
    monkeypatch.setattr(public_test_verifier, 'run_public_tests',
                        lambda *a, **kw: pytest.fail('should skip missing tests'))
    result = solve(repo, 'issue', public_test_image='bugpilot-public-tests:unit',
                   auto_select_public_tests=True)
    assert result['verification']['public_tests']['status'] == 'skipped'
    assert len(calls) == 1 and rollbacks == []


def test_auto_selection_invalid_combination_rejected_before_model_call(harness):
    solve, repo, calls, _ = harness
    with pytest.raises(ValueError):
        solve(repo, 'issue', auto_select_public_tests=True)
    with pytest.raises(ValueError):
        solve(repo, 'issue', auto_select_public_tests=True,
              public_test_targets=['tests/test_public.py'],
              public_test_image='bugpilot-public-tests:unit')
    assert not calls
