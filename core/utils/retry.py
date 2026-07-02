"""
Retry decorator with exponential backoff.

Usage:
    from core.utils.retry import retry

    @retry(max_attempts=3, base_delay=1.0)
    def flaky_function():
        ...
"""
import time
import functools
from typing import Type


def retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator: retry a function on exception with exponential backoff.

    Args:
        max_attempts:   Total attempts before raising (default 3).
        base_delay:     Initial wait in seconds (default 1.0).
        backoff_factor: Multiply delay by this each retry (default 2.0).
        exceptions:     Exception types to catch (default: all).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = base_delay
            last_error: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as error:
                    last_error = error
                    if attempt == max_attempts:
                        break
                    time.sleep(delay)
                    delay *= backoff_factor

            raise last_error

        return wrapper
    return decorator
