#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dreams.json의 회차 사례를 dreams-archive.json에 보관한다.

회차가 바뀌는 일요일 오전(새 회차 사례를 만들기 전)에 돌리면 지난 회차 사례가
그대로 아카이브에 남는다. 같은 회차를 다시 돌려도 중복 없이 id·date 기준으로 합쳐지므로,
평일에 한 번씩 돌려 마지막 요일 사례까지 채워 두어도 된다.

- 없는 과거 회차는 만들지 않는다(빈 rounds: []에서 시작).
- 당첨 등수는 여기서 계산하지 않는다 — 화면이 lotto-results.json과 대조해 채점한다.

usage: python3 scripts/archive-dreams.py [--round 1251] [--dry-run]
"""
import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "dreams.json")
OUT = os.path.join(ROOT, "dreams-archive.json")


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            j = json.load(f)
        return j if isinstance(j, dict) else default
    except (OSError, ValueError):
        return default


def case_key(c):
    return (str(c.get("id") or ""), str(c.get("date") or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--round", type=int, default=0, help="보관할 회차 (기본: dreams.json의 round)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = load(SRC, {})
    cases = [c for c in (src.get("cases") or [])
             if isinstance(c, dict) and isinstance(c.get("nums"), list) and len(c["nums"]) == 6]
    rnd = args.round or int(src.get("round") or 0)
    if not rnd and cases:
        rnd = int(cases[0].get("round") or 0)
    items = [c for c in cases if int(c.get("round") or rnd) == rnd]
    if not rnd or not items:
        print("보관할 사례가 없습니다 — dreams.json의 round/cases를 확인하세요.", file=sys.stderr)
        return 1

    doc = load(OUT, {"v": 1, "rounds": []})
    rounds = [r for r in (doc.get("rounds") or []) if isinstance(r, dict) and int(r.get("round") or 0)]
    cur = next((r for r in rounds if int(r["round"]) == rnd), None)
    entry = cur or {"round": rnd, "weekStart": "", "weekEnd": "", "items": []}

    merged = {}
    for c in (entry.get("items") or []):
        if isinstance(c, dict) and c.get("nums"):
            merged[case_key(c)] = c
    added = 0
    for c in items:
        if case_key(c) not in merged:
            added += 1
        merged[case_key(c)] = c
    entry["items"] = sorted(merged.values(), key=lambda c: str(c.get("date") or ""), reverse=True)
    entry["weekStart"] = src.get("weekStart") or entry.get("weekStart") or ""
    entry["weekEnd"] = src.get("weekEnd") or entry.get("weekEnd") or ""

    if cur:
        rounds[rounds.index(cur)] = entry
    else:
        rounds.append(entry)
    rounds.sort(key=lambda r: int(r["round"]), reverse=True)
    doc["rounds"] = rounds
    doc.setdefault("v", 1)
    doc["updated"] = time.strftime("%Y-%m-%d")

    print(f"{rnd}회 사례 {len(entry['items'])}건 보관 (새로 {added}건) · 아카이브 회차 {len(rounds)}개")
    if args.dry_run:
        print("(--dry-run: 파일을 쓰지 않았습니다)")
        return 0
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
