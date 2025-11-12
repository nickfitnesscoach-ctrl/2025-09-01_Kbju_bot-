"""Test security headers in admin panel."""

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
os.environ["WTF_CSRF_ENABLED"] = "False"
os.environ["USE_HTTPS"] = "False"  # Test without HTTPS first
# Disable webhook to avoid config validation errors
os.environ["N8N_WEBHOOK_URL"] = ""
os.environ["N8N_WEBHOOK_SECRET"] = ""

from app.admin_panel import app


def test_security_headers():
    """Test that security headers are present in responses."""
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    print("Test security headers...")
    print("-" * 60)

    # Test /health endpoint (no auth required)
    response = client.get("/health")

    expected_headers = {
        "X-Frame-Options": "DENY",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Content-Security-Policy": "default-src 'self'",
    }

    print(f"Status: {response.status_code}\n")
    print("Checking security headers:")

    results = []
    for header_name, expected_value in expected_headers.items():
        actual_value = response.headers.get(header_name, "")
        is_present = header_name in response.headers
        contains_expected = expected_value in actual_value if is_present else False

        status = "[OK]" if contains_expected else "[FAIL]"
        results.append({
            "name": header_name,
            "present": is_present,
            "contains_expected": contains_expected
        })

        print(f"{status} {header_name}")
        if is_present:
            print(f"     Value: {actual_value[:80]}...")

    print("\n" + "-" * 60)

    # Check HSTS header (should NOT be present when USE_HTTPS=False)
    hsts_present = "Strict-Transport-Security" in response.headers
    print(f"[OK] HSTS header correctly {'absent' if not hsts_present else 'present'} (USE_HTTPS=False)")

    # Count results
    passed = sum(1 for r in results if r["contains_expected"])
    total = len(results)

    print(f"\nResults: {passed}/{total} headers configured correctly")

    # Assert all headers are present
    assert passed == total, f"Expected all {total} headers, but only {passed} are correct"
    assert not hsts_present, "HSTS header should not be present when USE_HTTPS=False"

    print("\n[PASS] All security headers configured correctly!\n")


def test_https_mode_headers():
    """Test that HSTS header is present when USE_HTTPS=True."""
    os.environ["USE_HTTPS"] = "True"

    # Need to reload the module to pick up new env var
    import importlib
    import app.admin_panel as admin_module
    importlib.reload(admin_module)

    test_app = admin_module.app
    test_app.config["WTF_CSRF_ENABLED"] = False
    client = test_app.test_client()

    print("\nTest HTTPS mode (USE_HTTPS=True)...")
    print("-" * 60)

    response = client.get("/health")

    hsts_header = response.headers.get("Strict-Transport-Security", "")
    hsts_present = bool(hsts_header)

    print(f"[{'OK' if hsts_present else 'FAIL'}] HSTS header present: {hsts_present}")
    if hsts_present:
        print(f"     Value: {hsts_header}")

    # Check for max-age
    has_max_age = "max-age=31536000" in hsts_header
    print(f"[{'OK' if has_max_age else 'FAIL'}] HSTS max-age=31536000: {has_max_age}")

    # Check for includeSubDomains
    has_subdomains = "includeSubDomains" in hsts_header
    print(f"[{'OK' if has_subdomains else 'FAIL'}] HSTS includeSubDomains: {has_subdomains}")

    assert hsts_present, "HSTS header must be present when USE_HTTPS=True"
    assert has_max_age, "HSTS must include max-age=31536000"
    assert has_subdomains, "HSTS must include includeSubDomains"

    print("\n[PASS] HTTPS mode headers configured correctly!\n")


if __name__ == "__main__":
    test_security_headers()
    test_https_mode_headers()
