"""공공데이터포털 — 국민연금공단 국민연금 가입 사업장 내역(B552015/NpsBplcInfoInqireService).

- getBassInfoSearch(wkpl_nm)로 사업장을 찾고, getDetailInfoSearch(seq)로 가입자 수(jnngpCnt)·당월고지금액(crrmmNtcAmt)을 받는다.
- 월평균 보수 추정 = 당월고지금액 / 가입자수 / 보험료율. 2026년 보험료율은 9.5%(2025 개정, 매년 0.5%p 인상)로 두었고,
  기준소득월액 상한(2026년 기준 약 637만 원) 때문에 고연봉 기업은 과소 추정된다는 점을 결과에 함께 적는다.
- 응답 필드명은 공공데이터포털 명세 기준이며, 명세가 바뀌면 여기만 고친다.
"""
import os
import sys

import requests

from common import get_json, load_config, load_data, save_data, today

BASE = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireService"
RATE = 0.095  # 2026 국민연금 보험료율(사업장 합계). 2027년부터 0.10, 이후 매년 +0.005
CEILING_MONTHLY = 6_370_000  # 기준소득월액 상한(2025.7~2026.6 6,370,000원; 매년 7월 갱신 — 확인 필요)


def items(res):
    try:
        body = res["response"]["body"]["items"]
        it = body.get("item") if isinstance(body, dict) else None
        if it is None:
            return []
        return it if isinstance(it, list) else [it]
    except (KeyError, TypeError):
        return []


def main():
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        print("DATA_GO_KR_KEY 없음 — 국민연금 수집 건너뜀")
        return
    names = load_config("companies.json")["companies"]
    prev = load_data("companies.json", {"companies": {}})
    comp = prev.get("companies", {})
    s = requests.Session()
    log = []
    for name in names:
        q = name.replace("(주)", "").replace("주식회사", "").strip()
        res = get_json(s, f"{BASE}/getBassInfoSearch", params={"serviceKey": key, "pageNo": 1, "numOfRows": 20, "wkpl_nm": q, "_type": "json"})
        its = items(res)
        if not its:
            log.append(f"[{name}] 사업장 검색 결과 없음: {str(res)[:100]}")
            continue
        # 가입 상태(wkplJnngStcd 1=등록)인 것 중 가입자수가 최대인 사업장을 고른다
        best = None
        for it in its:
            if str(it.get("wkplJnngStcd", "1")) not in ("1", ""):
                continue
            seq = it.get("seq")
            det = get_json(s, f"{BASE}/getDetailInfoSearch", params={"serviceKey": key, "seq": seq, "_type": "json"})
            d = (items(det) or [{}])[0]
            try:
                cnt = int(d.get("jnngpCnt") or 0)
                amt = int(d.get("crrmmNtcAmt") or 0)
            except ValueError:
                continue
            if cnt and (best is None or cnt > best["members"]):
                best = {"wkplNm": it.get("wkplNm"), "seq": seq, "addr": it.get("wkplRoadNmDtlAddr", ""), "members": cnt,
                        "notice_amt": amt, "dataCrtYm": d.get("dataCrtYm") or it.get("dataCrtYm")}
        if not best:
            log.append(f"[{name}] 가입자 수 확인 불가")
            continue
        monthly = best["notice_amt"] / best["members"] / RATE if best["members"] else 0
        best["est_monthly_krw"] = int(monthly)
        best["est_annual_krw"] = int(monthly * 12)
        best["ceiling_hit"] = monthly >= CEILING_MONTHLY * 0.95
        best["note"] = "국민연금 고지액 기준 추정. 기준소득월액 상한 때문에 실제보다 낮을 수 있음" + (" (상한 근접 → 과소 추정 확실)" if best["ceiling_hit"] else "")
        best["fetched"] = today()
        comp.setdefault(name, {})["nps"] = best
        log.append(f"[{name}] {best['wkplNm']} 가입자 {best['members']}명, 추정 연봉 {best['est_annual_krw']:,}원{' (상한)' if best['ceiling_hit'] else ''}")
    save_data("companies.json", {"generated": today(), "companies": comp, "nps_log": log, "dart_log": prev.get("dart_log", [])})
    print("\n".join(log))


if __name__ == "__main__":
    sys.exit(main())
