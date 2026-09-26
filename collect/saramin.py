"""사람인 오픈 API(https://oapi.saramin.co.kr/job-search) 수집.

- 검색어별로 최신순 count건을 받아 신입 지원 가능 공고만 남긴다.
- 결과 스키마는 채용 레이더 postings 문서와 맞추기 쉽도록 평탄화한다.
- apply-cnt(지원자 수)·read-cnt(조회수)가 오면 함께 저장한다(경쟁 보정 근거).
"""
import os
import re
import sys

import requests

from common import get_json, load_config, load_data, save_data, today, ts_to_date

API = "https://oapi.saramin.co.kr/job-search"


def flatten(job):
    pos = job.get("position", {}) or {}
    comp = (job.get("company", {}) or {}).get("detail", {}) or {}

    def nm(key):
        v = pos.get(key) or {}
        return v.get("name", "") if isinstance(v, dict) else ""

    exp = pos.get("experience-level") or {}
    return {
        "id": str(job.get("id", "")),
        "url": job.get("url", ""),
        "active": job.get("active"),
        "company": comp.get("name", ""),
        "company_url": comp.get("href", ""),
        "title": pos.get("title", ""),
        "industry": nm("industry"),
        "location": nm("location"),
        "job_type": nm("job-type"),
        "job_mid": nm("job-mid-code"),
        "job_code": nm("job-code"),
        "experience": exp.get("name", ""),
        "experience_min": exp.get("min"),
        "experience_max": exp.get("max"),
        "education": nm("required-education-level"),
        "keyword": job.get("keyword", ""),
        "salary": (job.get("salary") or {}).get("name", ""),
        "posted": ts_to_date(job.get("posting-timestamp")),
        "opened": ts_to_date(job.get("opening-timestamp")),
        "deadline": ts_to_date(job.get("expiration-timestamp")),
        "close_type": (job.get("close-type") or {}).get("name", ""),
        "read_cnt": job.get("read-cnt"),
        "apply_cnt": job.get("apply-cnt"),
    }


def main():
    key = os.environ.get("SARAMIN_KEY", "").strip()
    if not key:
        print("SARAMIN_KEY 없음 — 사람인 수집 건너뜀")
        return
    cfg = load_config("keywords.json")
    ex_title = [re.compile(p) for p in cfg.get("exclude_title_patterns", [])]
    ex_comp = [re.compile(p) for p in cfg.get("exclude_company_patterns", [])]

    prev = load_data("saramin.json", {"jobs": {}})
    prev_jobs = prev.get("jobs", {})

    s = requests.Session()
    seen = {}
    log = []
    for q in cfg["queries"]:
        params = {
            "access-key": key,
            "keywords": q["keywords"],
            "count": min(int(q.get("count", 50)), 110),
            "sort": q.get("sort", "pd"),
            "fields": "posting-date,expiration-date,count",
            "sr": "directhire",
        }
        res = get_json(s, API, params=params, headers={"Accept": "application/json"})
        if "_error" in res or "code" in res:
            log.append(f"[{q['keywords']}] 오류: {res.get('_error') or res}")
            if res.get("code") == 4:
                log.append("일일 요청 한도 초과 — 이후 검색 중단")
                break
            continue
        jobs = (res.get("jobs") or {}).get("job") or []
        kept = 0
        for j in jobs:
            f = flatten(j)
            if not f["id"] or f["id"] in seen:
                continue
            if "신입" not in f["experience"] and "경력무관" not in f["experience"]:
                continue
            if any(p.search(f["title"]) for p in ex_title):
                continue
            if any(p.search(f["company"]) for p in ex_comp):
                continue
            f["matched_query"] = q["keywords"]
            seen[f["id"]] = f
            kept += 1
        log.append(f"[{q['keywords']}] 수신 {len(jobs)}건, 신입·필터 후 {kept}건")

    t = today()
    merged = {}
    for jid, f in seen.items():
        old = prev_jobs.get(jid)
        f["first_seen"] = old["first_seen"] if old else t
        f["last_seen"] = t
        f["is_new"] = old is None
        merged[jid] = f
    # 오늘 검색에 안 잡힌 기존 공고는 마감 전이면 유지(last_seen 갱신 없음)
    for jid, old in prev_jobs.items():
        if jid in merged:
            continue
        if old.get("deadline") and old["deadline"] < t:
            continue
        old["is_new"] = False
        merged[jid] = old

    new_count = sum(1 for f in merged.values() if f.get("is_new"))
    save_data("saramin.json", {"generated": t, "source": "사람인 오픈 API", "new_today": new_count, "total": len(merged), "log": log, "jobs": merged})
    print("\n".join(log))
    print(f"사람인: 총 {len(merged)}건, 오늘 신규 {new_count}건")


if __name__ == "__main__":
    sys.exit(main())
