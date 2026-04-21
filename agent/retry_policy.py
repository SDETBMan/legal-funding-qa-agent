"""
Retry helpers for LangGraph nodes and tools.

Only retry exception types you explicitly allow (e.g. timeouts, connect failures).
Do not blanket-retry on HTTP 4xx/semantic errors — a 404 is still a 404 on retry.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

import httpx
import structlog

log = structlog.get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Timeouts and transport-level failures — not ``HTTPStatusError`` (404, 409, etc.).
TRANSIENT_HTTPX_ERRORS: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.NetworkError,
    httpx.ReadError,
    httpx.WriteError,
    httpx.PoolTimeout,
)


def with_retry(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    retry_on: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError),
    tool_name: str = "unknown_tool",
) -> Callable[[F], F]:
    """
    Async exponential backoff for coroutine tools (e.g. Playwright, async httpx).

    Exceptions not in ``retry_on`` propagate immediately (no wasted attempts).
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: BaseException | None = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        log.warning(
                            "retry_attempt",
                            tool=tool_name,
                            attempt=attempt,
                            max_retries=max_retries,
                            delay_seconds=delay,
                        )
                    return await func(*args, **kwargs)

                except retry_on as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        log.warning(
                            "retry_scheduled",
                            tool=tool_name,
                            error_type=type(exc).__name__,
                            message=str(exc),
                            delay_seconds=delay,
                        )
                        await asyncio.sleep(delay)
                        delay *= backoff_factor
                    else:
                        log.error(
                            "retries_exhausted",
                            tool=tool_name,
                            max_retries=max_retries,
                            error_type=type(exc).__name__,
                            message=str(exc),
                        )

                except Exception as exc:
                    log.error(
                        "non_retryable_error",
                        tool=tool_name,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                    raise

            assert last_exception is not None
            raise last_exception

        return cast(F, wrapper)

    return decorator


def with_retry_sync(
    max_retries: int = 3,
    backoff_factor: float = 2.0,
    initial_delay: float = 1.0,
    retry_on: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError),
    tool_name: str = "unknown_tool",
) -> Callable[[F], F]:
    """
    Sync exponential backoff for blocking tools (e.g. sync ``httpx.Client``, file I/O
    where you still only want retries on transport timeouts — not on missing files).
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: BaseException | None = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        log.warning(
                            "retry_attempt",
                            tool=tool_name,
                            attempt=attempt,
                            max_retries=max_retries,
                            delay_seconds=delay,
                        )
                    return func(*args, **kwargs)

                except retry_on as exc:
                    last_exception = exc
                    if attempt < max_retries:
                        log.warning(
                            "retry_scheduled",
                            tool=tool_name,
                            error_type=type(exc).__name__,
                            message=str(exc),
                            delay_seconds=delay,
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        log.error(
                            "retries_exhausted",
                            tool=tool_name,
                            max_retries=max_retries,
                            error_type=type(exc).__name__,
                            message=str(exc),
                        )

                except Exception as exc:
                    log.error(
                        "non_retryable_error",
                        tool=tool_name,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                    raise

            assert last_exception is not None
            raise last_exception

        return cast(F, wrapper)

    return decorator


class FallbackModelConfig:
    """
    Primary/fallback model ids when the primary provider fails (e.g. outage).

    Call ``activate_fallback`` from your LLM node when you catch a retry-exhausted
    or provider-specific transport error; keep business logic out of this class.
    """

    def __init__(self, primary: str, fallback: str) -> None:
        self.primary = primary
        self.fallback = fallback
        self._using_fallback = False

    def get_current_model(self) -> str:
        return self.fallback if self._using_fallback else self.primary

    def activate_fallback(self, reason: str) -> None:
        if not self._using_fallback:
            log.warning(
                "model_fallback_activated",
                primary=self.primary,
                fallback=self.fallback,
                reason=reason,
            )
            self._using_fallback = True

    def reset(self) -> None:
        if self._using_fallback:
            log.info("model_fallback_reset", primary=self.primary)
            self._using_fallback = False

    @property
    def is_using_fallback(self) -> bool:
        return self._using_fallback
