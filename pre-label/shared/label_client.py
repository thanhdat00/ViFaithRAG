from pathlib import Path
from typing import Any, Protocol


class LabelClient(Protocol):
    def single_call(self, *, request: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Run one JSON labeling request and return parsed JSON plus raw response text."""

    def text_call(self, *, request: dict[str, Any]) -> str:
        """Run one text generation request and return response text."""

    def batch_call(
        self,
        *,
        requests: list[dict[str, Any]],
        input_file: Path,
        completion_window: str,
    ) -> dict[str, Any]:
        """Submit requests as an async batch and return provider metadata."""

    def retrieve_batch(self, batch_id: str) -> dict[str, Any]:
        """Return provider metadata for one async batch."""

    def wait_for_batch(self, *, batch_id: str, poll_interval_seconds: float) -> dict[str, Any]:
        """Poll one async batch until it reaches a terminal status."""

    def batch_call_sequential(
        self,
        *,
        requests: list[dict[str, Any]],
        input_file: Path,
        completion_window: str,
        batch_size: int,
        poll_interval_seconds: float,
    ) -> list[dict[str, Any]]:
        """Submit requests in chunks, waiting for each batch to complete before the next."""
