"""Verify no protected story fact is exposed by a candidate segment."""


def check(candidate, context=None) -> dict:
    """Return spoiler severity by checking candidate text against protected_facts.

    This is independent of any spoiler_level the generator assigned itself:
    it re-derives the verdict from a separately curated protected_facts list,
    never from a field the candidate-generation call set.
    """
    context = context or {}
    protected_facts = context.get("protected_facts", [])
    if not protected_facts:
        return {"status": "warning", "detail": "No protected_facts supplied; spoiler check has no ground truth to verify against."}

    exposed = []
    for item in candidate:
        text = f"{item.get('reason', '')} {item.get('description', '')}".lower()
        scene_id = item.get("scene_id")
        for fact in protected_facts:
            # Rule A: this segment's scene is exactly where the fact is first revealed.
            if fact.get("first_revealed_in") and scene_id == fact["first_revealed_in"]:
                exposed.append({"scene_id": scene_id, "fact_id": fact["id"], "reason": "segment is the fact's reveal scene"})
                continue
            # Rule B: the segment's own text echoes a keyword tied to the fact.
            if any(keyword.lower() in text for keyword in fact.get("keywords", [])):
                exposed.append({"scene_id": scene_id, "fact_id": fact["id"], "reason": "segment text matches a protected-fact keyword"})

    if exposed:
        detail = "; ".join(f"{e['scene_id']} exposes {e['fact_id']} ({e['reason']})" for e in exposed)
        return {"status": "fail", "detail": detail}
    return {"status": "pass", "detail": f"No candidate segment matched any of {len(protected_facts)} protected facts."}