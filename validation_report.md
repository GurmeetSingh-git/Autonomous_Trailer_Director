# Validation Report

## Replay run

Command:

```powershell
python cli.py --episode sample_run\episode --audience family --output submission
```

Result: `PASS_WITH_WARNINGS`

Generated artifacts:

- `story_map.json`
- `constraint_map.json`
- `family_trailer.json`
- `young_adult_trailer.json`
- `dialect_region_trailer.json`
- `decision_log.json`

## Checks

The replay validator verifies that every selected segment references a known scene, has a positive source range, excludes high-spoiler scenes, includes audio and subtitles, passes rights/rating/accessibility/bias/budget checks, and is screened for prompt-injection text. Each segment includes its source scene and policy evidence.

## Live path

The FastAPI upload path saves the video and requests a structured story map from Gemini. Live provider failures are returned as HTTP 502 with diagnostic logging. Replay mode remains the recommended evaluator path because it is deterministic and requires no API key.
