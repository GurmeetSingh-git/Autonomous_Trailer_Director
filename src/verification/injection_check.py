"""Verify untrusted content cannot alter pipeline instructions."""


def check(candidate, context=None) -> dict:
    """Return prompt-injection severity and an auditable explanation."""
    del context
    blocked = ("ignore previous", "ignore the contract", "reveal system prompt")
    if any(token in str(candidate).lower() for token in blocked):
        return {"status": "fail", "detail": "Untrusted scene content attempted to alter pipeline instructions."}
    return {"status": "pass", "detail": "No prompt-injection instruction was detected in candidate content."}
