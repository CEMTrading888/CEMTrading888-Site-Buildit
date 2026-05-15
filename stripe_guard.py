"""
Stripe: TEST mode only until attorney approves and the platform is ready to sell.

- Publishable keys must be pk_test_…
- Secret keys must be sk_test_…
- Local / QA card: 4242 4242 4242 4242 (any future exp, any CVC)

Call assert_stripe_test_mode_only() on app startup after load_dotenv().
Live keys (pk_live_ / sk_live_) raise RuntimeError so they cannot run by accident.
"""
from __future__ import annotations

import os


def assert_stripe_test_mode_only() -> None:
    pub = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()
    sec = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not pub and not sec:
        return
    if pub.startswith("pk_live_") or sec.startswith("sk_live_"):
        raise RuntimeError(
            "Stripe live keys are disabled. Use test keys only (pk_test_… / sk_test_…) until attorney approves."
        )
    if pub and not pub.startswith("pk_test_"):
        raise RuntimeError("STRIPE_PUBLISHABLE_KEY must be a test key (pk_test_…).")
    if sec and not sec.startswith("sk_test_"):
        raise RuntimeError("STRIPE_SECRET_KEY must be a test key (sk_test_…).")
