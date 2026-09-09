"""Verify rating and content policy compliance."""


def check(candidate, context=None) -> dict:
    """Return rating severity and an auditable explanation."""
    audience = (context or {}).get("audience", "family")
    if audience == "family" and any(item.get("sensitive_content", []) for item in candidate):
        return {"status": "fail", "detail": "Sensitive content is not allowed for the family audience."}
    return {"status": "pass", "detail": f"Selected content meets the {audience} audience policy."}
