import json

import requests
from django.conf import settings

from .base import InferenceResult

SYSTEM_PROMPT = (
    "You are a moderation assistant for the r/LouboutinLife subreddit. "
    "Given a post or comment's text, decide whether it violates typical "
    "subreddit rules (spam, harassment, scams/counterfeit sales, off-topic "
    "content, or other abuse). "
    "Respond with ONLY a JSON object, no other text, matching exactly this "
    'shape: {"flagged": <true|false>, "category": <short string, empty if '
    'not flagged>, "confidence": <float between 0 and 1>, "rationale": '
    '<one sentence>}.'
)


class OpenAICompatibleBackend:
    """Client for any server exposing an OpenAI-compatible chat completions
    endpoint (Ollama, llama.cpp server, vLLM, ...) — only INFERENCE_BASE_URL
    and INFERENCE_MODEL need to change to point at a different one."""

    def __init__(self, base_url=None, model_name=None):
        self.base_url = (base_url or settings.INFERENCE_BASE_URL).rstrip("/")
        self.model_name = model_name or settings.INFERENCE_MODEL

    def classify(self, text: str) -> InferenceResult:
        response = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "temperature": 0,
            },
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]

        try:
            parsed = json.loads(content)
            return InferenceResult(
                flagged=bool(parsed["flagged"]),
                category=str(parsed.get("category", "")),
                confidence=float(parsed.get("confidence", 0.0)),
                rationale=str(parsed.get("rationale", "")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise ValueError(f"Malformed inference response: {content!r}") from e
