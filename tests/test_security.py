from app.core.security import secrets_match


def test_secret_comparison() -> None:
    assert secrets_match("expected", "expected") is True
    assert secrets_match("wrong", "expected") is False
    assert secrets_match(None, "expected") is False
