"""
건강·약 트렌드 스캐너 — 데이터 수집 및 점수 산출
매일 새벽 GitHub Actions에서 자동 실행됩니다.
"""

import os
import sys
import json
import re
import math
import time
from datetime import datetime, timedelta
from collections import Counter

import requests
from bs4 import BeautifulSoup

# ── API 키 (GitHub Secrets에서 가져옴) ──
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")

NAVER_HEADERS = {
    "X-Naver-Client-Id": NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
}

# ── 설정 ──
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

# 약사 전문성 키워드
PHARMA_KEYWORDS = ["처방", "복용법", "용량", "상호작용", "금기", "성분", "함량",
                   "부작용", "약동학", "반감기", "대사", "CYP", "약물"]

# 검색의도 분류 키워드
DOUBT_KEYWORDS = ["부작용", "위험", "진짜", "효과없", "먹어도되나", "품절", "대체",
                  "주의", "경고", "논란", "가짜", "허위", "과대광고", "리콜", "중단"]
SHOPPING_KEYWORDS = ["추천", "가격", "할인", "후기", "구매", "최저가", "쿠팡",
                     "순위", "비교", "TOP", "best", "입문"]

# 약업계 트리거 단어
STRONG_TRIGGERS = ["품절", "허가", "리콜", "공급중단", "안전성서한", "안전성 서한",
                   "회수", "판매중지"]
NORMAL_TRIGGERS = ["급여", "약가", "인하", "규제", "단속", "표시광고", "허가변경"]

