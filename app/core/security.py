import secrets


def secrets_match(provided: str | None, expected: str) -> bool:
    """Compare request secrets without timing-sensitive equality."""

    return provided is not None and secrets.compare_digest(provided, expected)
