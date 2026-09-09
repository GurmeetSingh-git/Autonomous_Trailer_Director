# AI Collaboration Note

AI tools were used as implementation assistants, not as authoritative decision makers.

## Verification approach

- Repository structure and existing contracts were inspected before edits.
- Generated code was checked with Python compilation, TypeScript checking, and pytest.
- The deterministic pipeline was exercised through the public CLI.
- The live Gemini path is isolated from replay mode so evaluators do not need a personal API key.
- Model-generated story facts are validated against source-backed scene IDs and timing before becoming trailer segments.

## Known AI failure modes considered

- Invented scene references are rejected by the existence check.
- High-spoiler scenes are rejected.
- Invalid or zero-length time ranges are rejected.
- Model unavailability is handled by replay mode and the configured fallback model.
