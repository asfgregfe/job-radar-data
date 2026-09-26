"""공공데이터포털 — 국민연금공단 국민연금 가입 사업장 내역(B552015/NpsBplcInfoInqireService).

- getBassInfoSearch(wkpl_nm)로 사업장을 찾고, getDetailInfoSearch(seq)로 가입자 수(jnngpCnt)·당월고지금액(crrmmNtcAmt)을 받는다.
- 이 API는 XML로 응답한다(_type=json 미지원). 여기서는 XML을 직접 파싱한다.
- 월평균 보수 추정 = 당월고지금액 / 가입자수 / 보험료율. 2026년 보험료율은 9.5%(2025 개정, 매년 0.5%p 인상)로 두었고,
  기준소득월액 상한(2026년 기준 약 637만 원) 때문에 고연봉 기업은 과소 추정된다는 점을 결과에 함께 적는다.
- 인증키는 포털에 표시된 값을 그대로 Secrets에 넣으면 된다. 인코딩/디코딩 두 형태를 첫 호출에서 모두 시도해 되는 쪽을 쓴다.
"""
import os
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

import requests

from common import load_config, load_data, save_data, today

BASE = "https://apis.data.go.kr/B552015/NpsBplcInfoInqireServiceV2"  # 2026-09-26 사용자 확인: V2로 이전(구 주소는 코드 12 폐기 오류)
RATE = 0.095  # 2026 국민연금 보험료율(사업장 합계). 2027년부터 0.10, 이후 매년 +0.005
CEILING_MONTHLY = 6_370_000  # 기준소득월액 상한(2025.7~2026.6 6,370,000원; 매년 7월 갱신 — 확인 필요)


def call(session, op, key, **params):
    """XML 응답을 (items, meta) 로 돌려준다. meta에는 totalCount 또는 오류 메시지."""
    p = {"serviceKey": key, "pageNo": 1, "numOfRows": 30}
    p.update(params)
    try:
        r = session.get(f"{BASE}/{op}", params=p, timeout=30)
    except Exception as e:  # noqa: BLE001
        return [], {"error": repr(e)}
    text = r.text
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return [], {"error": f"HTTP {r.status_code} 비XML 응답: {text[:300]}"}
    if root.tag == "OpenAPI_ServiceResponse":
        h = root.find("cmmMsgHeader")
        msg = " / ".join(f"{c.tag}={c.text}" for c in h) if h is not None else text[:300]
        return [], {"error": f"HTTP {r.status_code} {msg}"}
    code = root.findtext("header/resultCode")
    if code not in (None, "00", "0"):
        return [], {"error": f"resultCode={code} {root.findtext('header/resultMsg')}"}
    items = []
    for it in root.iter("item"):
        items.append({c.tag: (c.text or "").strip() for c in it})
    return items, {"totalCount": root.findtext("body/totalCount")}


OPS = {"search": "getBassInfoSearch", "detail": "getDetailInfoSearch"}


def pick_key(session, raw):
    """원본 키와 URL 디코딩한 키, 그리고 V2에서 기능명이 바뀌었을 가능성(…V2 접미사)까지 시험해 동작하는 조합을 고른다."""
    cands = [raw]
    if "%" in raw:
        cands.append(urllib.parse.unquote(raw))
    last = None
    for k in cands:
        for suffix in ("", "V2"):
            items, meta = call(session, "getBassInfoSearch" + suffix, k, wkpl_nm="삼성전자")
            if "error" not in meta:
                OPS["search"] = "getBassInfoSearch" + suffix
                OPS["detail"] = "getDetailInfoSearch" + suffix
                return k, None
            last = meta["error"]
    return None, last


def main():
    raw = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not raw:
        print("DATA_GO_KR_KEY 없음 — 국민연금 수집 건너뜀")
        return
    names = load_config("companies.json")["companies"]
    prev = load_data("companies.json", {"companies": {}})
    comp = prev.get("companies", {})
    s = requests.Session()
    log = []
    key, err = pick_key(s, raw)
    if not key:
        log.append(f"인증키 검증 실패(원본·디코딩 모두): {err}")
        save_data("companies.json", {"generated": today(), "companies": comp, "nps_log": log, "dart_log": prev.get("dart_log", [])})
        print("\n".join(log))
        return
    for name in names:
        q = name.replace("(주)", "").replace("주식회사", "").strip()
        its, meta = call(s, OPS["search"], key, wkpl_nm=q)
        if "error" in meta:
            log.append(f"[{name}] 검색 오류: {meta['error'][:300]}")
            continue
        if not its:
            log.append(f"[{name}] 사업장 검색 결과 없음")
            continue
        best = None
        for it in its:
            if it.get("wkplJnngStcd", "1") not in ("1", ""):
                continue  # 탈퇴 사업장 제외
            seq = it.get("seq")
            if not seq:
                continue
            det, dmeta = call(s, OPS["detail"], key, seq=seq)
            d = det[0] if det else {}
            try:
                cnt = int(d.get("jnngpCnt") or 0)
                amt = int(d.get("crrmmNtcAmt") or 0)
            except ValueError:
                continue
            if cnt and (best is None or cnt > best["members"]):
                best = {"wkplNm": it.get("wkplNm"), "seq": seq, "addr": it.get("wkplRoadNmDtlAddr", ""), "members": cnt,
                        "notice_amt": amt, "dataCrtYm": d.get("dataCrtYm") or it.get("dataCrtYm"),
                        "candidates": len(its)}
            time.sleep(0.2)
        if not best:
            log.append(f"[{name}] 후보 {len(its)}건 중 가입자 수 확인 불가")
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
