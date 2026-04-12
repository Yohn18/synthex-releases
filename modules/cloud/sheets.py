# -*- coding: utf-8 -*-
"""
modules/cloud/sheets.py - Google Sheets integration for Synthex.
Uses gspread with a service account credentials file.
"""

import datetime
import os

from core.config import Config
from core.logger import get_logger


class SheetsSync:
    def __init__(self, config: Config):
        self.config = config
        self.logger = get_logger("sheets")
        self._client = None

    # -- Internal --
    def _get_client(self):
        if self._client is not None:
            return self._client
        import gspread
        from google.oauth2.service_account import Credentials

        creds_file = self.config.get(
            "google.credentials_file", "auth/google_credentials.json"
        )
        if not os.path.isabs(creds_file):
            base = os.path.join(os.path.dirname(__file__), "..", "..")
            creds_file = os.path.abspath(os.path.join(base, creds_file))

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_file(creds_file, scopes=scopes)
        self._client = gspread.authorize(creds)
        self.logger.info("Google Sheets client authorised.")
        return self._client

    def _worksheet(self, sheet_id: str):
        worksheet_name = self.config.get("google.worksheet_name", "Sheet1")
        return self._get_client().open_by_key(sheet_id).worksheet(worksheet_name)

    # -- Public API --
    def write_row(self, sheet_id: str, data: list) -> bool:
        """Append a single row to the Google Sheet identified by sheet_id."""
        try:
            self._worksheet(sheet_id).append_row(data)
            self.logger.info(f"Row written to {sheet_id}: {data}")
            return True
        except Exception as e:
            self.logger.error(f"write_row failed: {e}")
            return False

    def write_data(self, sheet_id: str, data_list: list) -> bool:
        """Append multiple rows to the Google Sheet identified by sheet_id."""
        try:
            self._worksheet(sheet_id).append_rows(data_list)
            self.logger.info(f"Wrote {len(data_list)} rows to {sheet_id}")
            return True
        except Exception as e:
            self.logger.error(f"write_data failed: {e}")
            return False

    def test_connection(self, sheet_id: str) -> str:
        """Write a test row and return a status message."""
        test_row = ["Synthex Test", datetime.datetime.now().isoformat(), "Connection OK"]
        success = self.write_row(sheet_id, test_row)
        if success:
            return "Connection OK  -  test row written successfully."
        return "Connection FAILED  -  check credentials file and Sheet ID."
