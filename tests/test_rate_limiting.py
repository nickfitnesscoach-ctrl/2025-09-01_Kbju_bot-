"""Test rate limiting on admin panel login endpoint."""

import os
import sys
from pathlib import Path

# Add project root to path (parent of tests/ folder)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Set required environment variables for testing
os.environ["ADMIN_PASSWORD_HASH"] = "scrypt:32768:8:1$test$test123"
os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"
os.environ["WTF_CSRF_ENABLED"] = "False"  # Disable CSRF for testing
# Disable webhook to avoid config validation errors
os.environ["N8N_WEBHOOK_URL"] = ""
os.environ["N8N_WEBHOOK_SECRET"] = ""

from app.admin_panel import app


def test_login_rate_limiting():
    """Test that login endpoint is rate limited after 5 attempts."""
    app.config["WTF_CSRF_ENABLED"] = False  # Disable CSRF protection for testing
    client = app.test_client()

    print("Test rate limiting on /login endpoint...")
    print("-" * 50)

    # Attempt to login 6 times with wrong password
    results = []
    for i in range(6):
        response = client.post(
            "/login",
            data={"password": "wrong_password"},
            follow_redirects=False
        )
        results.append({
            "attempt": i + 1,
            "status_code": response.status_code,
            "rate_limited": response.status_code == 429
        })
        status_text = "(RATE LIMITED)" if response.status_code == 429 else ""
        print(f"Attempt {i + 1}: HTTP {response.status_code} {status_text}")

    # Check that first 5 attempts return 200, and 6th returns 429 (rate limited)
    successful_attempts = sum(1 for r in results[:5] if r["status_code"] == 200)
    rate_limited_attempts = sum(1 for r in results[5:] if r["rate_limited"])

    print("-" * 50)
    print(f"\nResults:")
    print(f"[OK] First 5 attempts allowed: {successful_attempts}/5")
    print(f"[OK] 6th attempt rate limited: {rate_limited_attempts}/1")

    assert successful_attempts == 5, f"First 5 attempts should be allowed, got: {successful_attempts}"
    assert rate_limited_attempts >= 1, f"6th attempt should be rate limited, got: {rate_limited_attempts}"

    print("\n[PASS] Test passed! Rate limiting works correctly.")
    print("   - Maximum 5 login attempts per minute")
    print("   - 6th attempt blocked with HTTP 429\n")


if __name__ == "__main__":
    test_login_rate_limiting()
