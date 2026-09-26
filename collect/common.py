import json
import os
import time
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CONFIG = os.path.join(ROOT, "config")


def now_kst():
    return datetime.now(KST)


def today():
    return now_kst().strftime("%Y-%m-%d")


def load_config(name):
    with open(os.path.join(CONFIG, name), encoding="utf-8") as f:
        return json.load(f)


def load_data(name, default):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_data(name, obj):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def get_json(session, url, params=None, headers=None, retries=3, sleep=1.0):
    last = None
    for i in range(retries):
        try:
            r = session.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 200:
                try:
                    return r.json()
                except ValueError:
                    return {"_raw": r.text[:2000]}
            last = f"HTTP {r.status_code}: {r.text[:300]}"
        except Exception as e:  # noqa: BLE001
            last = repr(e)
        time.sleep(sleep * (i + 1))
    return {"_error": last}


def ts_to_date(ts):
    """epoch seconds(str/int) -> YYYY-MM-DD (KST)."""
    try:
        return datetime.fromtimestamp(int(ts), KST).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return ""
