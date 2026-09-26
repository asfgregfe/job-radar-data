"""수집 결과를 클라우드 일일 작업이 바로 읽을 수 있는 요약(data/summary.md)과 통합 JSON(data/latest.json)으로 만든다."""
import sys

from common import load_data, save_data, today


def main():
    t = today()
    sr = load_data("saramin.json", {"jobs": {}, "log": []})
    ats = load_data("ats.json", {"jobs": {}, "log": []})
    comp = load_data("companies.json", {"companies": {}})

    sr_jobs = [j for j in sr["jobs"].values() if not j.get("deadline") or j["deadline"] >= t]
    sr_new = sorted([j for j in sr_jobs if j.get("is_new")], key=lambda j: (j.get("deadline") or "9999", j["company"]))
    ats_new = [j for j in ats["jobs"].values() if j.get("is_new")]

    lines = [f"# 채용 레이더 원천 데이터 요약 — {t}", "",
             f"사람인 API: 활성 {len(sr_jobs)}건, 오늘 신규 {len(sr_new)}건. ATS API: 전체 {len(ats['jobs'])}건, 신규 {len(ats_new)}건. 기업 데이터 {len(comp.get('companies', {}))}개사.", "",
             "## 1. 사람인 오늘 신규 (마감 임박순) — 원문은 url을 열어 확인할 것", "",
             "| 마감 | 회사 | 공고 | 직무 | 경력 | 학력 | 고용형태 | 지역 | 지원자 | 조회 | url |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for j in sr_new:
        lines.append(f"| {j.get('deadline') or j.get('close_type','')} | {j['company']} | {j['title']} | {j.get('job_mid','')} | {j.get('experience','')} | {j.get('education','')} | {j.get('job_type','')} | {j.get('location','')} | {j.get('apply_cnt') or ''} | {j.get('read_cnt') or ''} | {j['url']} |")
    lines += ["", "## 2. 사람인 활성 공고 중 마감 7일 이내 (기존 문서 마감 대조용)", "", "| 마감 | 회사 | 공고 | url |", "|---|---|---|---|"]
    soon = sorted([j for j in sr_jobs if j.get("deadline") and j["deadline"] <= _plus(t, 7)], key=lambda j: j["deadline"])
    for j in soon[:80]:
        lines.append(f"| {j['deadline']} | {j['company']} | {j['title']} | {j['url']} |")
    lines += ["", "## 3. ATS(Greenhouse/Lever) 신규", ""]
    for j in ats_new:
        lines.append(f"- {j['company']} | {j['title']} | {j['location']} | {j['url']}")
        if j.get("content"):
            lines.append(f"  - 요약(원문 앞부분): {j['content'][:400]}")
    lines += ["", "## 4. 기업 데이터 (DART 직원현황 / 국민연금 추정)", "", "| 회사 | DART 법인명 | 연도 | 직원수 | 1인 평균급여(만원) | 평균근속(년) | NPS 가입자 | NPS 추정연봉(만원) | 비고 |", "|---|---|---|---|---|---|---|---|---|"]
    for name, d in sorted(comp.get("companies", {}).items()):
        da, np = d.get("dart") or {}, d.get("nps") or {}
        lines.append(f"| {name} | {da.get('corp_name','')} | {da.get('year','')} | {da.get('employees','')} | {_man(da.get('avg_salary_krw'))} | {da.get('avg_tenure_years','')} | {np.get('members','')} | {_man(np.get('est_annual_krw'))} | {'상한 근접(과소)' if np.get('ceiling_hit') else ''} |")
    lines += ["", "## 5. 수집 로그", ""] + [f"- {x}" for x in sr.get("log", []) + ats.get("log", []) + comp.get("dart_log", []) + comp.get("nps_log", [])]

    with open("data/summary.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    save_data("latest.json", {"generated": t, "saramin_new": sr_new, "saramin_active_count": len(sr_jobs), "ats_new": ats_new, "companies": comp.get("companies", {})})
    print(f"summary.md 생성: 사람인 신규 {len(sr_new)}, ATS 신규 {len(ats_new)}")


def _plus(t, days):
    from datetime import datetime, timedelta
    return (datetime.strptime(t, "%Y-%m-%d") + timedelta(days=days)).strftime("%Y-%m-%d")


def _man(v):
    return f"{int(v) // 10000:,}" if v else ""


if __name__ == "__main__":
    sys.exit(main())
