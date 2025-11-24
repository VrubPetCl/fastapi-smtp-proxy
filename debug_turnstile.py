#!/usr/bin/env python3
"""Debug script to verify Turnstile configuration and template rendering."""

import sys
from app.config import settings

def main():
    print("=" * 70)
    print("CLOUDFLARE TURNSTILE CONFIGURATION CHECK")
    print("=" * 70)

    print("\n1. Environment Variables:")
    print(f"   CF_TURNSTILE_SITE_KEY: {settings.cf_turnstile_site_key or '(not set)'}")
    print(f"   CF_TURNSTILE_SECRET_KEY: {settings.cf_turnstile_secret_key or '(not set)'}")

    print("\n2. Configuration Status:")
    print(f"   Turnstile Enabled: {settings.turnstile_enabled}")

    if not settings.turnstile_enabled:
        print("\n   ⚠️  Turnstile is DISABLED")
        print("   Reason: Environment variables are not set")
        print("\n   To enable:")
        print("   1. Add to .env file:")
        print("      CF_TURNSTILE_SITE_KEY=your_site_key")
        print("      CF_TURNSTILE_SECRET_KEY=your_secret_key")
        print("   2. Restart the application")
    else:
        print("\n   ✓ Turnstile is ENABLED")
        print(f"   Site Key (first 10 chars): {settings.cf_turnstile_site_key[:10]}...")
        print(f"   Secret Key (first 10 chars): {settings.cf_turnstile_secret_key[:10]}...")

    print("\n3. Template Variables:")
    print("   When rendering login.html, these values are passed:")
    print(f"   - turnstile_enabled: {settings.turnstile_enabled}")
    print(f"   - turnstile_site_key: {settings.cf_turnstile_site_key or '(empty)'}")

    print("\n4. Expected HTML Output:")
    if settings.turnstile_enabled:
        print("   ✓ Turnstile SDK will be loaded:")
        print('     <script src="https://challenges.cloudflare.com/turnstile/v0/api.js" async defer></script>')
        print("\n   ✓ Turnstile widget will be rendered:")
        print(f'     <div class="cf-turnstile" data-sitekey="{settings.cf_turnstile_site_key}" data-theme="light"></div>')
        print("\n   ✓ Form will include hidden field after challenge:")
        print('     <input type="hidden" name="cf-turnstile-response" value="TOKEN">')
    else:
        print("   ✗ No Turnstile elements will be rendered")
        print("   ✗ Login will work WITHOUT captcha verification")

    print("\n5. Backend Verification:")
    if settings.turnstile_enabled:
        print("   ✓ POST /admin/login will REQUIRE cf-turnstile-response field")
        print("   ✓ Token will be verified with Cloudflare API")
        print("   ✓ Login will fail if captcha is missing or invalid")
    else:
        print("   - POST /admin/login will NOT require captcha")
        print("   - cf-turnstile-response field is optional")

    print("\n6. Testing Steps:")
    print("   1. Open browser to: http://localhost:8000/admin/login")
    print("   2. Open browser DevTools (F12) → Network tab")
    print("   3. Refresh the page")
    print("   4. Check:")
    if settings.turnstile_enabled:
        print("      - Should see request to challenges.cloudflare.com")
        print("      - Should see Turnstile widget on page")
        print("      - Inspect form HTML for cf-turnstile div")
    else:
        print("      - Should NOT see any Cloudflare requests")
        print("      - Should NOT see Turnstile widget")
    print("   5. Fill username/password and submit")
    print("   6. Check form data in Network tab → Payload:")
    if settings.turnstile_enabled:
        print("      - Should include: cf-turnstile-response")
    else:
        print("      - Will NOT include: cf-turnstile-response")

    print("\n" + "=" * 70)

    return 0 if settings.turnstile_enabled else 1

if __name__ == "__main__":
    sys.exit(main())
