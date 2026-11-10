"""Tests for safe clean-HEAD comparison without Docker or LLM calls."""

from pathlib import Path
import importlib.util
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/check_v4_sympy_baseline.py'


def load():
    spec = importlib.util.spec_from_file_location('v4_sympy_baseline', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_head_export_does_not_modify_checkout(tmp_path):
    src = tmp_path / 'repo'; src.mkdir()
    subprocess.run(['git','-C',str(src),'init','-q'], check=True)
    subprocess.run(['git','-C',str(src),'config','user.email','test@example.com'], check=True)
    subprocess.run(['git','-C',str(src),'config','user.name','Test'], check=True)
    test = src/'sympy/utilities/tests/test_iterables.py'
    test.parent.mkdir(parents=True)
    test.write_text('def test_example(): assert True\n')
    file = src/'sympy/utilities/iterables.py'
    file.write_text('def foo(): return 1\n')
    subprocess.run(['git','-C',str(src),'add','.'], check=True)
    subprocess.run(['git','-C',str(src),'commit','-qm','fixture'], check=True)
    file.write_text('def foo(): return 2\n')
    out = tmp_path / 'baseline'; out.mkdir()
    mod = load()
    mod.archive_head(src, out)
    assert (out/'sympy/utilities/iterables.py').read_text() == 'def foo(): return 1\n'
    assert file.read_text() == 'def foo(): return 2\n'
    assert (out/'sympy/utilities/tests/test_iterables.py').is_file()


def test_interpret_regression_and_issue_signal():
    f=load().interpret
    p={'status':'passed'}; n={'status':'failed'}; e={'status':'infrastructure_error'}
    assert 'REGRESSION COVERAGE ONLY' in f(p,p)
    assert 'USEFUL SIGNAL' in f(n,p)
    assert 'REGRESSION SIGNAL' in f(p,n)
    assert 'BOTH FAILED' in f(n,n)
    assert 'INFRASTRUCTURE ERROR' in f(e,p)
