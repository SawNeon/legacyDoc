"""In-process request throttling."""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_MAX_TRACKED_KEYS = 50_000


@dataclass(frozen=True)
class RateLimitRule:
    """How many requests a single key may spend inside a window."""

    max_requests: int
    window_seconds: float
    name: str = "default"

    def __post_init__(self) -> None:
        if self.max_requests < 1:
            raise ValueError("max_requests precisa ser pelo menos 1.")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds precisa ser positivo.")


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int


@dataclass
class _KeyState:
    """Counters for the current window and the one before it."""

    window_index: int
    current_count: int
    previous_count: int


class SlidingWindowRateLimiter:
    """Approximate sliding window, the same shape nginx and CDNs use."""

    def __init__(
        self,
        *,
        max_tracked_keys: int = DEFAULT_MAX_TRACKED_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._states: OrderedDict[str, _KeyState] = OrderedDict()
        self._max_tracked_keys = max_tracked_keys
        self._clock = clock

    def check(self, key: str, rule: RateLimitRule) -> RateLimitDecision:
        """Count one request against `key` and say whether it may proceed."""
        now = self._clock()
        window_index = int(now // rule.window_seconds)
        elapsed_fraction = (now % rule.window_seconds) / rule.window_seconds

        state = self._state_for(key, window_index)
        estimated = state.previous_count * (1.0 - elapsed_fraction) + state.current_count

        if estimated >= rule.max_requests:
            return RateLimitDecision(
                allowed=False,
                remaining=0,
                retry_after_seconds=_seconds_until_allowed(state, rule, elapsed_fraction),
            )

        state.current_count += 1

        return RateLimitDecision(
            allowed=True,
            remaining=max(0, rule.max_requests - int(estimated) - 1),
            retry_after_seconds=0,
        )

    def reset(self) -> None:
        self._states.clear()

    def _state_for(self, key: str, window_index: int) -> _KeyState:
        state = self._states.get(key)

        if state is None:
            state = _KeyState(window_index=window_index, current_count=0, previous_count=0)
            self._states[key] = state
            self._evict_if_over_capacity()
        else:
            self._roll_window(state, window_index)

        self._states.move_to_end(key)

        return state

    @staticmethod
    def _roll_window(state: _KeyState, window_index: int) -> None:
        elapsed_windows = window_index - state.window_index

        if elapsed_windows <= 0:
            return

        state.previous_count = state.current_count if elapsed_windows == 1 else 0
        state.current_count = 0
        state.window_index = window_index

    def _evict_if_over_capacity(self) -> None:
        while len(self._states) > self._max_tracked_keys:
            self._states.popitem(last=False)


def _seconds_until_allowed(
    state: _KeyState,
    rule: RateLimitRule,
    elapsed_fraction: float,
) -> int:
    """When the weighted estimate drops back under the limit."""
    headroom = rule.max_requests - state.current_count

    if headroom > 0 and state.previous_count > 0:
        target_fraction = 1.0 - headroom / state.previous_count
        return _at_least_one_second((target_fraction - elapsed_fraction) * rule.window_seconds)

    remaining_window = (1.0 - elapsed_fraction) * rule.window_seconds
    decay_needed = max(0.0, 1.0 - rule.max_requests / max(state.current_count, 1))

    return _at_least_one_second(remaining_window + decay_needed * rule.window_seconds)


def _at_least_one_second(value: float) -> int:
    return max(1, math.ceil(value))
