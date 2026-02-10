# src/app/llm.py

import random
import time
import httpx
from app.settings import settings


class MockLLMClient:
    model = "mock-llm"

    def generate(self, prompt: str) -> str:
        time.sleep(1.0)
        if random.random() < 0.03:    
            raise RuntimeError("Mock LLM transient error")
        return f"[MOCK OUTPUT]\n\nPrompt:\n{prompt}\n\nResponse:\nThis is a mocked response."


class OpenAILLMClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def generate(self, prompt: str) -> str:
        # TODO: move to constants.py
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"model": self.model, "messages": [{"role": "user", "content": prompt}]}

        with httpx.Client(timeout=30.0) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]


def get_llm_client():
     # TODO: move openai to constants.py
    if settings.llm_provider.lower() == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY required when LLM_PROVIDER=openai")
        return OpenAILLMClient(settings.openai_api_key, settings.openai_model)
    return MockLLMClient()
