"""Verify accessibility requirements."""


def check(candidate, context=None) -> dict:
    """Return accessibility severity and an auditable explanation."""
    del context
    if all(item.get("subtitle") and item.get("audio") for item in candidate):
        return {"status": "pass", "detail": "Every selected segment has dialogue audio and subtitles."}
    return {"status": "warning", "detail": "Audio or subtitles are missing for one or more segments."}
