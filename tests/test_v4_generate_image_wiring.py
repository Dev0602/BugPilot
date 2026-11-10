"""Test prediction-generation routing without SWE-bench, Claude, or Docker."""

import ast
import json
from pathlib import Path
from types import SimpleNamespace


def _load_generate(tmp_path, *, images):
    source_path = Path('evaluation/swebench/current/generate.py')
    tree = ast.parse(source_path.read_text(encoding='utf-8'))
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate']
    assert len(functions) == 1
    calls, preflights = [], []
    repo = tmp_path / 'checkout'
    repo.mkdir()
    selected = [
        SimpleNamespace(instance_id='sympy__sample-1', repo='sympy/sympy', base_commit='abc',
                        problem_statement='public issue 1'),
        SimpleNamespace(instance_id='flask__sample-2', repo='pallets/flask', base_commit='def',
                        problem_statement='public issue 2'),
    ]

    def solver(path, issue, **options):
        calls.append((issue, options))
        return {'usage': {'input_tokens': 1}, 'file_path': 'pkg/mod.py',
                'verification': {'public_tests': {'status': 'skipped' if options else 'disabled',
                    'test_targets': []}}}

    def write_json(path, value):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(value))

    ns = {
        'Path': Path, 'MODEL': 'fixture', 'solve_issue': lambda *a, **kw: None, 'DEFAULT_DATASET': 'unused',
        'load_swebench_dataset': lambda *args: [],
        'deterministic_subset': lambda *args, **kwargs: selected,
        'public_instance_dict': lambda item: {'instance_id': item.instance_id},
        'write_json': write_json,
        'prepare_repository': lambda *args: {'path': str(repo)},
        'collect_model_patch': lambda *args, **kwargs: 'diff --git a/pkg/mod.py b/pkg/mod.py',
        'build_prediction': lambda item, patch, model_name: {'instance_id': item.instance_id},
        'write_predictions': lambda values, path: write_json(path, values),
        'preflight_public_test_images': lambda selected_images: preflights.append(selected_images),
        '_record_generation_failure': lambda outcome, exc: outcome.update(status='generation_failed', error=str(exc)),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source_path), 'exec'), ns)
    return ns['generate'], solver, calls, preflights


def test_configured_repo_only_receives_public_test_options(tmp_path):
    images = {'sympy/sympy': 'bugpilot-public-tests:sympy-dev'}
    generate, solver, calls, preflights = _load_generate(tmp_path, images=images)
    result = generate(dataset_name='fixture', split='test', count=2, seed='seed',
                      output_dir=tmp_path / 'results', solver=solver, public_test_images=images)
    assert preflights == [images]
    assert calls[0][1] == {'public_test_image': images['sympy/sympy'],
                           'auto_select_public_tests': True}
    assert calls[1][1] == {}
    assert [item['public_test_status'] for item in result['results']] == ['skipped', 'disabled']


def test_disabled_mode_needs_no_images(tmp_path):
    generate, solver, calls, preflights = _load_generate(tmp_path, images={})
    result = generate(dataset_name='fixture', split='test', count=2, seed='seed',
                      output_dir=tmp_path / 'results', solver=solver)
    assert preflights == [{}]
    assert all(options == {} for _, options in calls)
    assert all(o['status'] == 'prediction_generated' for o in result['results'])


def test_dry_run_makes_no_model_calls_or_preflight(tmp_path):
    generate, solver, calls, preflights = _load_generate(tmp_path, images={})
    result = generate(dataset_name='fixture', split='test', count=2, seed='seed',
                      output_dir=tmp_path / 'results', solver=solver, dry_run=True,
                      public_test_images={'sympy/sympy': 'bugpilot-public-tests:missing'})
    assert len(result['selected']) == 2
    assert calls == [] and preflights == []
