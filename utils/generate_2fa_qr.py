"""Generate QR code for 2FA setup."""

import os
import sys

import pyotp
import qrcode
from dotenv import load_dotenv

load_dotenv()

TOTP_SECRET = os.getenv("TOTP_SECRET")
if not TOTP_SECRET:
    print("Error: TOTP_SECRET not found in .env")
    print("\nGenerate a new secret with:")
    print("  python -c \"import pyotp; print(pyotp.random_base32())\"")
    print("\nThen add to .env:")
    print("  TOTP_SECRET=YOUR_SECRET_HERE")
    sys.exit(1)

# Create TOTP URI
app_name = "FitnessBot Admin"
totp = pyotp.TOTP(TOTP_SECRET)
provisioning_uri = totp.provisioning_uri(
    name="admin",
    issuer_name=app_name
)

print("=" * 60)
print("2FA Setup Information")
print("=" * 60)
print(f"\nTOTP URI: {provisioning_uri}")
print(f"\nManual entry key: {TOTP_SECRET}")
print("\nCurrent code (for testing):", totp.now())

# Generate QR code
qr = qrcode.QRCode(version=1, box_size=10, border=5)
qr.add_data(provisioning_uri)
qr.make(fit=True)

img = qr.make_image(fill_color="black", back_color="white")
filename = "2fa_qr_code.png"
img.save(filename)

print(f"\nQR code saved to: {filename}")
print("\nNext steps:")
print("1. Open 2fa_qr_code.png")
print("2. Scan the QR code with your authenticator app")
print("3. Enter the 6-digit code when logging in")
print("\nSupported apps:")
print("- Google Authenticator")
print("- Microsoft Authenticator")
print("- Authy")
print("- 1Password")
print("=" * 60)
