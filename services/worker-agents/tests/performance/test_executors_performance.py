import pytest


pytestmark = pytest.mark.skip(reason='Performance tests not runnable in unit environment')


def test_performance_placeholder():
    assert True
