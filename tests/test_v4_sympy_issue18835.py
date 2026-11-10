"""Local unit tests; no Docker, SymPy installation, or Claude API required."""
import ast
import pytest

from scripts.check_v4_sympy_issue18835 import REPRO_CONTENT, REPRO_PATH, classify, _write_repro


def test_repro_source_and_isolation(tmp_path):
    ast.parse(REPRO_CONTENT)
    assert 'with pytest.raises(RuntimeError):' in REPRO_CONTENT
    assert 'values.remove("T")' in REPRO_CONTENT
    _write_repro(tmp_path)
    assert (tmp_path / REPRO_PATH).read_text() == REPRO_CONTENT
    with pytest.raises(RuntimeError):
        _write_repro(tmp_path)


def test_classification():
    p = {'status': 'passed'}
    f = {'status': 'failed'}
    e = {'status': 'infrastructure_error'}
    assert 'RED TO GREEN' in classify(f, p)
    assert 'STILL FAILING' in classify(f, f)
    assert 'BOTH PASS' in classify(p, p)
    assert 'REGRESSION' in classify(p, f)
    assert 'INFRASTRUCTURE ERROR' in classify(e, p)
