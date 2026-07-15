from __future__ import annotations

import datetime as dt
import threading

from absorb.conversation.errors import ModelUnavailable
from absorb.conversation.metrics import record_metric


class GeminiConversationProvider:
    """Bounded adapter around the existing lazy Gemini model."""

    def __init__(self, model, *, failure_threshold=3, cooldown_seconds=60, now=None):
        self.model = model
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc))
        self._failures = 0
        self._open_until = None
        self._lock = threading.Lock()

    def plan(self, prompt):
        return self._generate(prompt, json_mode=True)

    def answer(self, prompt):
        return self._generate(prompt, json_mode=False)

    def _generate(self, prompt, *, json_mode):
        if self.model is None:
            raise ModelUnavailable("model unavailable")
        with self._lock:
            if self._open_until is not None and self._open_until > self.now():
                raise ModelUnavailable("model circuit open")
        kwargs = {"request_options": {"timeout": 8}}
        if json_mode:
            kwargs["generation_config"] = {"response_mime_type": "application/json"}
        try:
            response = self.model.generate_content(prompt, **kwargs)
            text = str(getattr(response, "text", "") or "").strip()
            if not text:
                raise ModelUnavailable("empty model response")
        except Exception as exc:
            if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
                record_metric("llm_timeout")
            with self._lock:
                self._failures += 1
                if self._failures >= self.failure_threshold:
                    self._open_until = self.now() + dt.timedelta(seconds=self.cooldown_seconds)
            raise ModelUnavailable("model request failed") from exc
        with self._lock:
            self._failures = 0
            self._open_until = None
        return text
