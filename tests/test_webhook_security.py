"""Test webhook security validation."""

import os
import sys
from pathlib import Path

# Add project root to path (parent of tests/ folder)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def test_webhook_validation_without_secret():
    """Test that config raises error when webhook URL is set but secret is missing."""
    print("Test 1: Webhook URL without secret (should fail)...")
    print("-" * 60)

    # Set environment: URL without secret (BEFORE clearing modules)
    os.environ["N8N_WEBHOOK_URL"] = "https://example.com/webhook"
    os.environ.pop("N8N_WEBHOOK_SECRET", None)  # Ensure secret is not set
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"

    # Clear existing config AFTER setting environment
    for key in list(sys.modules.keys()):
        if key.startswith("config"):
            del sys.modules[key]

    try:
        import config  # This should raise RuntimeError
        print("[FAIL] Expected RuntimeError but none was raised")
        print("       Config loaded without webhook secret validation")
        assert False, "Expected RuntimeError when webhook URL is set without secret"
    except RuntimeError as exc:
        error_message = str(exc)
        print(f"[OK] RuntimeError raised as expected")
        print(f"     Message: {error_message[:100]}...")

        # Verify error message mentions security
        assert "Security Error" in error_message, "Error should mention security"
        assert "N8N_WEBHOOK_SECRET" in error_message, "Error should mention N8N_WEBHOOK_SECRET"
        print("[OK] Error message contains security warning")

    print("\n[PASS] Webhook validation correctly blocks missing secret\n")


def test_webhook_validation_with_secret():
    """Test that config loads successfully when both URL and secret are set."""
    print("Test 2: Webhook URL with secret (should succeed)...")
    print("-" * 60)

    # Set environment: URL with secret (BEFORE clearing modules)
    os.environ["N8N_WEBHOOK_URL"] = "https://example.com/webhook"
    os.environ["N8N_WEBHOOK_SECRET"] = "my_secure_secret_123"
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"

    # Clear existing config AFTER setting environment
    for key in list(sys.modules.keys()):
        if key.startswith("config"):
            del sys.modules[key]

    try:
        import config  # This should succeed
        print(f"[OK] Config loaded successfully")
        print(f"     Webhook URL: {config.N8N_WEBHOOK_URL}")
        print(f"     Webhook Secret: {'*' * len(config.N8N_WEBHOOK_SECRET)}")

        assert config.N8N_WEBHOOK_URL == "https://example.com/webhook"
        assert config.N8N_WEBHOOK_SECRET == "my_secure_secret_123"
        print("[OK] Webhook configuration correct")

    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}")
        raise

    print("\n[PASS] Webhook validation allows URL with secret\n")


def test_webhook_validation_no_url():
    """Test that config loads successfully when webhook URL is not set."""
    print("Test 3: No webhook URL (should succeed)...")
    print("-" * 60)

    # Set environment: No webhook URL (BEFORE clearing modules)
    # Must set empty string to override .env file values
    os.environ["N8N_WEBHOOK_URL"] = ""
    os.environ["N8N_WEBHOOK_SECRET"] = ""
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"

    # Clear existing config AFTER setting environment
    for key in list(sys.modules.keys()):
        if key.startswith("config"):
            del sys.modules[key]

    try:
        import config  # This should succeed
        print(f"[OK] Config loaded successfully")
        print(f"     Webhook URL: '{config.N8N_WEBHOOK_URL}' (empty)")
        print(f"     Webhook Secret: '{config.N8N_WEBHOOK_SECRET}' (empty)")

        assert config.N8N_WEBHOOK_URL == ""
        print("[OK] Webhook disabled correctly")

    except Exception as exc:
        print(f"[FAIL] Unexpected error: {exc}")
        raise

    print("\n[PASS] Config loads successfully without webhook\n")


def test_webhook_headers():
    """Test that webhook headers include authentication."""
    print("Test 4: Webhook headers include authentication...")
    print("-" * 60)

    # Set environment with webhook (BEFORE clearing modules)
    os.environ["N8N_WEBHOOK_URL"] = "https://example.com/webhook"
    os.environ["N8N_WEBHOOK_SECRET"] = "test_secret_456"
    os.environ["TELEGRAM_BOT_TOKEN"] = "test_token"

    # Clear existing config AFTER setting environment
    for key in list(sys.modules.keys()):
        if key.startswith("config") or key.startswith("app.webhook"):
            del sys.modules[key]

    from app.webhook import _build_headers

    headers = _build_headers()

    print(f"Headers built: {list(headers.keys())}")

    assert "X-Webhook-Secret" in headers, "X-Webhook-Secret header must be present"
    assert headers["X-Webhook-Secret"] == "test_secret_456"
    print(f"[OK] X-Webhook-Secret header present")
    print(f"     Value: {'*' * len(headers['X-Webhook-Secret'])}")

    assert headers["Content-Type"] == "application/json"
    print(f"[OK] Content-Type header correct")

    print("\n[PASS] Webhook headers include authentication\n")


if __name__ == "__main__":
    test_webhook_validation_without_secret()
    test_webhook_validation_with_secret()
    test_webhook_validation_no_url()
    test_webhook_headers()

    print("=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)
    print("\nSummary:")
    print("- Webhook security validation is working correctly")
    print("- N8N_WEBHOOK_SECRET is now mandatory when webhook is enabled")
    print("- Webhook requests include X-Webhook-Secret header")
    print("- Configuration fails fast at startup if security is misconfigured")
