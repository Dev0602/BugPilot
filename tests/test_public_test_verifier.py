"""Mock-based tests: never start Docker or use Claude API credits."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from evaluation.swebench.current.public_test_verifier import run_public_tests, _validate_test_targets


@pytest.fixture
def repo(tmp_path):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_sample.py').write_text('def test_works(): pass\n')
    return tmp_path


@pytest.mark.parametrize('target', [
    '../test_secret.py', '/etc/passwd', '-k evil',
    'tests/missing.py', 'tests/test_sample.py\n--rootdir=/etc',
    'tests/test_sample.py::',
])
def test_reject_bad_test_targets(repo, target):
    with pytest.raises(ValueError):
        _validate_test_targets(repo, [target])


def test_accept_existing_test_node(repo):
    assert _validate_test_targets(repo, ['tests/test_sample.py::test_works']) == [
        'tests/test_sample.py::test_works'
    ]


class FakeContainer:
    def __init__(self, exit_code):
        self.exit_code = exit_code
        self.removed = False
        self.killed = False

    def wait(self, timeout):
        assert timeout == 60
        return {'StatusCode': self.exit_code}

    def logs(self):
        return b'1 passed' if self.exit_code == 0 else b'1 failed'

    def remove(self, force):
        self.removed = force

    def kill(self):
        self.killed = True


@pytest.mark.parametrize('code,status', [
    (0, 'passed'), (1, 'failed'), (2, 'infrastructure_error'), (5, 'infrastructure_error')
])
def test_container_outcomes(repo, code, status):
    container = FakeContainer(code)

    def launch(*args, **kwargs):
        assert kwargs['network_disabled'] is True
        assert kwargs['read_only'] is True
        assert kwargs['volumes'][str(repo.resolve())]['mode'] == 'ro'
        assert kwargs['cap_drop'] == ['ALL']
        assert kwargs['command'][0:2] == ['python', '-c']
        return container

    fake_client = SimpleNamespace(
        images=SimpleNamespace(get=lambda name: name),
        containers=SimpleNamespace(run=launch),
    )
    outcome = run_public_tests(
        repo,
        ['tests/test_sample.py'],
        image='bugpilot-public-tests:demo',
        timeout_seconds=60,
        docker_client=fake_client,
    )
    assert outcome['status'] == status
    assert container.removed


def test_missing_image_is_not_test_failure(repo):
    def missing(_):
        raise RuntimeError('Image not found')

    fake_client = SimpleNamespace(images=SimpleNamespace(get=missing))
    outcome = run_public_tests(
        repo,
        ['tests/test_sample.py'],
        image='bugpilot-public-tests:demo',
        docker_client=fake_client,
    )
    assert outcome['status'] == 'infrastructure_error'


def test_reject_non_allowlisted_image(repo):
    with pytest.raises(ValueError):
        run_public_tests(repo, ['tests/test_sample.py'], image='ubuntu:latest')


def test_reject_symlink_outside_repo(repo, tmp_path):
    outside = tmp_path.parent / 'test_outside_public_test_verifier.py'
    outside.write_text('def test_no(): pass\n')
    (repo / 'tests' / 'test_external.py').symlink_to(outside)
    with pytest.raises(ValueError):
        _validate_test_targets(repo, ['tests/test_external.py'])


def test_missing_pytest_is_not_failed_assertion(repo):
    class NoPytestContainer(FakeContainer):
        def logs(self):
            return b'/usr/bin/python: No module named pytest'

    container = NoPytestContainer(1)
    fake_client = SimpleNamespace(
        images=SimpleNamespace(get=lambda name: name),
        containers=SimpleNamespace(run=lambda *a, **kw: container),
    )
    result = run_public_tests(
        repo, ['tests/test_sample.py'],
        image='bugpilot-public-tests:demo',
        docker_client=fake_client,
    )
    assert result['status'] == 'infrastructure_error'
