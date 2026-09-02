"""OAuth2 + access/refresh token authentication for TikTok Marketing API."""

from typing import Any, Dict, Optional
import json
import os
import time
import webbrowser
from urllib.parse import urlencode

import requests

from .utils import get_app_data_dir, logger

TIKTOK_AUTH_URL = "https://business-api.tiktok.com/portal/auth"
TIKTOK_TOKEN_URL = "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/"
TIKTOK_REFRESH_URL = "https://business-api.tiktok.com/open_api/v1.3/oauth2/refresh_token/"


class TokenInfo:
    def __init__(
        self,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[int] = None,
        advertiser_ids: Optional[list] = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in or 86400
        self.advertiser_ids = advertiser_ids or []
        self.created_at = int(time.time())

    def is_expired(self, skew_seconds: int = 300) -> bool:
        return int(time.time()) >= (self.created_at + int(self.expires_in) - skew_seconds)

    def serialize(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": self.expires_in,
            "advertiser_ids": self.advertiser_ids,
            "created_at": self.created_at,
        }

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "TokenInfo":
        token = cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in"),
            advertiser_ids=data.get("advertiser_ids"),
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
            if not data.get("access_token") and not data.get("refresh_token"):
                return False
            self.token_info = TokenInfo.deserialize(data)
            logger.info("Loaded cached TikTok Ads token")
            return True
        except Exception as e:
            logger.error(f"Error loading cached TikTok token: {e}")
            return False

    def _save_token_to_cache(self) -> None:
        if not self.token_info:
            return
        try:
            with open(self._cache_path(), "w", encoding="utf-8") as f:
                json.dump(self.token_info.serialize(), f)
            logger.info(f"TikTok token cached at: {self._cache_path()}")
        except Exception as e:
            logger.error(f"Error saving TikTok token: {e}")

    def get_auth_url(self) -> str:
        app_id = os.environ.get("TIKTOK_APP_ID", "")
        params = {
            "app_id": app_id,
            "state": "tiktok-ads-mcp",
            "redirect_uri": self.redirect_uri,
        }
        return f"{TIKTOK_AUTH_URL}?{urlencode(params)}"

    def _store_from_api(self, payload: Dict[str, Any]) -> Optional[TokenInfo]:
        data = payload.get("data") or payload
        access_token = data.get("access_token")
        if not access_token:
            logger.error(f"TikTok token response missing access_token: {payload}")
            return None
        self.token_info = TokenInfo(
            access_token=access_token,
            refresh_token=data.get("refresh_token") or os.environ.get("TIKTOK_REFRESH_TOKEN"),
            expires_in=data.get("expires_in"),
            advertiser_ids=data.get("advertiser_ids"),
        )
        self._save_token_to_cache()
        return self.token_info

    def exchange_code(self, code: str) -> Optional[TokenInfo]:
        app_id = os.environ.get("TIKTOK_APP_ID", "")
        secret = os.environ.get("TIKTOK_APP_SECRET", "")
        if not app_id or not secret:
            logger.error("Missing TIKTOK_APP_ID or TIKTOK_APP_SECRET")
            return None
        response = requests.post(
            TIKTOK_TOKEN_URL,
            json={"app_id": app_id, "secret": secret, "auth_code": code},
            timeout=30,
        )
        if response.status_code != 200:
            logger.error(f"TikTok token exchange failed: {response.status_code} {response.text}")
            return None
        return self._store_from_api(response.json())

    def refresh_access_token(self) -> Optional[TokenInfo]:
        refresh_token = (
            (self.token_info.refresh_token if self.token_info else None)
            or os.environ.get("TIKTOK_REFRESH_TOKEN")
        )
        app_id = os.environ.get("TIKTOK_APP_ID", "")
        secret = os.environ.get("TIKTOK_APP_SECRET", "")
        if not refresh_token or not app_id or not secret:
            logger.warning("Cannot refresh TikTok token — missing refresh_token or app credentials")
            return None
        response = requests.post(
            TIKTOK_REFRESH_URL,
            json={"app_id": app_id, "secret": secret, "refresh_token": refresh_token},
            timeout=30,
        )
        if response.status_code != 200:
            logger.error(f"TikTok token refresh failed: {response.status_code} {response.text}")
            return None
        payload = response.json()
        if payload.get("code") not in (0, None) and payload.get("code") != 0:
            # TikTok success is code == 0
            if payload.get("code") != 0:
                logger.error(f"TikTok token refresh API error: {payload}")
                return None
        return self._store_from_api(payload)

    def get_access_token(self) -> Optional[str]:
        env_token = os.environ.get("TIKTOK_ACCESS_TOKEN")
        if env_token:
            return env_token
        if self.token_info:
            if self.token_info.is_expired():
                refreshed = self.refresh_access_token()
                if refreshed:
                    return refreshed.access_token
            if self.token_info.access_token:
                return self.token_info.access_token
        if os.environ.get("TIKTOK_REFRESH_TOKEN"):
            refreshed = self.refresh_access_token()
            if refreshed:
                return refreshed.access_token
        return None

    def invalidate_token(self) -> None:
        self.token_info = None
        try:
            cache_path = self._cache_path()
            if cache_path.exists():
                cache_path.unlink()
        except Exception as e:
            logger.error(f"Error removing TikTok token cache: {e}")


auth_manager = AuthManager()


async def get_current_access_token() -> Optional[str]:
    return auth_manager.get_access_token()


def is_configured(access_token: Optional[str] = None) -> bool:
    if access_token:
        return True
    return bool(auth_manager.get_access_token())


def login():
    from .callback_server import start_callback_server, wait_for_code

    print("Starting TikTok Ads authentication flow...")
    try:
        port = start_callback_server()
    except Exception as e:
        print(f"Error starting callback server: {e}")
        print("Set TIKTOK_ACCESS_TOKEN / TIKTOK_REFRESH_TOKEN instead.")
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
        print("Authentication successful. Access token saved.")
    else:
        print("Failed to exchange authorization code for a TikTok access token.")
