"""Client for the local OpenAI-compatible model server (Colibri). There is no other backend:
if this server is down, analysis waits and everything else keeps working."""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from .config import ModelConfig


class ModelUnavailable(Exception):
    """The server is down or serving a different model. Tasks wait; attempts are not spent."""


class ModelError(Exception):
    pass


@dataclass
class Reply:
    text: str
    model_served: str
    tokens_in: int | None
    tokens_out: int | None
    finish_reason: str | None
    duration_ms: int


class LocalModel:
    def __init__(self, cfg: ModelConfig, transport: httpx.BaseTransport | None = None):
        self.cfg = cfg
        self.client = httpx.Client(base_url=cfg.base_url.rstrip("/"), transport=transport, timeout=httpx.Timeout(cfg.request_timeout_seconds, connect=5))

    def status(self) -> dict:
        """What the server is serving right now. Lists models only; never generates."""
        try:
            r = self.client.get("/models", timeout=5)
            r.raise_for_status()
            served = [m.get("id") for m in r.json().get("data", [])]
            ctx = next((m.get("context_length") for m in r.json().get("data", []) if m.get("id") in served), None)
        except (httpx.HTTPError, ValueError) as e:
            return {"reachable": False, "served": [], "configured": self.cfg.model_id, "ready": False,
                    "message": f"The local model server at {self.cfg.base_url} is not reachable ({type(e).__name__})."}
        ready = self.cfg.model_id in served
        msg = "Ready" if ready else (
            f"The server is running {', '.join(served) or 'no model'}, not the configured {self.cfg.model_id}. "
            "Analysis waits until the configured model is served, or until you change the configured model.")
        return {"reachable": True, "served": served, "configured": self.cfg.model_id, "ready": ready, "contextTokens": ctx, "message": msg}

    def chat(self, system: str, user: str, *, max_tokens: int | None = None, model: str | None = None) -> Reply:
        model = model or self.cfg.model_id
        body = {"model": model, "temperature": 0, "max_tokens": max_tokens or self.cfg.max_output_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        start = time.monotonic()
        try:
            r = self.client.post("/chat/completions", json=body)
        except httpx.ConnectError as e:
            raise ModelUnavailable(f"Model server not reachable: {e}") from None
        except httpx.TimeoutException:
            raise ModelError(f"No reply within {self.cfg.request_timeout_seconds:.0f} s.") from None
        except httpx.HTTPError as e:
            raise ModelError(f"{type(e).__name__}: {e}") from None
        ms = int((time.monotonic() - start) * 1000)
        if r.status_code in (404, 503) and "model" in r.text.lower():
            raise ModelUnavailable(f"HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code != 200:
            raise ModelError(f"HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return Reply(text=(choice.get("message") or {}).get("content") or "", model_served=data.get("model") or "unknown",
                     tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"),
                     finish_reason=choice.get("finish_reason"), duration_ms=ms)
