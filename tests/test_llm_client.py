from types import SimpleNamespace

from llm.client import LLMClient


class RateLimitError(Exception):
    status_code = 429


def test_live_client_retries_rate_limited_generation(monkeypatch, tmp_path) -> None:
    attempts = 0

    class Models:
        def generate_content(self, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise RateLimitError("too many requests")
            return SimpleNamespace(parsed=SimpleNamespace(ok=True), text="")

    class Files:
        def upload(self, file):
            return SimpleNamespace(name="file-1", state=SimpleNamespace(name="ACTIVE"))

        def get(self, name):
            return SimpleNamespace(name=name, state=SimpleNamespace(name="ACTIVE"))

    class Client:
        models = Models()
        files = Files()

    monkeypatch.setattr("llm.client.genai.Client", lambda api_key: Client())
    monkeypatch.setattr("llm.client.time.sleep", lambda _: None)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    result = LLMClient(mode="live").generate_structured(
        system_prompt="test",
        media=str(tmp_path / "frame.jpg"),
        context={},
        response_schema=object,
    )

    assert result.ok is True
    assert attempts == 2