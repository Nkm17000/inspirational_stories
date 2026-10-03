"""Cloudflare Workers AI multi-account rotation.

Rules:
- Any configured account can be used; there is NO neuron-limit routing.
- If Cloudflare reports the account's daily allocation is exhausted
  (HTTP 429 / error 4006 / matching quota message), mark that account
  exhausted for the current UTC date in MongoDB.
- Exhausted accounts are skipped for the rest of that UTC day.
- On the next UTC day, the account is eligible again automatically.
- Successful image usage is recorded per account and UTC date.
"""

import os
from datetime import datetime, timezone

from .db import get_mongodb_collection
from .config import DATABASE_NAME


USAGE_COLLECTION = os.getenv(
    "CLOUDFLARE_USAGE_COLLECTION",
    "cloudflare_daily_usage",
).strip()


def utc_now():
    return datetime.now(timezone.utc)


def utc_day():
    return utc_now().strftime("%Y-%m-%d")


def configured_accounts():
    """Return configured accounts in numeric order."""
    accounts = []

    for index in range(1, 51):
        account_id = os.getenv(
            f"CLOUDFLARE_ACCOUNT_ID_{index}",
            "",
        ).strip()
        api_token = os.getenv(
            f"CLOUDFLARE_API_TOKEN_{index}",
            "",
        ).strip()

        if account_id and api_token:
            accounts.append(
                {
                    "index": index,
                    "account_id": account_id,
                    "api_token": api_token,
                }
            )

    # Backward compatibility with the original single-account setup.
    if not accounts:
        account_id = os.getenv(
            "CLOUDFLARE_ACCOUNT_ID",
            "",
        ).strip()
        api_token = os.getenv(
            "CLOUDFLARE_API_TOKEN",
            "",
        ).strip()

        if account_id and api_token:
            accounts.append(
                {
                    "index": 1,
                    "account_id": account_id,
                    "api_token": api_token,
                }
            )

    return accounts


def _collection():
    client, _ = get_mongodb_collection()
    return client


def _ensure_index(collection):
    try:
        collection.create_index(
            [
                ("date_utc", 1),
                ("account_id", 1),
            ],
            unique=True,
            name="cloudflare_account_day_unique",
        )
    except Exception as exc:
        print(
            f"⚠️ Could not create Cloudflare usage index: {exc}",
            flush=True,
        )


def get_account_status(account_id):
    """Read one account's status for the current UTC day."""
    day = utc_day()
    client = _collection()

    try:
        collection = client[DATABASE_NAME][USAGE_COLLECTION]
        _ensure_index(collection)

        row = collection.find_one(
            {
                "date_utc": day,
                "account_id": account_id,
            }
        )

        if not row:
            return {
                "date_utc": day,
                "account_id": account_id,
                "exhausted": False,
                "neurons_used": 0.0,
                "image_count": 0,
            }

        return {
            "date_utc": day,
            "account_id": account_id,
            "exhausted": bool(row.get("exhausted", False)),
            "neurons_used": float(
                row.get("neurons_used", 0.0) or 0.0
            ),
            "image_count": int(
                row.get("image_count", 0) or 0
            ),
            "exhausted_reason": row.get(
                "exhausted_reason"
            ),
            "exhausted_at": row.get(
                "exhausted_at"
            ),
        }
    finally:
        client.close()


def mark_exhausted(account_id, reason):
    """Mark an account exhausted for today's UTC date."""
    day = utc_day()
    now = utc_now()

    client = _collection()

    try:
        collection = client[DATABASE_NAME][USAGE_COLLECTION]
        _ensure_index(collection)

        collection.update_one(
            {
                "date_utc": day,
                "account_id": account_id,
            },
            {
                "$set": {
                    "exhausted": True,
                    "exhausted_reason": reason,
                    "exhausted_at": now,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "date_utc": day,
                    "account_id": account_id,
                    "neurons_used": 0.0,
                    "image_count": 0,
                },
            },
            upsert=True,
        )

        print(
            f"🚫 Cloudflare account {account_id} marked "
            f"EXHAUSTED for UTC {day}",
            flush=True,
        )
    finally:
        client.close()


def record_usage(
    account_id,
    neurons,
    neuron_source,
):
    """Record successful image usage for account + UTC date."""
    day = utc_day()
    now = utc_now()
    value = max(0.0, float(neurons or 0.0))

    client = _collection()

    try:
        collection = client[DATABASE_NAME][USAGE_COLLECTION]
        _ensure_index(collection)

        inc = {
            "neurons_used": value,
            "image_count": 1,
        }

        set_fields = {
            "updated_at": now,
            "last_success_at": now,
            "last_neuron_source": neuron_source,
        }

        collection.update_one(
            {
                "date_utc": day,
                "account_id": account_id,
            },
            {
                "$inc": inc,
                "$set": set_fields,
                "$setOnInsert": {
                    "date_utc": day,
                    "account_id": account_id,
                    "exhausted": False,
                },
            },
            upsert=True,
        )
    finally:
        client.close()


def get_available_accounts():
    """Return configured accounts that are not exhausted today."""
    available = []

    for account in configured_accounts():
        status = get_account_status(
            account["account_id"]
        )

        if status["exhausted"]:
            print(
                f"⏭️ Cloudflare Account "
                f"{account['index']} skipped: exhausted "
                f"for UTC {utc_day()}",
                flush=True,
            )
            continue

        available.append(account)

    return available


def is_quota_exhausted_response(
    status_code,
    response_data,
):
    """Identify Cloudflare's daily free-allocation exhaustion response."""
    if status_code != 429:
        return False

    text = str(response_data).lower()

    return (
        "4006" in text
        or "daily free allocation" in text
        or "used up your daily free allocation" in text
        or "daily allocation" in text
        or "quota" in text
    )
