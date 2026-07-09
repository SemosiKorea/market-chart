from __future__ import annotations

import argparse

import httpx

from market_signal.config import load_settings
from market_signal.providers.kis.auth import KISAuthClient, KISAuthError
from market_signal.security import mask_secret


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a non-ordering KIS auth smoke test against the configured environment."
    )
    parser.add_argument(
        "--skip-websocket",
        action="store_true",
        help="Only request a REST access token; skip WebSocket approval key issuance.",
    )
    parser.add_argument(
        "--refresh-token",
        action="store_true",
        help="Ignore the local access token cache and request a fresh REST token.",
    )
    args = parser.parse_args()

    settings = load_settings()

    try:
        settings.require_kis_credentials()
        with httpx.Client(timeout=settings.kis_timeout_seconds) as http_client:
            client = KISAuthClient(settings=settings, http_client=http_client)
            token = client.issue_access_token_cached(refresh=args.refresh_token)
            print("KIS REST token: OK")
            print(f"  token_type: {token.token_type}")
            print(f"  expires_in: {token.expires_in}")
            print(f"  token: {mask_secret(token.access_token)}")

            if not args.skip_websocket:
                approval = client.issue_approval_key()
                print("KIS WebSocket approval key: OK")
                print(f"  approval_key: {mask_secret(approval.approval_key)}")

        print("No order API was called.")
        return 0
    except (ValueError, KISAuthError, httpx.HTTPError) as exc:
        print(f"KIS auth smoke test failed: {exc}")
        print("No order API was called.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
