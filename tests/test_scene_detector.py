from src.ingestion import scene_detector


def test_scene_detection_samples_frames_and_closes_video(monkeypatch) -> None:
    calls = {}

    class FakeCapture:
        released = False

        def release(self) -> None:
            self.released = True

    class FakeVideo:
        _cap = FakeCapture()

    class FakeSceneManager:
        def add_detector(self, detector) -> None:
            calls["threshold"] = detector._threshold

        def detect_scenes(self, video, frame_skip: int) -> None:
            calls["video"] = video
            calls["frame_skip"] = frame_skip

        def get_scene_list(self) -> list:
            return []

    video = FakeVideo()
    monkeypatch.setattr(scene_detector, "open_video", lambda path: video)
    monkeypatch.setattr(scene_detector, "SceneManager", FakeSceneManager)

    assert scene_detector.detect_scene_cuts("episode.mp4", threshold=25.0) == []
    assert calls == {"threshold": 25.0, "video": video, "frame_skip": scene_detector.FRAME_SKIP}
    assert video._cap.released
