import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

_HTTP_RETRYABLE = (httpx.RequestError, TimeoutError, ConnectionError)
_TG_RETRYABLE = (TimeoutError, ConnectionError, OSError)

retry_http = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(_HTTP_RETRYABLE),
    reraise=True,
)

retry_tg = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    retry=retry_if_exception_type(_TG_RETRYABLE),
    reraise=True,
)
