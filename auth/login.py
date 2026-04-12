"""
auth/login.py - Authentication and session management for Synthex.
Supports Firebase Auth and Google OAuth via gspread/google-auth.
"""

import os
import json
import ssl
import certifi
import requests
import urllib3
from core.config import Config
from core.logger import get_logger

ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_AUTH_DIR = os.path.dirname(os.path.abspath(__file__))
_TOKEN_FILE = os.path.join(_AUTH_DIR, "token.json")

FIREBASE_SIGNIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
)


def firebase_login(username: str, password: str, api_key: str = "AIzaSyBtReTuUDI5EWyThJysJZ3YnRlWvmufRGo") -> bool:
    """POST to Firebase Auth REST API. Returns True on success, False on failure."""
    email = username if "@" in username else username + "@gmail.com"
    try:
        resp = requests.post(
            FIREBASE_SIGNIN_URL,
            params={"key": api_key},
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=10,
            verify=False,
        )
        resp.raise_for_status()
        data = resp.json()
        token_data = {
            "idToken": data.get("idToken"),
            "refreshToken": data.get("refreshToken"),
            "email": data.get("email"),
            "expiresIn": data.get("expiresIn"),
        }
        with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2)
        return True
    except Exception:
        return False


class AuthManager:
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger("auth")
        self._token: str | None = config.get("auth.token") or None
        self._google_client = None

    def login(self, username: str = None, password: str = None) -> bool:
        username = username or self.config.get("auth.username", "")
        password = password or self.config.get("auth.password", "")
        if not username or not password:
            self.logger.warning("Login skipped: no credentials configured.")
            return False

        api_key = self.config.get("firebase.api_key", "AIzaSyBtReTuUDI5EWyThJysJZ3YnRlWvmufRGo")
        self.logger.info(f"Logging in as: {username}")
        success = firebase_login(username, password, api_key)
        if success:
            with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
                self._token = json.load(f).get("idToken")
            self.logger.info("Login successful.")
        else:
            self.logger.warning("Login failed.")
        return success

    def logout(self):
        self._token = None
        if os.path.exists(_TOKEN_FILE):
            os.remove(_TOKEN_FILE)
        self.logger.info("Logged out.")

    def get_token(self) -> str | None:
        return self._token

    def is_authenticated(self) -> bool:
        return self._token is not None

    # --- Google auth ---

    def get_google_client(self):
        if self._google_client is not None:
            return self._google_client

        import gspread
        from google.oauth2.service_account import Credentials

        creds_file = self.config.get("google.credentials_file", "auth/google_credentials.json")
        if not os.path.exists(creds_file):
            raise FileNotFoundError(
                f"Google credentials not found: {creds_file}\n"
                "Download a service account JSON from Google Cloud Console."
            )

        creds = Credentials.from_service_account_file(creds_file, scopes=GOOGLE_SCOPES)
        self._google_client = gspread.authorize(creds)
        self.logger.info("Google Sheets client authorized.")
        return self._google_client

    def get_worksheet(self, spreadsheet_id: str = None, worksheet_name: str = None):
        spreadsheet_id = spreadsheet_id or self.config.get("google.spreadsheet_id", "")
        worksheet_name = worksheet_name or self.config.get("google.worksheet_name", "Sheet1")
        client = self.get_google_client()
        sheet = client.open_by_key(spreadsheet_id)
        return sheet.worksheet(worksheet_name)