# 글로벌 약물명 (한국 상륙 감지용)
GLOBAL_DRUGS = ["Ozempic", "Wegovy", "Mounjaro", "GLP-1", "Tirzepatide",
                "Semaglutide", "ozempic", "wegovy", "mounjaro",
                "위고비", "오젬픽", "마운자로", "삭센다"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1단계: 네이버 뉴스에서 급등 키워드 자동 추출
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_naver_news(query, display=100, sort="date"):
    """네이버 뉴스 검색 API 호출"""
    url = "https://openapi.naver.com/v1/search/news.json"
    params = {"query": query, "display": display, "sort": sort}
    try:
        r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:
        print(f"  [ERROR] 뉴스 검색 실패 ({query}): {e}")
        return []


def extract_keywords_from_news():
    """건강/의약 뉴스 제목에서 키워드 자동 추출"""
    print("=" * 50)
    print("1단계: 네이버 뉴스에서 키워드 추출")
    print("=" * 50)

    # 건강/의약 관련 검색어로 뉴스 수집
    seed_queries = [
        "건강기능식품", "영양제", "비타민", "유산균",
        "다이어트약", "비만치료제", "GLP-1",
        "처방약", "의약품", "식약처",
        "영양제 부작용", "건강식품 논란",
        "약국", "약사", "의약품 허가",
    ]

    all_titles = []
    for q in seed_queries:
        items = fetch_naver_news(q, display=100)
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            all_titles.append(title)
        time.sleep(0.1)

    print(f"  수집된 뉴스 제목: {len(all_titles)}건")

    # 제목에서 명사(2글자 이상 한글 단어) 추출
    word_counter = Counter()
    # 불용어
    stopwords = {"기자", "뉴스", "보도", "관련", "대한", "통해", "위해", "이상",
                 "이하", "최근", "현재", "오늘", "내일", "올해", "지난", "다음",
                 "경우", "가능", "정도", "사진", "제공", "연합", "한겨레", "조선",
                 "중앙", "동아", "매일", "한국", "서울", "국내", "세계", "글로벌",
                 "시장", "업계", "기업", "회사", "사업", "발표", "조사", "연구",
                 "결과", "분석", "전문", "관계", "이번"}

    for title in all_titles:
        words = re.findall(r"[가-힣]{2,}", title)
        for w in words:
            if w not in stopwords and len(w) >= 2:
                word_counter[w] += 1

    # 빈도 3회 이상인 키워드만 (= 여러 기사에서 언급 = 이슈)
    trending = [(word, count) for word, count in word_counter.most_common(100)
                if count >= 3]

    print(f"  추출된 트렌딩 키워드: {len(trending)}개")
    for w, c in trending[:20]:
        print(f"    {w}: {c}건")

    return trending  # (keyword, news_count) 튜플 리스트 반환


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2단계: H — 주제 온도 (네이버 DataLab 검색량 변화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_search_trend(keyword):
    """네이버 DataLab API로 최근 검색량 변화율 계산 (일간 단위)"""
    url = "https://openapi.naver.com/v1/datalab/search"

    today = datetime.now()
    start_date = (today - timedelta(days=28)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": [
            {"groupName": keyword, "keywords": [keyword]}
        ],
    }

    try:
        r = requests.post(url, headers={
            **NAVER_HEADERS,
            "Content-Type": "application/json",
        }, json=body, timeout=10)
        r.raise_for_status()
        data = r.json()

        results = data.get("results", [])
        if not results or not results[0].get("data"):
            return 0, 0

        points = results[0]["data"]
        if len(points) < 14:
            return 0, 0

        # 최근 7일 평균 vs 이전 7일 평균 비교
        recent = [p.get("ratio", 0) for p in points[-7:]]
        previous = [p.get("ratio", 0) for p in points[-14:-7]]

        avg_recent = sum(recent) / len(recent) if recent else 0
        avg_previous = sum(previous) / len(previous) if previous else 0

        if avg_previous == 0:
            change_rate = 300 if avg_recent > 0 else 0
        else:
            change_rate = ((avg_recent - avg_previous) / avg_previous) * 100

        return change_rate, avg_recent

    except Exception as e:
        print(f"  [ERROR] DataLab 실패 ({keyword}): {e}")
        return 0, 0


def calc_h_score(change_rate, news_count=0):
    """변화율 → H 점수 변환. 뉴스 빈도도 보조 반영."""
    # DataLab 기반 점수
    if change_rate >= 300:
        h = 100
    elif change_rate >= 200:
        h = 70
    elif change_rate >= 100:
        h = 50
    elif change_rate >= 50:
        h = 30
    elif change_rate >= 20:
        h = 15
    elif change_rate > 0:
        h = 5
    else:
        h = 0

    # 뉴스에 자주 등장하면 최소 점수 보장 (H=0 방지)
    if h == 0 and news_count >= 5:
        h = 15
    elif h == 0 and news_count >= 3:
        h = 10
    elif h < 5 and news_count >= 3:
        h = max(h, 5)

    return h


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3단계: I, P — 동반 검색어 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_related_keywords(keyword):
    """네이버 검색 API로 블로그 검색 → 동반 키워드 추출"""
    url = "https://openapi.naver.com/v1/search/blog.json"
    params = {"query": keyword, "display": 50, "sort": "date"}
    try:
        r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])

        all_text = ""
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            desc = re.sub(r"<[^>]+>", "", item.get("description", ""))
            all_text += f" {title} {desc}"

        return all_text
    except Exception as e:
        print(f"  [ERROR] 블로그 검색 실패 ({keyword}): {e}")
        return ""


def calc_i_score(related_text):
    """검색의도 배수 계산: I = 1.0 + 0.5 × (A - B) / (A + B + 1)"""
    a = sum(1 for w in DOUBT_KEYWORDS if w in related_text)
    b = sum(1 for w in SHOPPING_KEYWORDS if w in related_text)
    i_score = 1.0 + 0.5 * (a - b) / (a + b + 1)
    intent_type = "의심/경고형" if a > b else ("구매/추천형" if b > a else "중립")
    return round(i_score, 2), intent_type, a, b


