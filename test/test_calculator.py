import pytest
from app.calculator import add, subtract, multiply, divide


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(10, 4) == 6


def test_multiply():
    assert multiply(3, 7) == 21


def test_divide_basic():
    assert divide(20, 5) == 4


def test_divide_returns_float():
    # Python division returns float
    assert isinstance(divide(9, 2), float)
    assert divide(9, 2) == 4.5


def test_divide_by_zero_raises_valueerror():
    with pytest.raises(ValueError, match="Division by zero"):
        divide(20, 0)


def test_float_precision_with_approx():
    assert divide(1, 3) == pytest.approx(0.3333333333, rel=1e-9)


@pytest.mark.parametrize("a,b", [
    ("2", 3),
    (2, "3"),
    (None, 1),
    ([], 1),
])

def test_type_validation_raises_typeerror(a, b):
    with pytest.raises(TypeError):
        add(a, b)

def test_wrong_divide_result():
    assert divide (20, 5) == 5
    
def test_divide():
    assert divide(20, 0) == 4
