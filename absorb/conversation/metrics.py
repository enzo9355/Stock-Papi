from __future__ import annotations

import threading


METRIC_NAMES = frozenset(
    {
        "natural_language_requests",
        "command_requests",
        "llm_success",
        "llm_timeout",
        "llm_error",
        "tool_calls",
        "tool_errors",
        "clarification_requests",
        "stale_data_answers",
        "insufficient_data_answers",
        "write_action_proposals",
        "write_confirmations",
        "rejected_prompt_injection",
    }
)


class SafeConversationMetrics:
    """Process-local counters that never accept labels or user content."""

    def __init__(self):
        self._counts = {name: 0 for name in METRIC_NAMES}
        self._lock = threading.Lock()

    def increment(self, name: str) -> None:
        if name not in METRIC_NAMES:
            raise ValueError("unknown conversation metric")
        with self._lock:
            self._counts[name] += 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def clear(self) -> None:
        with self._lock:
            for name in self._counts:
                self._counts[name] = 0


CONVERSATION_METRICS = SafeConversationMetrics()


def record_metric(name: str) -> None:
    CONVERSATION_METRICS.increment(name)
