import asyncio
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

P = ParamSpec("P")
T = TypeVar("T")

_RETRYABLE_STATUS_CODES = {429}


def _is_retryable_http(exc: BaseException) -> bool:
    if isinstance(exc, httpx.RequestError | TimeoutError | ConnectionError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else 0
        return status in _RETRYABLE_STATUS_CODES or 500 <= status < 600
    return False


async def honor_retry_after(response: httpx.Response, cap: float = 60.0) -> None:
    raw = response.headers.get("retry-after")
    if raw is None:
        return
    try:
        delay = min(float(raw), cap)
    except ValueError:
        return
    if delay > 0:
        await asyncio.sleep(delay)


def _http_status_error(message: str, response: httpx.Response) -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(message, request=response.request, response=response)


_HTTP_RETRYABLE = (httpx.RequestError, TimeoutError, ConnectionError)
_TG_RETRYABLE = (TimeoutError, ConnectionError, OSError)

_tenacity_http = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception(_is_retryable_http),
    reraise=True,
)

_tenacity_tg = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(_TG_RETRYABLE),
    reraise=True,
)


def retry_http(func: Callable[P, T]) -> Callable[P, T]:
    return _tenacity_http(func)


def retry_tg(func: Callable[P, T]) -> Callable[P, T]:
    return _tenacity_tg(func)


E = TypeVar("E", bound=BaseException)


def retry_on(exc_type: type[E]) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Three-attempt retry decorator for a specific exception type."""

    def deco(func: Callable[P, T]) -> Callable[P, T]:
        return retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
            retry=retry_if_exception_type(exc_type),
            reraise=True,
        )(func)

    return deco
