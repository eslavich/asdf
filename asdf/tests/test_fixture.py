import pytest

@pytest.fixture(scope='module')
def some_module_fixture():
    return {"values": []}

@pytest.mark.parametrize("value", [1, 2, 3])
def test_something(some_module_fixture, value):
    some_module_fixture["values"].append(value)
    assert some_module_fixture["values"] == [value]
