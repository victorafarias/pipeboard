"""OAuth2 + refresh-token authentication for Google Ads API."""

from typing import Any, Dict, Optional
import json
import os
import pathlib
import time
import webbrowser
from urllib.parse import urlencode

import requests

from .utils import get_app_data_dir, logger

GOOGLE_AUTH_SCOPE = "https://www.googleapis.com/auth/adwords"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class TokenInfo:
    def __init__(
        self,
        refresh_token: str,
        access_token: Optional[str] = None,
        expires_in: Optional[int] = None,
    ):
        self.refresh_token = refresh_token
        self.access_token = access_token
        self.expires_in = expires_in
        self.created_at = int(time.time())

    def serialize(self) -> Dict[str, Any]:
        return {
            "refresh_token": self.refresh_token,
            "access_token": self.access_token,
            "expires_in": self.expires_in,
            "created_at": self.created_at,
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "TokenInfo":
        token = cls(
            refresh_token=data.get("refresh_token", ""),
            access_token=data.get("access_token"),
            expires_in=data.get("expires_in"),
        )
        token.created_at = data.get("created_at", int(time.time()))
        return token


class AuthManager:
    def __init__(self):
        self.redirect_uri = "http://localhost:8080/callback"
        self.token_info: Optional[TokenInfo] = None
        self._load_cached_token()

    def _cache_path(self):
        return get_app_data_dir() / "token_cache.json"

    def _load_cached_token(self) -> bool:
        cache_path = self._cache_path()
        if not cache_path.exists():
            return False
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not data.get("refresh_token"):
                return False
            self.token_info = TokenInfo.deserialize(data)
            logger.info("Loaded cached Google Ads refresh token")
            return True
        except Exception as e:
            logger.error(f"Error loading cached Google Ads token: {e}")
            return False

    def _save_token_to_cache(self) -> None:
        if not self.token_info:
            return
        try:
            with open(self._cache_path(), "w", encoding="utf-8") as f:
                json.dump(self.token_info.serialize(), f)
            logger.info(f"Google Ads token cached at: {self._cache_path()}")
        except Exception as e:
            logger.error(f"Error saving Google Ads token: {e}")

    def get_auth_url(self) -> str:
        client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
        params = {
            "client_id": client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": GOOGLE_AUTH_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> Optional[TokenInfo]:
        client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID", "")
        client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            logger.error("Missing GOOGLE_ADS_CLIENT_ID or GOOGLE_ADS_CLIENT_SECRET")
            return None
        response = requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": self.redirect_uri,
            },
            timeout=30,
        )
        if response.status_code != 200:
            logger.error(f"Google token exchange failed: {response.status_code} {response.text}")
            return None
        data = response.json()
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            logger.error("No refresh_token in Google OAuth response (prompt=consent required)")
            return None
        self.token_info = TokenInfo(
            refresh_token=refresh_token,
            access_token=data.get("access_token"),
            expires_in=data.get("expires_in"),
        )
        self._save_token_to_cache()
        return self.token_info

    def get_refresh_token(self) -> Optional[str]:
        env_token = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN")
        if env_token:
            return env_token
        if self.token_info and self.token_info.refresh_token:
            return self.token_info.refresh_token
        return None

    def invalidate_token(self) -> None:
        self.token_info = None
        try:
            cache_path = self._cache_path()
            if cache_path.exists():
                cache_path.unlink()
        except Exception as e:
            logger.error(f"Error removing Google Ads token cache: {e}")


auth_manager = AuthManager()


async def get_current_access_token() -> Optional[str]:
    """Return the current Google Ads OAuth refresh token.

    Named access_token to match the Meta MCP decorator/HTTP-auth pattern.
    Google Ads uses a refresh token (plus developer token + client credentials)
    rather than a single Graph-style access token.
    """
    return auth_manager.get_refresh_token()


def get_google_ads_config(refresh_token: Optional[str] = None) -> Dict[str, Any]:
    token = refresh_token or auth_manager.get_refresh_token()
    config: Dict[str, Any] = {
        "developer_token": os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
        "client_id": os.environ.get("GOOGLE_ADS_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_ADS_CLIENT_SECRET", ""),
        "refresh_token": token or "",
        "use_proto_plus": True,
    }
    login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")
    if login_customer_id:
        config["login_customer_id"] = login_customer_id.replace("-", "").strip()
    return config


def is_configured(refresh_token: Optional[str] = None) -> bool:
    config = get_google_ads_config(refresh_token)
    return bool(
        config.get("developer_token")
        and config.get("client_id")
        and config.get("client_secret")
        and config.get("refresh_token")
    )


def login():
    """CLI helper: open a browser for Google OAuth and wait for the callback."""
    from .callback_server import start_callback_server, wait_for_code

    print("Starting Google Ads authentication flow...")
    try:
        port = start_callback_server()
    except Exception as e:
        print(f"Error starting callback server: {e}")
        print("Set GOOGLE_ADS_REFRESH_TOKEN instead, or run this on a machine with a browser.")
        return
    auth_manager.redirect_uri = f"http://localhost:{port}/callback"
    auth_url = auth_manager.get_auth_url()
    print(f"Opening browser with URL: {auth_url}")
    webbrowser.open(auth_url)
    code = wait_for_code(timeout=300)
    if not code:
        print("Authentication timed out. Please try again.")
        return
    token_info = auth_manager.exchange_code(code)
    if token_info:
        _write_refresh_token_to_dotenv(token_info.refresh_token)
        print("Authentication successful. Refresh token saved to token cache and .env.")
    else:
        print("Failed to exchange authorization code for a refresh token.")


def _write_refresh_token_to_dotenv(refresh_token: str) -> None:
    env_path = pathlib.Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        env_path.write_text(f"GOOGLE_ADS_REFRESH_TOKEN={refresh_token}\n", encoding="utf-8")
        return
    text = env_path.read_text(encoding="utf-8")
    if "GOOGLE_ADS_REFRESH_TOKEN=" in text:
        lines = []
        for line in text.splitlines(keepends=True):
            if line.startswith("GOOGLE_ADS_REFRESH_TOKEN="):
                newline = "\n" if line.endswith("\n") else ""
                lines.append(f"GOOGLE_ADS_REFRESH_TOKEN={refresh_token}{newline}")
            else:
                lines.append(line)
        env_path.write_text("".join(lines), encoding="utf-8")
    else:
        env_path.write_text(text.rstrip() + f"\nGOOGLE_ADS_REFRESH_TOKEN={refresh_token}\n", encoding="utf-8")
    print(f"Wrote GOOGLE_ADS_REFRESH_TOKEN to {env_path}")