def calc_p_score(related_text):
    """약사근거 배수 계산: P = 0.7 + 0.6 × min(n, 3) / 3"""
    matched = [w for w in PHARMA_KEYWORDS if w in related_text]
    n = len(matched)
    p_score = 0.7 + 0.6 * min(n, 3) / 3
    return round(p_score, 2), matched


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3.5단계: 관련 뉴스 헤드라인 (왜 급등했는지 맥락 제공)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_keyword_news(keyword, count=2):
    """해당 키워드의 최신 뉴스 헤드라인 반환"""
    items = fetch_naver_news(keyword, display=10, sort="date")
    headlines = []
    for item in items[:count]:
        title = re.sub(r"<[^>]+>", "", item.get("title", ""))
        link = item.get("link", "")
        headlines.append({"title": title, "link": link})
    return headlines


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4단계: G — 전문가 갭 (일반 콘텐츠 vs 전문가 콘텐츠 비율)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_blog_total_count(query):
    """네이버 블로그 검색 → totalCount 반환"""
    url = "https://openapi.naver.com/v1/search/blog.json"
    params = {"query": query, "display": 1}
    try:
        r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("total", 0)
    except Exception:
        return 0


def calc_g_score(keyword):
    """전문가 갭 배수 계산: 일반 콘텐츠 대비 전문가 콘텐츠 비율"""
    total = _get_blog_total_count(keyword)
    time.sleep(0.1)
    expert = _get_blog_total_count(f"{keyword} 약사")

    gap_ratio = total / (expert + 1)

    # total < 5: 수요 자체가 없음
    if total < 5:
        g_score = 0.7
        g_label = "수요 없음"
    elif gap_ratio >= 30:
        g_score = 1.3
        g_label = "전문가 갭 큼"
    elif gap_ratio >= 10:
        g_score = 1.1
        g_label = "전문가 부족"
    elif gap_ratio >= 3:
        g_score = 1.0
        g_label = "보통"
    else:
        g_score = 0.7
        g_label = "전문가 포화"

    return g_score, total, expert, gap_ratio, g_label


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5단계: Y — 유튜브 선행 배수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def search_youtube(keyword):
    """YouTube Data API로 최근 48시간 내 급등 영상 검색"""
    if not YOUTUBE_API_KEY:
        return 1.0, []

    url = "https://www.googleapis.com/youtube/v3/search"
    published_after = (datetime.utcnow() - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": 5,
        "regionCode": "KR",
        "relevanceLanguage": "ko",
        "key": YOUTUBE_API_KEY,
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])

        if not items:
            return 1.0, []

        # 조회수 확인을 위해 video ID 수집
        video_ids = [item["id"]["videoId"] for item in items if "videoId" in item.get("id", {})]
        if not video_ids:
            return 1.0, []

        # 조회수 조회
        stats_url = "https://www.googleapis.com/youtube/v3/videos"
        stats_params = {
            "part": "statistics,snippet",
            "id": ",".join(video_ids),
            "key": YOUTUBE_API_KEY,
        }
        sr = requests.get(stats_url, params=stats_params, timeout=10)
        sr.raise_for_status()

        videos = []
        max_views = 0
        for v in sr.json().get("items", []):
            views = int(v.get("statistics", {}).get("viewCount", 0))
            title = v.get("snippet", {}).get("title", "")
            channel = v.get("snippet", {}).get("channelTitle", "")
            published = v.get("snippet", {}).get("publishedAt", "")
            if views > max_views:
                max_views = views
            videos.append({
                "title": title,
                "channel": channel,
                "views": views,
                "published": published,
                "video_id": v["id"],
            })

        if max_views >= 100000:
            y_score = 1.3
        elif max_views >= 30000:
            y_score = 1.15
        else:
            y_score = 1.0

        return y_score, videos

    except Exception as e:
        print(f"  [ERROR] YouTube 검색 실패 ({keyword}): {e}")
        return 1.0, []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5.5단계: 연관 키워드 확장 (네이버 자동완성)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_autocomplete_keywords(keyword, max_results=5):
    """네이버 자동완성 API로 연관 키워드 조회"""
    url = "https://ac.search.naver.com/nx/ac"
    params = {"q": keyword, "con": 1, "frm": "nv", "ans": 2}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://search.naver.com/",
        "Accept": "application/json, text/javascript, */*",
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        # 자동완성 결과는 items[0] 배열에 [키워드, ...] 형태
        items = data.get("items", [])
        if not items:
            return []
        suggestions = []
        for group in items:
            for item in group:
                kw = item[0] if isinstance(item, list) else str(item)
                # 원본 키워드와 동일한 건 제외
                if kw != keyword and kw not in suggestions:
                    suggestions.append(kw)
        return suggestions[:max_results]
    except Exception as e:
        print(f"  [ERROR] 자동완성 실패 ({keyword}): {e}")
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6단계: 약업계 뉴스 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def collect_pharma_news():
    """약업계 뉴스 크롤링 (네이버 뉴스 검색 기반)"""
    print("\n" + "=" * 50)
    print("6단계: 약업계 뉴스 수집")
    print("=" * 50)

    queries = ["식약처 허가", "의약품 공급중단", "의약품 리콜", "약사공론",
               "팜뉴스", "건기식 규제", "의약품 안전성"]
    headlines = []

    for q in queries:
        items = fetch_naver_news(q, display=20)
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            link = item.get("link", "")
            pub_date = item.get("pubDate", "")

            # 트리거 단어 확인
            signal = None
            for trigger in STRONG_TRIGGERS:
                if trigger in title:
                    signal = "strong"
                    break
            if not signal:
                for trigger in NORMAL_TRIGGERS:
                    if trigger in title:
                        signal = "normal"
                        break

            # 글로벌 약물 언급 확인
            global_mention = None
            for drug in GLOBAL_DRUGS:
                if drug.lower() in title.lower():
                    global_mention = drug
                    break

            if signal or global_mention:
                headlines.append({
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "signal": signal or "global",
                    "trigger": global_mention or next(
                        (t for t in STRONG_TRIGGERS + NORMAL_TRIGGERS if t in title), ""),
                })
        time.sleep(0.1)

    # 중복 제거
    seen = set()
    unique = []
    for h in headlines:
        if h["title"] not in seen:
            seen.add(h["title"])
            unique.append(h)

    print(f"  약업계 뉴스: {len(unique)}건")
    for h in unique[:10]:
        icon = "🔴" if h["signal"] == "strong" else ("🟡" if h["signal"] == "normal" else "🌐")
        print(f"    {icon} {h['title']}")

    return unique


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7단계: 유튜브 급등 (네이버에 아직 안 온 것)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def find_youtube_only_trends():
    """유튜브에서는 터졌지만 네이버에 아직 안 온 주제 탐지"""
    print("\n" + "=" * 50)
    print("7단계: 유튜브 급등 탐지")
    print("=" * 50)

    if not YOUTUBE_API_KEY:
        print("  [SKIP] YouTube API 키 없음")
        return []

    yt_queries = ["영양제", "건강기능식품", "약사", "비타민", "유산균",
                  "다이어트약", "비만치료제"]
    hot_videos = []

    for q in yt_queries:
        url = "https://www.googleapis.com/youtube/v3/search"
        published_after = (datetime.utcnow() - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "part": "snippet",
            "q": q,
            "type": "video",
            "order": "viewCount",
            "publishedAfter": published_after,
            "maxResults": 5,
            "regionCode": "KR",
            "relevanceLanguage": "ko",
            "key": YOUTUBE_API_KEY,
        }
        try:
            r = requests.get(url, params=params, timeout=10)
            r.raise_for_status()
            items = r.json().get("items", [])
            video_ids = [item["id"]["videoId"] for item in items
                         if "videoId" in item.get("id", {})]
            if not video_ids:
                continue

            stats_r = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"part": "statistics,snippet", "id": ",".join(video_ids),
                        "key": YOUTUBE_API_KEY},
                timeout=10,
            )
            stats_r.raise_for_status()

            for v in stats_r.json().get("items", []):
                views = int(v.get("statistics", {}).get("viewCount", 0))
                if views >= 30000:
                    hot_videos.append({
                        "title": v["snippet"]["title"],
                        "channel": v["snippet"]["channelTitle"],
                        "views": views,
                        "published": v["snippet"]["publishedAt"],
                        "video_id": v["id"],
                        "query": q,
                    })
        except Exception as e:
            print(f"  [ERROR] YouTube ({q}): {e}")
        time.sleep(0.2)

    # 조회수 내림차순 정렬, 중복 제거
    seen = set()
    unique = []
    for v in sorted(hot_videos, key=lambda x: x["views"], reverse=True):
        if v["video_id"] not in seen:
            seen.add(v["video_id"])
            unique.append(v)

    print(f"  유튜브 급등 영상: {len(unique)}건")
    for v in unique[:5]:
        print(f"    🎬 {v['title']} — {v['channel']} ({v['views']:,}회)")

    return unique[:10]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인: 전체 파이프라인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def judge(score):
    if score >= 80:
        return "now"
    elif score >= 40:
        return "good"
    elif score >= 15:
        return "maybe"
    else:
        return "pass"


