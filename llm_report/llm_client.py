import os
from typing import Optional

try:
    import openai
except Exception:
    openai = None


class LLMClient:
    def __init__(self, model_version: str = "default", api_key: Optional[str] = None, mock: Optional[bool] = None, provider: str = "openai"):
        self.model_version = model_version
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.provider = provider.lower()

        if mock is None:
            self.mock = os.environ.get("ENABLE_MOCK_LLM", "true").lower() in ("1", "true", "yes", "on")
        else:
            self.mock = bool(mock)

        if not self.mock and self.provider == "openai" and openai is not None and self.api_key:
            openai.api_key = self.api_key

    def generate(self, prompt: str, max_tokens: int = 256) -> str:
        if self.mock:
            snippet = prompt[:120].replace("\n", " ").replace("  ", " ")
            return f"[MOCK] {snippet}..."

        if self.provider == "openai" and openai is not None and self.api_key:
            try:
                resp = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=max_tokens,
                    temperature=0.2,
                )
                return resp.choices[0].message["content"].strip()
            except Exception as e:
                return f"[MOCK] API 실패: {e}"

        elif self.provider == "openrouter":
            import requests
            key = os.environ.get("OPENROUTER_API_KEY") or self.api_key
            if not key:
                return "[MOCK] OpenRouter API 키가 설정되지 않음"
            base = os.environ.get("OPENROUTER_API_BASE", "https://openrouter.ai/api/v1/chat/completions")
            model = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            }
            try:
                resp = requests.post(base, headers=headers, json=payload, timeout=30)
                if not resp.ok:
                    return f"[MOCK] OpenRouter 응답 실패: {resp.status_code} {resp.text[:200]}"
                data = resp.json()
                if isinstance(data, dict):
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if content:
                        return content.strip()
                return "[MOCK] OpenRouter 응답 파싱 실패"
            except Exception as e:
                return f"[MOCK] OpenRouter 예외: {e}"

        return "[MOCK] Unsupported provider"