#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""회차별 당첨번호를 받아 lotto-results.json을 갱신한다.

깃허브 액션(토요일 20:40·20:45·20:55·21:10 KST)에서 그대로 돌린다.
- 이번 주 회차가 이미 파일에 있으면 커밋 없이 바로 끝난다(no-op). 예약 실행이 여러 번 겹쳐도
  먼저 성공한 실행 뒤의 실행은 몇 초 만에 끝난다.
- 아직 결과가 안 올라왔으면 MONG_PICK_WAIT(초) 만큼 기다렸다 다시 본다.
- 동행복권 API가 응답을 늦게 주거나 끊기면 MONG_PICK_NET_RETRY(초) 뒤 다시 시도한다.
  끝내 실패하면 파일을 건드리지 않고 조용히 끝낸다(워크플로를 실패로 만들지 않음).
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timedelta, timezone

ENDPOINT = "https://www.dhlottery.co.kr/lt645/selectPstLt645InfoNew.do"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "https://www.dhlottery.co.kr/lt645/result",
    "Accept": "application/json",
}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lotto-results.json")
KEEP = 200   # 최근 200회차 보관 — 지난 회차 아카이브(dreams-archive.json)의 꿈도 오래 채점되도록
KST = timezone(timedelta(hours=9))


def last_saturday(now=None):
    """가장 최근 토요일(KST) 날짜. 이 회차 결과까지는 파일에 들어와 있어야 한다."""
    d = (now or datetime.now(KST)).astimezone(KST)
    return (d - timedelta(days=(d.weekday() - 5) % 7)).date().isoformat()


def fetch(round_no):
    url = f"{ENDPOINT}?srchDir=center&srchLtEpsd={round_no}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as r:
        j = json.load(r)
    rows = ((j or {}).get("data") or {}).get("list") or []
    return [to_draw(x) for x in rows if to_draw(x)]


def to_draw(row):
    if not row:
        return None
    nums = [row.get(f"tm{i}WnNo") for i in range(1, 7)]
    try:
        nums = [int(n) for n in nums]
        bonus = int(row.get("bnsWnNo"))
        rnd = int(row.get("ltEpsd"))
    except (TypeError, ValueError):
        return None
    if len([n for n in nums if 1 <= n <= 45]) != 6 or not 1 <= bonus <= 45 or not rnd:
        return None
    ymd = str(row.get("ltRflYmd") or "")
    date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}" if len(ymd) == 8 else ""
    return {"round": rnd, "date": date, "numbers": sorted(nums), "bonus": bonus}


def load():
    try:
        with open(OUT, encoding="utf-8") as f:
            j = json.load(f)
        if isinstance(j.get("draws"), dict):
            return j
    except (OSError, ValueError):
        pass
    return {"version": 1, "updated": "", "latest": 0, "draws": {}}


def save(doc):
    doc["draws"] = {k: doc["draws"][k] for k in sorted(doc["draws"], key=lambda x: int(x))}
    while len(doc["draws"]) > KEEP:
        doc["draws"].pop(next(iter(doc["draws"])))
    doc["latest"] = max(int(k) for k in doc["draws"])
    doc["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")


def newest(doc):
    """(최신 회차, 그 회차 날짜). doc["latest"]가 아직 저장 전이어도 실제 draws 기준으로 센다."""
    draws = doc.get("draws") or {}
    if not draws:
        return 0, ""
    latest = max(int(k) for k in draws)
    return latest, str((draws.get(str(latest)) or {}).get("date") or "")


def up_to_date(doc, need):
    """이번 주(가장 최근 토요일) 회차까지 들어와 있으면 True → 커밋할 것 없음."""
    latest, date = newest(doc)
    return bool(latest and date and date >= need)


def main():
    doc = load()
    latest, date = newest(doc)
    if not latest:
        print("lotto-results.json에 기준 회차가 없습니다.", file=sys.stderr)
        return 0

    need = last_saturday()
    if up_to_date(doc, need):
        print(f"이미 최신 — {latest}회({date}) · 기준 {need}. 커밋할 것이 없습니다.")
        return 0

    wait = max(10, int(os.environ.get("MONG_PICK_WAIT") or 180))
    tries = max(1, int(os.environ.get("MONG_PICK_TRIES") or 1))
    net_retry = max(5, int(os.environ.get("MONG_PICK_NET_RETRY") or 20))
    print(f"기준 회차 {need} · 지금 파일 최신 {latest}회({date or '날짜 없음'}) — 확인 시작")

    added = 0
    for attempt in range(tries):
        rnd, _ = newest(doc)
        rnd += 1
        try:
            got = fetch(rnd)
        except Exception as e:                       # 네트워크·응답 지연 — 파일은 건드리지 않는다
            print(f"{rnd}회 조회 실패({type(e).__name__}): {e}", file=sys.stderr)
            if attempt < tries - 1:
                print(f"{net_retry}초 뒤 다시 시도 ({attempt + 1}/{tries})")
                time.sleep(net_retry)
                continue
            print("조회가 계속 실패해 이번 실행은 그대로 끝냅니다(파일 변경 없음).", file=sys.stderr)
            return 0

        new = [d for d in got if str(d["round"]) not in doc["draws"]]
        if new:
            for d in new:
                doc["draws"][str(d["round"])] = d
            added += len(new)
            print(f"{sorted(d['round'] for d in new)}회 추가")

        if up_to_date(doc, need):
            break
        if attempt < tries - 1:
            print(f"{int(max(doc['draws'])) + 1}회 아직 없음 — {wait}초 뒤 다시 확인 ({attempt + 1}/{tries})")
            time.sleep(wait)

    if added:
        save(doc)
        print(f"{added}개 회차 추가 → 최신 {doc['latest']}회")
    else:
        print("새 회차 없음 — 커밋하지 않습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
