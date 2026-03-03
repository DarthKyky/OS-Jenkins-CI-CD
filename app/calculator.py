from numbers import Real


def _ensure_number(x, name: str):
    if not isinstance(x, Real):
        raise TypeError(f"{name} must be a real number (int/float), got {type(x).__name__}")


def add(a, b):
    _ensure_number(a, "a")
    _ensure_number(b, "b")
    return a + b


def subtract(a, b):
    _ensure_number(a, "a")
    _ensure_number(b, "b")
    return a - b


def multiply(a, b):
    _ensure_number(a, "a")
    _ensure_number(b, "b")
    return a * b


def divide(a, b):
    _ensure_number(a, "a")
    _ensure_number(b, "b")
    if b == 0:
        raise ValueError("Division by zero")
    return a / b