def score_keyword(kw, news_count, skip_youtube, parent=None):
    """단일 키워드의 H, I, P, G, Y 점수를 산출하고 결과 dict 반환. H=0이면 None 반환."""
    prefix = f"    [{'+' if parent else ''}] " if parent else "    "

    # H — 주제 온도
    change_rate, current_vol = get_search_trend(kw)
    h = calc_h_score(change_rate, news_count=news_count)
    print(f"{prefix}H={h} (변화율 {change_rate:+.0f}%)")
    time.sleep(0.15)

    if h == 0:
        print(f"{prefix}→ H=0이므로 스킵")
        return None

    # 관련 뉴스 헤드라인
    news_headlines = get_keyword_news(kw, count=2)
    for nh in news_headlines:
        print(f"{prefix}📰 {nh['title'][:50]}")
    time.sleep(0.1)

    # I, P — 동반 검색어 분석
    related = get_related_keywords(kw)
    time.sleep(0.15)

    i_score, intent_type, doubt_n, shop_n = calc_i_score(related)
    print(f"{prefix}I={i_score} ({intent_type})")

    p_score, pharma_matched = calc_p_score(related)
    print(f"{prefix}P={p_score} (매칭: {', '.join(pharma_matched) if pharma_matched else '없음'})")

    # G — 전문가 갭
    g_score, g_total, g_expert, g_ratio, g_label = calc_g_score(kw)
    print(f"{prefix}G={g_score} (후기 {g_total}건 vs 전문가 {g_expert}건, {g_label})")
    time.sleep(0.15)

    # Y — 유튜브
    if skip_youtube:
        y_score, yt_videos = 1.0, []
    else:
        y_score, yt_videos = search_youtube(kw)
        time.sleep(0.15)
    print(f"{prefix}Y={y_score}")

    # 최종 점수
    total = round(h * i_score * p_score * g_score * y_score, 1)
    verdict = judge(total)
    print(f"{prefix}★ 점수 = {total} → {verdict}")

    result = {
        "keyword": kw,
        "score": total,
        "verdict": verdict,
        "h": h, "change_rate": round(change_rate, 1),
        "i": i_score, "intent_type": intent_type,
        "p": p_score, "pharma_keywords": pharma_matched,
        "g": g_score, "g_total": g_total, "g_expert": g_expert,
        "g_label": g_label,
        "y": y_score, "yt_videos": yt_videos[:2],
        "news_headlines": news_headlines,
    }
    if parent:
        result["parent"] = parent
    return result


