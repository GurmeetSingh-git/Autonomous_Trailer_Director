"""Verify bias and representation constraints."""


def check(candidate, context=None) -> dict:
    """Return cultural-respect severity and an auditable explanation."""
    del context
    if any("stereotype" in str(item).lower() for item in candidate):
        return {"status": "fail", "detail": "Candidate language contains a stereotyping signal."}
    return {"status": "pass", "detail": "No stereotyping language was detected in the selected evidence."}
