# Known Limitations

- Replay mode uses a deterministic fixture when an episode package has no structured metadata; it does not infer scenes from raw pixels.
- The live API currently stores run state in memory and is intended for a local demonstration.
- Rights, subtitle, contract, and audience-profile inputs are not yet loaded from external package files.
- Video rendering is not implemented; the output is an executable edit decision list.
- A human editor, legal reviewer, and cultural reviewer must approve final promotional use.
- Gemini availability, quotas, and media-processing limits remain external dependencies.