def main():
    skip_youtube = "--skip-youtube" in sys.argv

    print(f"\n{'#' * 50}")
    print(f"  건강·약 트렌드 스캐너 — {datetime.now().strftime('%Y.%m.%d %H:%M')}")
    if skip_youtube:
        print(f"  [모드] 실시간 갱신 (유튜브 스킵)")
    print(f"{'#' * 50}\n")

    # 1. 키워드 자동 추출
    keyword_data = extract_keywords_from_news()  # [(keyword, news_count), ...]

    if not keyword_data:
        print("\n[!] 추출된 키워드가 없습니다. 시드 키워드로 대체합니다.")
        keyword_data = [(kw, 5) for kw in
                        ["마운자로", "위고비", "오젬픽", "비타민D", "유산균",
                         "글루타치온", "콜라겐", "오메가3", "NMN", "코엔자임Q10"]]

    # 상위 30개 키워드만 분석 (API 호출 절약)
    keyword_data = keyword_data[:30]

    # 2~5. 각 키워드별 점수 산출
    print("\n" + "=" * 50)
    print("2~5단계: 키워드별 점수 산출")
    print("=" * 50)

    topics = []
    scored_keywords = set()  # 이미 점수 매긴 키워드 (중복 방지)

    for i, (kw, news_count) in enumerate(keyword_data):
        print(f"\n  [{i+1}/{len(keyword_data)}] {kw} (뉴스 {news_count}건)")
        scored_keywords.add(kw)

        result = score_keyword(kw, news_count, skip_youtube)
        if result:
            topics.append(result)

    # 5.5단계: 연관 키워드 확장 (상위 10개 키워드)
    print("\n" + "=" * 50)
    print("5.5단계: 연관 키워드 확장")
    print("=" * 50)

    # 현재 상위 10개를 parent로 사용
    top_for_expansion = sorted(topics, key=lambda x: x["score"], reverse=True)[:10]
    related_topics = []

    for t in top_for_expansion:
        parent_kw = t["keyword"]
        print(f"\n  [{parent_kw}] 연관검색어 조회...")
        suggestions = get_autocomplete_keywords(parent_kw, max_results=5)
        time.sleep(0.1)

        if not suggestions:
            print(f"    → 연관검색어 없음")
            continue

        print(f"    자동완성: {suggestions}")

        for rel_kw in suggestions:
            if rel_kw in scored_keywords:
                print(f"    [{rel_kw}] 이미 분석됨, 스킵")
                continue
            scored_keywords.add(rel_kw)

            print(f"\n    + 연관: {rel_kw} (← {parent_kw})")
            result = score_keyword(rel_kw, 0, skip_youtube, parent=parent_kw)
            if result:
                related_topics.append(result)

    print(f"\n  연관 키워드에서 {len(related_topics)}개 추가 발견")

    # 기존 + 연관 키워드 합쳐서 점수순 정렬
    topics.extend(related_topics)
    topics.sort(key=lambda x: x["score"], reverse=True)

    # 6. 약업계 뉴스
    pharma_news = collect_pharma_news()

    # 7. 유튜브 급등
    # skip_youtube면 이전 데이터 재사용
    prev_yt_trends = []
    prev_yt_updated = ""
    output_path = os.path.join(DATA_DIR, "latest.json")
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                prev = json.load(f)
            prev_yt_trends = prev.get("youtube_trends", [])
            prev_yt_updated = prev.get("youtube_updated_at", "")
        except Exception:
            pass

    if skip_youtube:
        print("\n[SKIP] 유튜브 — 이전 데이터 재사용")
        youtube_trends = prev_yt_trends
        yt_updated = prev_yt_updated or "이전 데이터"
    else:
        youtube_trends = find_youtube_only_trends()
        yt_updated = datetime.now().strftime("%Y-%m-%d %H:%M")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 결과 저장
    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "updated_at": now_str,
        "naver_updated_at": now_str,
        "youtube_updated_at": yt_updated,
        "topics": topics,
        "pharma_news": pharma_news[:15],
        "youtube_trends": youtube_trends,
    }

    output_path = os.path.join(DATA_DIR, "latest.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    # 히스토리 누적 저장
    history_dir = os.path.join(DATA_DIR, "history")
    os.makedirs(history_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    history_path = os.path.join(history_dir, f"{ts}.json")
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 50}")
    print(f"완료! 결과 저장: {output_path}")
    print(f"히스토리 저장: {history_path}")
    print(f"  글감 {len(topics)}개 분석, 약업계 뉴스 {len(pharma_news)}건")
    print(f"{'=' * 50}")

    return result


if __name__ == "__main__":
    main()
