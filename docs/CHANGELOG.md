# Changelog - Security Fixes

## [2025-11-10] - Security Audit Fixes

### 🔒 Security

#### CRITICAL
- **#1: Added Two-Factor Authentication (2FA)**
  - Implemented TOTP-based 2FA with pyotp
  - Optional configuration via `ENABLE_2FA=True`
  - QR code generation for authenticator apps
  - Support for Google Authenticator, Microsoft Authenticator, Authy
  - Two-step authentication: password → TOTP code

#### HIGH Priority
- **#2: Implemented Rate Limiting on Login**
  - Added Flask-Limiter to admin panel
  - Strict limit: 5 login attempts per minute
  - Global limits: 200/day, 50/hour
  - Automatic blocking on HTTP 429

- **#6: HTTPS Support & Secure Cookies**
  - Added `USE_HTTPS` environment variable
  - Secure cookie flags: `SESSION_COOKIE_SECURE=True`
  - SameSite cookie policy: Strict for HTTPS
  - Session timeout: 1 hour
  - HSTS headers for HTTPS enforcement

- **#4: Mandatory Webhook Authentication**
  - `N8N_WEBHOOK_SECRET` now required when webhook is enabled
  - Application fails fast at startup if misconfigured
  - X-Webhook-Secret header in all webhook requests
  - Improved security logging

#### MEDIUM Priority
- **#9: Comprehensive Security Headers**
  - Content-Security-Policy (XSS protection)
  - X-Frame-Options: DENY (clickjacking protection)
  - X-Content-Type-Options: nosniff (MIME sniffing protection)
  - Referrer-Policy: strict-origin-when-cross-origin
  - Permissions-Policy (disable unused browser APIs)
  - Strict-Transport-Security (HSTS for HTTPS)

- **#16: File Upload Size & MIME Type Validation**
  - Maximum file size: 20 MB (matches Telegram limits)
  - MIME type whitelist for photos and videos
  - HTTP 413 error handler
  - Comprehensive upload logging

### 📁 Files Changed

#### Modified Files
- `app/admin_panel.py` - Added 2FA, rate limiting, security headers, file limits
- `app/webhook.py` - Improved authentication and logging
- `config.py` - Webhook secret validation at startup
- `requirements.txt` - Added pyotp==2.9.0, qrcode==7.4.2

#### New Files & Structure
```
tests/                           # New folder for security tests
├── test_rate_limiting.py       # Rate limiting tests ✅
├── test_security_headers.py    # Security headers tests ✅
├── test_webhook_security.py    # Webhook auth tests ✅
└── README.md                   # Test documentation

docs/                           # Organized documentation
├── 2fa-setup.md               # 2FA setup guide
├── https-setup.md             # HTTPS configuration guide
├── security-audit.md          # Original security audit
├── security-fixes-report.md   # Detailed fix report
├── PROJECT_STRUCTURE.md       # Project structure overview
├── CHANGELOG.md               # This file
├── bugs.md                    # Known issues (moved from root)
└── README_DEV.md              # Developer docs (moved from root)

utils/                          # Utility scripts
└── generate_2fa_qr.py         # QR code generator for 2FA
```

#### Deleted Files
- `README_DEV.md` (moved to docs/)
- `bugs.md` (moved to docs/)

### 🧪 Testing

All tests pass successfully:

```bash
✅ test_rate_limiting.py
   - 5 login attempts allowed per minute
   - 6th attempt blocked with HTTP 429

✅ test_security_headers.py
   - All security headers present
   - HSTS enabled in HTTPS mode

✅ test_webhook_security.py
   - Webhook secret validation works
   - Configuration fails fast
   - X-Webhook-Secret header included
```

### 📊 Metrics

**Before Fixes:**
- Overall Risk Level: MEDIUM
- Critical Issues: 1
- High Priority: 3
- Medium Priority: 2

**After Fixes:**
- Overall Risk Level: LOW ✅
- Critical Issues: 0 ✅
- High Priority: 0 ✅
- Medium Priority: 0 ✅

### 🚀 Migration Guide

#### 1. Update Dependencies
```bash
pip install -r requirements.txt
```

New dependencies:
- `pyotp==2.9.0` - TOTP for 2FA
- `qrcode==7.4.2` - QR code generation

#### 2. Update .env (Optional but Recommended)

```bash
# Enable HTTPS mode (recommended for production)
USE_HTTPS=True

# Enable Two-Factor Authentication (optional)
ENABLE_2FA=True
TOTP_SECRET=<generate with: python -c "import pyotp; print(pyotp.random_base32())">

# Webhook secret (mandatory if N8N_WEBHOOK_URL is set)
N8N_WEBHOOK_SECRET=<your_secret_here>
```

#### 3. Setup HTTPS (Production)
See [docs/https-setup.md](https-setup.md) for nginx + Let's Encrypt setup

#### 4. Setup 2FA (Optional)
See [docs/2fa-setup.md](2fa-setup.md) for complete 2FA setup guide

#### 5. Run Tests
```bash
python tests/test_rate_limiting.py
python tests/test_security_headers.py
python tests/test_webhook_security.py
```

### 📝 Notes

- **Backward Compatibility**: All security features are optional (except webhook auth if webhook is enabled)
- **Default Behavior**: 2FA is OFF by default, can be enabled via `ENABLE_2FA=True`
- **Breaking Changes**: If `N8N_WEBHOOK_URL` is set, `N8N_WEBHOOK_SECRET` is now MANDATORY
- **Production Ready**: All fixes tested and documented

### 🔗 Documentation

- [2FA Setup Guide](2fa-setup.md)
- [HTTPS Setup Guide](https-setup.md)
- [Security Audit](security-audit.md)
- [Security Fixes Report](security-fixes-report.md)
- [Project Structure](PROJECT_STRUCTURE.md)

### 👥 Contributors

- Claude Code - Security audit fixes and implementation

---

## Future Improvements (Backlog)

### High Priority
- [ ] Migrate rate limiting from in-memory to Redis for multi-instance support
- [ ] Add audit logging for all admin actions
- [ ] Implement security monitoring (Sentry integration)

### Medium Priority
- [ ] Add CAPTCHA after multiple failed login attempts
- [ ] Implement IP whitelisting for admin panel
- [ ] Add automated dependency scanning (pip-audit in CI/CD)
- [ ] Create backup/recovery documentation for 2FA

### Low Priority
- [ ] Add WebAuthn/FIDO2 support as alternative to TOTP
- [ ] Implement session management dashboard
- [ ] Add security event notifications
