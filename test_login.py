"""
Firebase login debug script - tests with certifi SSL and verify=False fallback.
"""

import sys
import certifi
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

API_KEY = "AIzaSyBtReTuUDI5EWyThJysJZ3YnRlWvmufRGo"
EMAIL = "yohanesnzzz777@gmail.com"
PASSWORD = "12345678910"

SIGNIN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"

def attempt(label, **kwargs):
    print(f"\n[{label}]")
    try:
        resp = requests.post(
            SIGNIN_URL,
            params={"key": API_KEY},
            json={"email": EMAIL, "password": PASSWORD, "returnSecureToken": True},
            timeout=10,
            **kwargs,
        )
        print(f"  Status : {resp.status_code}")
        data = resp.json()
        if resp.ok:
            print(f"  Result : SUCCESS")
            print(f"  Email  : {data.get('email')}")
            print(f"  Token  : {data.get('idToken','')[:60]}...")
            return True
        else:
            err = data.get("error", {})
            print(f"  Error  : {err.get('message')}")
            print(f"  Reason : {err.get('errors')}")
            print(f"  Detail : {data}")
    except Exception as e:
        print(f"  Exception: {e}")
    return False

print("=" * 60)
print(f"API Key  : {API_KEY}")
print(f"Email    : {EMAIL}")
print(f"Python   : {sys.version}")
print(f"certifi  : {certifi.where()}")
print("=" * 60)

# Try 1: certifi bundle
if attempt("certifi SSL verify", verify=certifi.where()):
    sys.exit(0)

# Try 2: verify=False (bypass SSL entirely)
if attempt("SSL verify=False", verify=False):
    sys.exit(0)

# Try 3: system default
if attempt("system default SSL", verify=True):
    sys.exit(0)

print("\nAll attempts failed. The issue is the API key itself, not SSL.")
print("Action needed: In Google Cloud Console, go to APIs & Services > Credentials")
print("  - Remove all Application restrictions from the API key")
print("  - Remove all API restrictions (or add Identity Toolkit API)")
print("  OR create a new unrestricted key and paste it here.")
