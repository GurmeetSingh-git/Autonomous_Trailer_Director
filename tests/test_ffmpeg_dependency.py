import pytest

import api


def test_resolve_ffmpeg_path_requires_install(monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda name: None)

    with pytest.raises(FileNotFoundError, match="FFmpeg is not installed"):
        api.resolve_ffmpeg_path()
