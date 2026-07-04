from unittest.mock import patch

from config import get_llm_config
from local import LocalLlamaService, _heuristic_tool_call_payload


def test_get_llm_config_local_backend(monkeypatch, tmp_path):
    model_path = tmp_path / "test-model.gguf"
    model_path.write_text("stub", encoding="utf-8")

    monkeypatch.setenv("SCOUT_BACKEND", "local")
    monkeypatch.setenv("SCOUT_LOCAL_MODEL_PATH", str(model_path))
    monkeypatch.setenv("SCOUT_LOCAL_BASE_URL", "http://127.0.0.1:4242/v1")
    monkeypatch.setenv("SCOUT_LOCAL_API_KEY", "local")

    config = get_llm_config()

    assert config["backend"] == "local"
    assert config["base_url"] == "http://127.0.0.1:4242/v1"
    assert config["api_key"] == "local"
    assert config["model"] == "test-model.gguf"


def test_local_service_gpu_fallback_tries_lower_layers(tmp_path):
    model_path = tmp_path / "model.gguf"
    model_path.write_text("stub", encoding="utf-8")

    attempts = []

    class FakeLLM:
        def create_chat_completion(self, **kwargs):
            return {
                "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    def fake_build(model_path_arg, ctx, threads, gpu_layers):
        attempts.append(gpu_layers)
        if gpu_layers in (16, 8):
            raise RuntimeError("GPU offload unavailable")
        return FakeLLM()

    with patch("local._build_llama", side_effect=fake_build):
        service = LocalLlamaService(model_path, ctx=2048, threads=2, gpu_layers="auto", max_tokens=64)
        service.load()

    assert attempts == [16, 8, 0]
    assert service.selected_gpu_layers == 0


def test_local_service_formats_openai_chat_response(tmp_path):
    model_path = tmp_path / "model.gguf"
    model_path.write_text("stub", encoding="utf-8")

    class FakeLLM:
        def create_chat_completion(self, **kwargs):
            return {
                "id": "chatcmpl-test",
                "created": 123,
                "choices": [{"message": {"content": "reply"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7},
            }

    service = LocalLlamaService(model_path, ctx=2048, threads=2, gpu_layers="0", max_tokens=64)
    service._llm = FakeLLM()

    response = service.chat_completion(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.0,
            "max_tokens": 12,
        }
    )

    assert response["object"] == "chat.completion"
    assert response["model"] == "model.gguf"
    assert response["choices"][0]["message"]["role"] == "assistant"
    assert response["choices"][0]["message"]["content"] == "reply"
    assert response["usage"]["total_tokens"] == 7


def test_local_router_promotes_memory_questions_to_sysinfo():
    payload = _heuristic_tool_call_payload(
        [
            {"role": "system", "content": "tool prompt"},
            {"role": "user", "content": "how much memory do i have"},
        ]
    )

    assert payload == {"tool_calls": [{"tool": "get_sysinfo", "args": {}}]}


def test_local_router_promotes_ollama_install_check_to_run_cmd():
    payload = _heuristic_tool_call_payload(
        [
            {"role": "system", "content": "tool prompt"},
            {"role": "user", "content": "verify if i have ollama"},
        ]
    )

    assert payload == {"tool_calls": [{"tool": "run_cmd", "args": {"command": "ollama --version"}}]}
