from __future__ import annotations

import argparse
import hmac
import json
from pathlib import Path

import keyring


EXPECTED_BACKEND = "keyring.backends.Windows.WinVaultKeyring"
DEFAULT_SERVICE = "Halpha/Binance/BINANCE_DEMO"
KEY_ACCOUNT = "api_key"
SECRET_ACCOUNT = "api_secret"


class CredentialImportError(Exception):
    """An import failure whose message is guaranteed not to contain a secret."""


def _normalize_label(value: str) -> str:
    return value.strip().rstrip(":=").casefold().replace("-", "_").replace(" ", "_")


def _read_source(source: Path) -> tuple[str, str]:
    try:
        lines = [line.strip() for line in source.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    except OSError as exc:
        raise CredentialImportError(f"SOURCE_READ_FAILED:{type(exc).__name__}") from None

    if len(lines) != 4:
        raise CredentialImportError("SOURCE_FORMAT_UNSUPPORTED")
    key_label, api_key, secret_label, api_secret = lines
    if _normalize_label(key_label) not in {"api", "key", "api_key", "apikey"}:
        raise CredentialImportError("SOURCE_KEY_LABEL_UNSUPPORTED")
    if _normalize_label(secret_label) not in {"secret", "api_secret", "apisecret"}:
        raise CredentialImportError("SOURCE_SECRET_LABEL_UNSUPPORTED")

    for value in (api_key, api_secret):
        if not value.isascii() or not 32 <= len(value) <= 256 or any(character.isspace() for character in value):
            raise CredentialImportError("SOURCE_VALUE_SHAPE_INVALID")
    return api_key, api_secret


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Binance Demo credentials into Windows Vault without echoing values.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    args = parser.parse_args()

    backend = keyring.get_keyring()
    backend_name = f"{type(backend).__module__}.{type(backend).__qualname__}"
    if backend_name != EXPECTED_BACKEND:
        raise CredentialImportError("KEYRING_BACKEND_MISMATCH")

    api_key, api_secret = _read_source(args.source)
    try:
        keyring.set_password(args.service, KEY_ACCOUNT, api_key)
        keyring.set_password(args.service, SECRET_ACCOUNT, api_secret)
        stored_key = keyring.get_password(args.service, KEY_ACCOUNT)
        stored_secret = keyring.get_password(args.service, SECRET_ACCOUNT)
    except Exception as exc:
        raise CredentialImportError(f"WINVAULT_OPERATION_FAILED:{type(exc).__name__}") from None

    key_matches = stored_key is not None and hmac.compare_digest(api_key, stored_key)
    secret_matches = stored_secret is not None and hmac.compare_digest(api_secret, stored_secret)
    evidence = {
        "service": args.service,
        "accounts": [KEY_ACCOUNT, SECRET_ACCOUNT],
        "backend": backend_name,
        "key_length": len(api_key),
        "secret_length": len(api_secret),
        "round_trip_matches": key_matches and secret_matches,
        "source_retained": True,
        "status": "QUALIFIED" if key_matches and secret_matches else "REJECTED",
    }
    print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if key_matches and secret_matches else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CredentialImportError as exc:
        print(json.dumps({"status": "REJECTED", "error": str(exc)}, sort_keys=True))
        raise SystemExit(1) from None
