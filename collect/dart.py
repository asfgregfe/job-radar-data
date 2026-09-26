"""금감원 DART 오픈API — 직원 현황(empSttus): 직원 수, 평균 근속연수, 1인 평균 급여.

- corpCode.xml(zip)로 법인명→고유번호 매핑을 만든 뒤(하루 1회 캐시), 사업보고서(reprt_code 11011) 기준 최근 연도를 조회한다.
- 공시 대상(상장·외감 대형 법인)만 잡힌다. 비상장 중견은 nps.py로 보완.
- 필드 의미: sm 합계 인원, avrg_cnwk_sdytrn 평균 근속연수, jan_salary_am 1인 평균 급여액(원), fo_bbm 사업부문, sexdstn 성별.
"""
import io
import json
import os
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date

import requests

from common import DATA, get_json, load_config, load_data, save_data, today

CORP = "https://opendart.fss.or.kr/api/corpCode.xml"
EMP = "https://opendart.fss.or.kr/api/empSttus.json"


def load_corp_map(key, session):
    # 예전 버전이 data/에 남긴 10MB 캐시는 저장소에서 제거한다(커밋 대상이 아님)
    stale = os.path.join(DATA, "_dart_corpcode.json")
    if os.path.exists(stale):
        os.remove(stale)
    cache = "/tmp/_dart_corpcode.json"
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    r = session.get(CORP, params={"crtfc_key": key}, timeout=60)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    xml = z.read(z.namelist()[0])
    root = ET.fromstring(xml)
    m = {}
    for el in root.iter("list"):
        name = (el.findtext("corp_name") or "").strip()
        code = (el.findtext("corp_code") or "").strip()
        stock = (el.findtext("stock_code") or "").strip()
        if name and code:
            m.setdefault(name, []).append({"corp_code": code, "stock_code": stock})
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False)
    return m


def find_corp(m, name):
    n = name.replace("(주)", "").replace("주식회사", "").replace(" ", "")
    # 정확 일치 우선, 상장사(stock_code 있음) 우선
    cands = []
    for k, v in m.items():
        kk = k.replace("(주)", "").replace("주식회사", "").replace(" ", "")
        if kk == n or kk == "에이치디" + n or kk == n.replace("HD", "에이치디"):
            cands += [(0, k, x) for x in v]
        elif n and (n in kk):
            cands += [(1 + len(kk) - len(n), k, x) for x in v]
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], 0 if c[2]["stock_code"] else 1))
    return {"matched_name": cands[0][1], **cands[0][2]}


def main():
    key = os.environ.get("DART_KEY", "").strip()
    if not key:
        print("DART_KEY 없음 — DART 수집 건너뜀")
        return
    names = load_config("companies.json")["companies"]
    prev = load_data("companies.json", {"companies": {}})
    comp = prev.get("companies", {})
    s = requests.Session()
    m = load_corp_map(key, s)
    year = date.today().year - 1
    log = []
    for name in names:
        c = find_corp(m, name)
        if not c:
            log.append(f"[{name}] DART 고유번호 없음(비상장·비공시 가능)")
            continue
        rows = None
        for y in (year, year - 1):
            res = get_json(s, EMP, params={"crtfc_key": key, "corp_code": c["corp_code"], "bsns_year": str(y), "reprt_code": "11011"})
            if res.get("status") == "000" and res.get("list"):
                rows = (y, res["list"])
                break
            if res.get("status") == "020":
                log.append("DART 일일 한도 초과 — 중단")
                break
        if not rows:
            log.append(f"[{name}] 직원현황 없음 ({c['matched_name']})")
            continue
        y, lst = rows
        total_emp, sal_w, ten_w, w = 0, 0.0, 0.0, 0
        segs = []
        for r in lst:
            try:
                n = int(str(r.get("sm", "0")).replace(",", "") or 0)
            except ValueError:
                n = 0
            try:
                sal = int(str(r.get("jan_salary_am", "0")).replace(",", "") or 0)
            except ValueError:
                sal = 0
            try:
                ten = float(str(r.get("avrg_cnwk_sdytrn", "0")).replace(",", "").replace("년", "") or 0)
            except ValueError:
                ten = 0.0
            total_emp += n
            if n and sal:
                sal_w += sal * n
                ten_w += ten * n
                w += n
            segs.append({"부문": r.get("fo_bbm", ""), "성별": r.get("sexdstn", ""), "인원": n, "평균급여_원": sal, "평균근속_년": ten})
        d = comp.setdefault(name, {})
        d.update({
            "dart": {
                "corp_name": c["matched_name"], "corp_code": c["corp_code"], "stock_code": c["stock_code"], "year": y,
                "employees": total_emp,
                "avg_salary_krw": int(sal_w / w) if w else None,
                "avg_tenure_years": round(ten_w / w, 1) if w else None,
                "segments": segs, "fetched": today(),
            }
        })
        log.append(f"[{name}] {c['matched_name']} {y}: 직원 {total_emp}명, 평균급여 {d['dart']['avg_salary_krw'] or '미기재(부문별 공시 없음)'}원")
    save_data("companies.json", {"generated": today(), "companies": comp, "dart_log": log})
    print("\n".join(log))


if __name__ == "__main__":
    sys.exit(main())
