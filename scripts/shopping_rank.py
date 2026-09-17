#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""네이버 데이터랩 쇼핑인사이트 '분야별 인기검색어'(건강식품 상위 500)를 하루 단위로 쌓고, 새로 진입·급상승한 검색어를 뽑는다.

왜 (2026-09-17): 이 스캐너의 목적은 '아예 새로운 키워드 찾기'인데 재료가 고정 검색어 37개로 찾은 뉴스뿐이었다.
뉴스의 '새것'은 대부분 보도자료(제품 홍보)라 사람들이 실제로 찾는 것과 다르다. 만들 당시엔 공식 API 로 볼 수 있는 게 없어 뉴스로 우회했다.
쇼핑인사이트 인기검색어는 소비자가 실제로 찾는 성분·제품 이름의 순위라서 '새로 뜨는 성분명'(젖산마그네슘·포스파티딜세린·매스틱…)이 직접 보인다.
공식 API 가 아니라 데이터랩 화면이 쓰는 주소다 — 집 IP(미니PC)에서만 부른다. 하루 1회 25쪽(+첫 실행 때 과거 14일 채우기).
"""
import json
import os
import time
from datetime import datetime, timedelta

import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANK_DIR = os.path.join(BASE_DIR, "data", "shopping_rank")
CID_HEALTH_FOOD = "50000023"   # 식품 > 건강식품
URL = "https://datalab.naver.com/shoppingInsight/getCategoryKeywordRank.naver"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Referer": "https://datalab.naver.com/shoppingInsight/sCategory.naver",
    "X-Requested-With": "XMLHttpRequest",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}
PAGES = 25          # 20개 × 25쪽 = 500위
HISTORY_DAYS = 14


def _path(day):
    return os.path.join(RANK_DIR, f"{day}.json")


def fetch_day(day):
    """그날 하루의 인기검색어 1~500위(문자열 리스트, 순위순). 실패하면 받은 데까지."""
    out = []
    for page in range(1, PAGES + 1):
        try:
            r = requests.post(URL, headers=HEADERS, timeout=15, data={
                "cid": CID_HEALTH_FOOD, "timeUnit": "date", "startDate": day, "endDate": day,
                "age": "", "gender": "", "device": "", "page": page, "count": 20})
            if r.status_code != 200:
                print(f"    [쇼핑순위] {day} {page}쪽 status {r.status_code} — 중단")
                break
            ranks = r.json().get("ranks", [])
        except Exception as e:
            print(f"    [쇼핑순위] {day} {page}쪽 실패: {e}")
            break
        if not ranks:
            break
        out.extend(str(x.get("keyword", "")).strip() for x in ranks)
        time.sleep(0.25)
    return out


def ensure_history(days=HISTORY_DAYS):
    """어제까지 최근 days 일치 파일이 없으면 받아서 채운다. 반환: {날짜: [검색어…]}"""
    os.makedirs(RANK_DIR, exist_ok=True)
    today = datetime.now().date()
    hist = {}
    for i in range(days, 0, -1):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        p = _path(day)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    hist[day] = json.load(f)
                continue
            except (ValueError, OSError):
                pass
        ranks = fetch_day(day)
        if len(ranks) >= 100:          # 덜 받힌 날은 저장하지 않는다(다음 실행 때 다시 시도)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(ranks, f, ensure_ascii=False)
            hist[day] = ranks
            print(f"    [쇼핑순위] {day} 저장({len(ranks)}개)")
    return hist


def find_movers(hist, top_n=300, limit=45):
    """가장 최근 날 기준으로 새로 진입했거나 크게 오른 검색어.
    - 새 진입: 최근 날 top_n 안에 있는데 그 전 기록(5일 이상 있을 때) 어디에도 500위 안에 없던 것
    - 급상승: 일주일쯤 전 순위(그 전 구간의 가장 좋은 순위) 대비 40계단 이상이면서 30% 이상 오른 것"""
    days = sorted(hist)
    if len(days) < 6:
        return []
    last = days[-1]
    cur = {k: i + 1 for i, k in enumerate(hist[last])}
    early_days, recent_days = days[:-4], days[-4:-1]
    movers = []
    for kw, rank in cur.items():
        if rank > top_n or not kw:
            continue
        early = [hist[d].index(kw) + 1 for d in early_days if kw in hist[d]]
        recent = [hist[d].index(kw) + 1 for d in recent_days if kw in hist[d]]
        if not early and not recent:
            movers.append({"keyword": kw, "rank": rank, "kind": "새 진입", "from_rank": None, "gain": 500 - rank})
        elif not early:
            movers.append({"keyword": kw, "rank": rank, "kind": "최근 진입", "from_rank": min(recent), "gain": 500 - rank})
        else:
            base = min(early)
            if base - rank >= 40 and rank <= base * 0.7:
                movers.append({"keyword": kw, "rank": rank, "kind": "급상승", "from_rank": base, "gain": base - rank})
    movers.sort(key=lambda m: m["gain"], reverse=True)
    return movers[:limit]


def collect_movers():
    """스캐너가 부르는 입구. 실패해도 빈 목록만 돌려준다(뉴스만으로 계속 진행)."""
    try:
        hist = ensure_history()
        movers = find_movers(hist)
        print(f"    [쇼핑순위] 기록 {len(hist)}일 · 새 진입/급상승 {len(movers)}개")
        rank_today = {k: i + 1 for i, k in enumerate(hist[sorted(hist)[-1]])} if hist else {}
        return movers, rank_today
    except Exception as e:
        print(f"    [쇼핑순위] 수집 실패 — 건너뜀: {e}")
        return [], {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    m, _ = collect_movers()
    for x in m:
        print(x)
