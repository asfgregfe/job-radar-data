"""공개 Job Board API가 있는 ATS(Greenhouse, Lever) 수집.

Greenhouse: https://boards-api.greenhouse.io/v1/boards/<board>/jobs?content=true
Lever:      https://api.lever.co/v0/postings/<site>?mode=json
둘 다 인증 없이 공개. board/site 이름은 config/ats_boards.json.
"""
import re
import sys

import requests

from common import get_json, load_config, load_data, save_data, today

GH = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
LV = "https://api.lever.co/v0/postings/{site}"


def strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    cfg = load_config("ats_boards.json")
    loc_kw = [k.lower() for k in cfg.get("location_keywords", [])]
    title_kw = [k.lower() for k in cfg.get("title_keywords", [])]
    prev = load_data("ats.json", {"jobs": {}}).get("jobs", {})
    s = requests.Session()
    out, log, t = {}, [], today()

    def keep(title, location):
        tl, ll = title.lower(), (location or "").lower()
        return any(k in ll for k in loc_kw) and any(k in tl for k in title_kw)

    for b in cfg.get("greenhouse", []):
        res = get_json(s, GH.format(board=b["board"]), params={"content": "true"})
        jobs = res.get("jobs") if isinstance(res, dict) else None
        if not jobs:
            log.append(f"[greenhouse:{b['board']}] 결과 없음 또는 오류: {str(res)[:120]}")
            continue
        n = 0
        for j in jobs:
            loc = (j.get("location") or {}).get("name", "")
            if not keep(j.get("title", ""), loc):
                continue
            jid = f"gh:{b['board']}:{j.get('id')}"
            out[jid] = {
                "id": jid, "ats": "greenhouse", "company": b["company"], "title": j.get("title", ""),
                "location": loc, "url": j.get("absolute_url", ""), "updated": (j.get("updated_at") or "")[:10],
                "content": strip_html(j.get("content", ""))[:3000],
                "first_seen": prev.get(jid, {}).get("first_seen", t), "last_seen": t, "is_new": jid not in prev,
            }
            n += 1
        log.append(f"[greenhouse:{b['board']}] 전체 {len(jobs)}건, 지역·직급 필터 후 {n}건")

    for b in cfg.get("lever", []):
        res = get_json(s, LV.format(site=b["site"]), params={"mode": "json"})
        if not isinstance(res, list):
            log.append(f"[lever:{b['site']}] 오류: {str(res)[:120]}")
            continue
        n = 0
        for j in res:
            cat = j.get("categories") or {}
            loc = cat.get("location", "") or ""
            if not keep(j.get("text", ""), loc):
                continue
            jid = f"lv:{b['site']}:{j.get('id')}"
            out[jid] = {
                "id": jid, "ats": "lever", "company": b["company"], "title": j.get("text", ""),
                "location": loc, "team": cat.get("team", ""), "commitment": cat.get("commitment", ""),
                "url": j.get("hostedUrl", ""), "updated": "",
                "content": strip_html(j.get("descriptionPlain", "") or j.get("description", ""))[:3000],
                "first_seen": prev.get(jid, {}).get("first_seen", t), "last_seen": t, "is_new": jid not in prev,
            }
            n += 1
        log.append(f"[lever:{b['site']}] 전체 {len(res)}건, 필터 후 {n}건")

    save_data("ats.json", {"generated": t, "source": "Greenhouse/Lever 공개 Job Board API", "new_today": sum(1 for v in out.values() if v["is_new"]), "total": len(out), "log": log, "jobs": out})
    print("\n".join(log))


if __name__ == "__main__":
    sys.exit(main())
