"""Feature modules for the Fitness Bot."""

from .subscription_gate import (
    CHECK_CALLBACK_DATA,
    ensure_subscription_and_continue,
    is_user_subscribed,
    should_gate,
)

__all__ = [
    "CHECK_CALLBACK_DATA",
    "ensure_subscription_and_continue",
    "is_user_subscribed",
    "should_gate",
]
