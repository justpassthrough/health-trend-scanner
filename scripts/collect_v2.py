"""
건강 트렌드 스캐너 v2 — AI 기반 글감 발굴 파이프라인
GitHub Actions에서 하루 2회 (08:00, 20:00 KST) 자동 실행
"""

import os
import sys
import json
import re
import time
import math
import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests

# ── 인코딩 (Windows cp949 방지) ──
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# ── 로컬 테스트용 .env 로드 (있으면) ──
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
except Exception:
    pass

# ── API 키 ──
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── AI 실행 방식 (2026-09-17) ──
# 기본은 구독제 Claude Code CLI(`claude -p`, 미니PC에서 로컬 실행 — API 과금 없음, Opus).
# CLI 가 없을 때만(예: GitHub Actions 수동 실행) ANTHROPIC_API_KEY 로 Haiku API 폴백.
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
CLAUDE_MODEL = os.environ.get("TREND_CLAUDE_MODEL", "opus")
CLAUDE_TIMEOUT_SEC = int(os.environ.get("TREND_CLAUDE_TIMEOUT_SEC", "900"))
# 실제 검색 화면 확인(집 IP 에서만 가능): video-auto 의 serp-check 를 불러 쓴다. 비우면 건너뜀.
SERP_CHECK_DIR = os.environ.get("SERP_CHECK_DIR", "")
REWRITE_AFTER_DAYS = 15

# ── 검색광고 키워드도구 API 키 (월간 절대 검색수 + 경쟁정도) ──
NAVER_AD_CUSTOMER_ID = os.environ.get("NAVER_AD_CUSTOMER_ID", "")
NAVER_AD_API_KEY = os.environ.get("NAVER_AD_API_KEY", "")
NAVER_AD_SECRET_KEY = os.environ.get("NAVER_AD_SECRET_KEY", "")
SEARCHAD_BASE = "https://api.searchad.naver.com"

NAVER_HEADERS = {
    "X-Naver-Client-Id": NAVER_CLIENT_ID,
    "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
}

# ── 경로 ──
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCANS_DIR = os.path.join(DATA_DIR, "scans")
os.makedirs(SCANS_DIR, exist_ok=True)

# ── 내 블로그 글 목록 (inflow-keyword-analyzer 레포에서 자동 갱신) ──
MY_POSTS_URL = (
    "https://raw.githubusercontent.com/"
    "justpassthrough/inflow-keyword-analyzer/main/data/my_posts.json"
)

# ── 씨드 쿼리 (카테고리별) ──
SEED_QUERIES = {
    "영양제·성분": [
        "영양제 신제품", "건강기능식품 트렌드", "비타민 연구",
        "프로바이오틱스 신제품", "영양제 부작용", "건기식 허가",
        "오메가3", "루테인", "코엔자임Q10", "마그네슘",
        "콜라겐 영양제", "글루타치온",
    ],
    "약업계·정책": [
        "식약처 허가", "건강보험 적용 약", "약가 인하",
        "의약품 품절", "의약품 리콜", "약사회 뉴스",
        "제약 신약 허가", "의약품 안전성",
    ],
    "질환·치료": [
        "비만치료제 신약", "탈모 치료 신약", "당뇨 신약",
        "고혈압 가이드라인", "알레르기 치료", "수면장애 약",
        "GLP-1 신약", "항암제 신약",
    ],
    "소비자건강": [
        "다이어트 유행 성분", "피부관리 성분", "수면 보조제",
        "눈 건강 영양제", "관절 건강 영양제", "장 건강",
        "탈모 샴푸 성분", "구강건강", "갱년기 영양제",
    ],
}

# ── 건강 맥락 확인용 단어 ──
HEALTH_CONTEXT_WORDS = {
    "건강", "의약", "약국", "약사", "병원", "치료", "처방", "복용",
    "영양", "비타민", "식품", "성분", "부작용", "효과", "증상", "효능",
    "질환", "감염", "백신", "면역", "진단", "환자", "임상", "허가",
    "식약처", "다이어트", "비만", "체중", "혈압", "혈당", "콜레스테롤",
    "유산균", "프로바이오틱스", "오메가", "콜라겐", "글루타치온",
    "영양제", "건기식", "의약품", "약물", "제형",
    "당뇨", "고혈압", "암", "종양", "알레르기",
    "루테인", "마그네슘", "코엔자임", "크릴오일", "아연", "철분",
    "탈모", "관절", "수면", "갱년기", "전립선", "눈건강",
    "리콜", "품절", "급여", "약가", "건강보험",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1단계: 데이터 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def fetch_naver_news(query, display=30, sort="date"):
    """네이버 뉴스 검색 API 호출"""
    url = "https://openapi.naver.com/v1/search/news.json"
    params = {"query": query, "display": display, "sort": sort}
    try:
        r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:
        print(f"  [WARN] 뉴스 검색 실패 ({query}): {e}")
        return []


def collect_news():
    """카테고리별 씨드 쿼리로 뉴스 수집, 중복 제거 후 반환"""
    print("=" * 50)
    print("1단계: 뉴스 수집")
    print("=" * 50)

    news_by_category = {}
    seen_titles = set()
    total = 0

    for category, queries in SEED_QUERIES.items():
        category_news = []
        for q in queries:
            items = fetch_naver_news(q, display=30)
            time.sleep(0.1)  # API 속도 제한
            for item in items:
                title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
                desc = re.sub(r"<[^>]+>", "", item.get("description", "")).strip()

                # 건강 맥락 필터
                combined = title + " " + desc
                if not any(w in combined for w in HEALTH_CONTEXT_WORDS):
                    continue

                # 중복 제거 (제목 기준)
                title_norm = re.sub(r"\s+", "", title)
                if title_norm in seen_titles:
                    continue
                seen_titles.add(title_norm)

                category_news.append({
                    "title": title,
                    "description": desc[:150],  # 토큰 절약
                    "link": item.get("link", ""),
                })

        news_by_category[category] = category_news
        total += len(category_news)
        print(f"  {category}: {len(category_news)}건")

    print(f"  → 총 {total}건 (중복 제거 후)")
    return news_by_category


def load_my_posts():
    """내 블로그 글 목록 로드 (inflow-keyword-analyzer 레포)"""
    print("\n" + "=" * 50)
    print("내 블로그 글 목록 로드")
    print("=" * 50)

    try:
        r = requests.get(MY_POSTS_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        # my_posts.json 구조: { "blog_id": ..., "posts": [...] }
        if isinstance(data, dict):
            posts = data.get("posts", [])
        elif isinstance(data, list):
            posts = data
        else:
            posts = []
        print(f"  → {len(posts)}개 글 로드 완료")
        return posts
    except Exception as e:
        print(f"  [WARN] 글 목록 로드 실패: {e}")
        print("  → 빈 목록으로 진행 (이미 작성 여부 판단 불가)")
        return []


def get_search_trend(keyword):
    """네이버 DataLab API로 최근 검색량 변화율 계산"""
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
            return 0.0, 0.0

        points = results[0]["data"]
        if len(points) < 14:
            return 0.0, 0.0

        recent = [p.get("ratio", 0) for p in points[-7:]]
        previous = [p.get("ratio", 0) for p in points[-14:-7]]

        avg_recent = sum(recent) / len(recent) if recent else 0
        avg_previous = sum(previous) / len(previous) if previous else 0

        if avg_previous == 0:
            change_rate = 300.0 if avg_recent > 0 else 0.0
        else:
            change_rate = ((avg_recent - avg_previous) / avg_previous) * 100

        return round(change_rate, 1), round(avg_recent, 1)

    except Exception as e:
        print(f"    [WARN] DataLab 실패 ({keyword}): {e}")
        return 0.0, 0.0


def get_expert_gap(keyword):
    """전문가 갭 계산: 전체 블로그 수 vs '약사' 포함 블로그 수"""
    url = "https://openapi.naver.com/v1/search/blog.json"

    try:
        # 전체 블로그
        r = requests.get(url, headers=NAVER_HEADERS,
                         params={"query": keyword, "display": 1}, timeout=10)
        r.raise_for_status()
        total = r.json().get("total", 0)

        time.sleep(0.1)

        # 약사 블로그
        r = requests.get(url, headers=NAVER_HEADERS,
                         params={"query": f"{keyword} 약사", "display": 1}, timeout=10)
        r.raise_for_status()
        expert = r.json().get("total", 0)

        gap_ratio = total / (expert + 1)

        if total < 100:
            label = "수요 적음"
        elif gap_ratio >= 30:
            label = "전문가 갭 큼"
        elif gap_ratio >= 10:
            label = "전문가 부족"
        elif gap_ratio >= 3:
            label = "보통"
        else:
            label = "전문가 포화"

        return {
            "total_blogs": total,
            "expert_blogs": expert,
            "gap_ratio": round(gap_ratio, 1),
            "label": label,
        }

    except Exception as e:
        print(f"    [WARN] 전문가갭 실패 ({keyword}): {e}")
        return {
            "total_blogs": 0,
            "expert_blogs": 0,
            "gap_ratio": 0,
            "label": "확인불가",
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 검색광고 키워드도구 API (월간 절대 검색수 + 경쟁정도)
#   - 키워드 딥다이브 툴에서 검증된 코드를 이식
#   - DataLab은 '상대 트렌드'만 주므로, '절대 수요'를 메우는 핵심 보강
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _searchad_signature(timestamp, method, path):
    """검색광고 API용 HMAC-SHA256 서명 생성."""
    message = f"{timestamp}.{method}.{path}"
    digest = hmac.new(
        NAVER_AD_SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _parse_qc(value):
    """월간검색수 파싱. '< 10' 같은 문자열 → 정수."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        v = value.replace("<", "").replace(",", "").strip()
        if v.isdigit():
            return int(v)
        return 9  # "< 10" 류는 9로 근사
    return 0


def fetch_search_volume(keywords):
    """검색광고 API로 키워드들의 월간검색수(PC+모바일)와 경쟁정도 조회.
    keywords: 문자열 리스트. 반환: {키워드(공백제거,대문자): {pc, mobile, total, comp_idx}}.
    키가 없으면 빈 dict 반환(있는 기능에 영향 없음)."""
    result = {}
    if not (NAVER_AD_CUSTOMER_ID and NAVER_AD_API_KEY and NAVER_AD_SECRET_KEY):
        print("  [검색광고] 키 없음 — 검색량 조회 스킵 (기회점수는 약사가치 폴백)")
        return result
    path = "/keywordstool"
    # API는 한 번에 hintKeywords 최대 5개 권장 → 5개씩 배치
    for i in range(0, len(keywords), 5):
        batch = keywords[i:i + 5]
        # 검색광고 API는 키워드의 공백을 무시함 → 공백 제거해서 전달
        hint = ",".join(k.replace(" ", "") for k in batch)
        timestamp = str(int(time.time() * 1000))
        headers = {
            "X-Timestamp": timestamp,
            "X-API-KEY": NAVER_AD_API_KEY,
            "X-Customer": str(NAVER_AD_CUSTOMER_ID),
            "X-Signature": _searchad_signature(timestamp, "GET", path),
        }
        try:
            r = requests.get(
                SEARCHAD_BASE + path,
                headers=headers,
                params={"hintKeywords": hint, "showDetail": "1"},
                timeout=10,
            )
            if r.status_code != 200:
                print(f"  [검색광고 경고] status {r.status_code}: {r.text[:120]}")
                time.sleep(0.5)
                continue
            for item in r.json().get("keywordList", []):
                rel = item.get("relKeyword", "")
                key = rel.replace(" ", "").upper()
                pc = _parse_qc(item.get("monthlyPcQcCnt", 0))
                mo = _parse_qc(item.get("monthlyMobileQcCnt", 0))
                # 같은 배치에서 hint로 넣은 키워드는 정확매칭만 채택(연관어 노이즈 방지)
                result[key] = {
                    "pc": pc,
                    "mobile": mo,
                    "total": pc + mo,
                    "comp_idx": item.get("compIdx", ""),
                }
        except Exception as e:
            print(f"  [검색광고 경고] {e}")
        time.sleep(0.4)  # rate limit 보호
    return result


def lookup_volume(volume_map, keyword):
    """fetch_search_volume 결과에서 특정 키워드의 지표를 안전하게 꺼냄."""
    return volume_map.get(keyword.replace(" ", "").upper())


# ── 점수 계산 헬퍼 (2트랙) ──

def _expert_gap_mult(gap):
    """전문가갭 비율 → 배수(0.7~1.3). 약사가 비집고 들어갈 틈이 클수록 높음."""
    ratio = gap.get("gap_ratio", 0) or 0
    total = gap.get("total_blogs", 0) or 0
    if total < 100:
        return 0.9  # 표본 적음 → 중립 근처
    if ratio >= 30:
        return 1.3
    if ratio >= 10:
        return 1.1
    if ratio >= 3:
        return 1.0
    return 0.7  # 포화


def calc_pharma_value(pharma_value_raw, gap):
    """약사가치 = AI가 매긴 전문성점수(1~5) × 전문가갭배수. 시점 무관 '적합도'."""
    pv = pharma_value_raw if isinstance(pharma_value_raw, (int, float)) else 3
    pv = max(1, min(5, pv))
    return round(pv * _expert_gap_mult(gap), 2)


# 검색형 최소 수요 하한: 월검색량이 이 값 미만이거나 데이터가 없으면
# '유입 거의 없는 글감'으로 보고 정렬에서 맨 뒤로 밀어냄(제외가 아니라 하향).
# keyword-deep-dive의 100회 기준과 동일하게 맞춤.
DEMAND_MIN = 100


def has_demand(topic):
    """검색형 글감이 '실제 검색 수요'가 있는지 판정. 정렬 1차 키로 사용."""
    sv = topic.get("search_volume")
    if isinstance(topic.get("shopping_rank"), int) and topic["shopping_rank"] <= 300:
        return True   # 검색광고의 월 검색량은 지난 30일 평균이라 막 뜬 말은 작게 나온다 — 쇼핑 순위 300위 안이면 수요로 인정
    return isinstance(sv, (int, float)) and sv >= DEMAND_MIN


def calc_opportunity(search_volume, comp_idx, pharma_value, position=None):
    """검색형 기회점수 = 약사가치 × 수요배수(log10 검색량) × 자리배수.
    자리배수 = 실제 검색 화면에서 블로그 영역 위치·쇼핑 덮임(position_mult). 화면을 못 봤으면(Actions 실행 등)
    예전처럼 광고 경쟁도로 폴백 — 광고 경쟁도는 광고주 입찰 경쟁이라 상위노출과는 거리가 있다.
    검색량 없으면 None(→ 약사가치로 폴백)."""
    if search_volume is None:
        return None
    # log10(검색량)/2: 100회=1.0, 2500회≈1.7, 1.1만회≈2.0, 23만회≈2.7
    demand_mult = math.log10(max(search_volume, 10)) / 2
    spot = position if position is not None else {"낮음": 1.2, "중간": 1.0, "높음": 0.8}.get(comp_idx, 1.0)
    return round(pharma_value * demand_mult * spot, 1)


def opportunity_label(search_volume, comp_idx):
    """검색량·경쟁도 조합을 사람이 읽을 라벨로."""
    if search_volume is None:
        return None
    if search_volume < 100:
        return "수요 적음"
    if search_volume >= 500 and comp_idx == "낮음":  # 차트 분할선(DEMAND_SPLIT)과 동일 기준
        return "💎황금(수요多·경쟁低)"
    if comp_idx == "낮음":
        return "양호(경쟁 낮음)"
    if comp_idx == "높음":
        return "포화(경쟁 높음)"
    return "보통"


def calc_timeliness(pharma_value, recency, change_rate, already_covered,
                    consecutive_days, news_count):
    """시의형 시의점수 — '지금 막 뜨는 새 주제'를 최상단으로.
    1순위 = 신선도(최신 기사 경과시간 + 24h 기사 다발), 그 다음 신규성(이미 쓴 주제 강하게 하향),
    급등(보조), 뉴스 규모(약한 보조). 뉴스량은 일부러 약하게 둠 — 큰 옛이슈가 위로 가지 않게."""
    recency = recency or {}

    # ── 신선도 (PRIMARY) ── 최신 기사가 얼마나 최근인가
    nh = recency.get("newest_hours")
    if nh is None:
        fresh = 0.6          # 최근 기사 못 찾음 = 식은 주제
    elif nh < 24:
        fresh = 1.6          # 하루 안에 터짐
    elif nh < 48:
        fresh = 1.3
    elif nh < 72:
        fresh = 1.1
    elif nh < 168:
        fresh = 0.9          # 1주일 이내
    else:
        fresh = 0.5          # 1주일 넘음 = 식은 떡
    # 24시간 기사 다발 = 지금 폭발 중
    c24 = recency.get("count_24h", 0)
    if c24 >= 10:
        fresh *= 1.25
    elif c24 >= 3:
        fresh *= 1.1

    # ── 신규성 ── 이미 쓴 주제 강하게 하향 / 첫 등장 가산
    if already_covered:
        nov = 0.4
    elif consecutive_days and consecutive_days >= 4:
        nov = 0.8            # 며칠째 계속 = 신선함 줄어듦
    elif consecutive_days == 1:
        nov = 1.15           # 오늘 처음 등장
    else:
        nov = 1.0

    # ── 급등 (보조) ──
    cr = change_rate or 0
    spike = 1.2 if cr >= 20 else (0.9 if cr <= -20 else 1.0)

    # ── 뉴스 규모 (약한 보조) ── 10건=1.0, 1000건=1.3, 1만건=1.45
    vol = 1 + (math.log10(max(news_count or 0, 10)) - 1) * 0.15

    base = pharma_value if pharma_value else 3
    return round(base * fresh * nov * spike * vol, 1)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2단계: AI 분석
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_ai_prompt(news_by_category, my_posts, movers=None, recent_suggestions=None, uncovered=None):
    """AI 프롬프트 구성"""
    movers = movers or []
    uncovered_block = ", ".join(f"{k}({r}위)" for k, r in (uncovered or [])) or "없음"
    movers_block = "\n".join(
        f"- {m['keyword']} ({m['kind']}: 지금 {m['rank']}위" + (f", 전에는 {m['from_rank']}위" if m.get("from_rank") else "") + ")"
        for m in movers) or "수집된 순위 없음"
    recent_block = ", ".join(recent_suggestions or []) or "없음"

    # 내 블로그 글 제목 목록
    post_titles = []
    for p in sorted(my_posts, key=lambda x: x.get("date", ""), reverse=True):
        title = p.get("title", "")
        if title:
            post_titles.append(f"{p.get('date', '')} {title}".strip())
    posts_block = "\n".join(f"- {t}" for t in post_titles)  # 전체(예전엔 50개만 넣어 나머지와 겹치는 글감이 나왔다)

    # 카테고리별 뉴스 블록
    news_blocks = {}
    for category, articles in news_by_category.items():
        lines = []
        for a in articles[:25]:  # 카테고리당 최대 25개 (토큰 절약)
            lines.append(f"- {a['title']}")
            if a["description"]:
                lines.append(f"  → {a['description'][:100]}")
        news_blocks[category] = "\n".join(lines)

    prompt = f"""당신은 병원 약사이자 약물전달(DDS) 연구자가 운영하는 네이버 건강 블로그의 콘텐츠 전략가입니다.

[목표]
아래 오늘의 뉴스를 분석하여, 이 블로거가 새롭게 확장할 수 있는 글감을 찾아주세요.

[가장 중요한 규칙 — 글감을 두 종류(track)로 나눕니다]
모든 글감은 반드시 둘 중 하나로 분류하세요. 두 종류 모두 골고루 뽑아야 합니다.

① track = "검색형" (에버그린 / 사람들이 검색창에 직접 치는 것)
   - 성분명·영양제·제품·증상처럼 소비자가 평소에 검색하는 주제
   - 예: 감마오리자놀, 바나바잎, 리포좀비타민C, 시서스추출물, 루테인, 글루타치온
   - 이 트랙은 '실제 검색 수요'로 평가되므로 keyword가 **반드시 짧은 실제 검색어**여야 함

② track = "시의형" (지금 막 터진 뉴스 / 산업·정책·신약)
   - 평소 검색량은 적지만 지금 이슈가 된 약업계·정책·신약·허가·품절·리콜·산업 소식
   - 예: 탈모약 건강보험, 위고비 품절, 종근당 비만신약, 식약처 리콜
   - 이 트랙은 '뉴스 규모와 시의성'으로 평가됨. 산업/주식/희귀질환 신약 뉴스도 여기 포함(필터링하지 말 것)

[keyword 작성 규칙 — 매우 중요]
- keyword는 **네이버 검색창에 그대로 칠 수 있는 짧은 단어/구**여야 합니다 (보통 2~12자).
- 문장으로 쓰지 마세요. 괄호 설명을 넣지 마세요.
  - 나쁨: "GLP-1 계열 비만치료제 복용 중 탈모 위험" (← 문장, 검색 안 됨)
  - 좋음: keyword="비만치료제 탈모", track="검색형"
  - 나쁨: "경구용 GLP-1 비만치료제 (HK이노엔, 종근당 CKD-514 등)"
  - 좋음: keyword="먹는 비만약", track="시의형"
- 길게 설명하고 싶은 내용은 keyword가 아니라 why_now / pharmacist_angle / title_idea 에 쓰세요.

[entity / search_terms — 실제 검색어에 붙이기 위한 필드. 매우 중요]
- entity: 이 글감의 핵심 대상 **하나**(성분·약·제품·질환·제도 이름). 한 단어 또는 고유 이름. 예: "NMN", "통풍", "미프진", "타우린"
- search_terms: 일반인이 네이버 검색창에 **실제로 칠 법한** 검색어 후보 3개. 각각 1~2단어(최대 3단어), 조사·문장 금지.
  - 뉴스에 나온 단어를 이어 붙이지 마세요. "고단백 다이어트 통풍", "음수량 반려묘 식이섬유", "제로 무알코올 맥주 퓨린"은 아무도 검색하지 않습니다.
  - 좋은 예(통풍 글감): ["통풍에 나쁜 음식", "통풍 단백질", "요산 수치 낮추는 법"]
  - 좋은 예(고양이 타우린): ["고양이 타우린", "고양이 타우린 영양제", "타우린 고양이 용량"]
  - 코드가 이 후보들의 실제 월 검색량을 조회해 가장 나은 것을 대표 검색어로 씁니다. 자신 없으면 대상 이름에 흔한 의도어(부작용·효능·먹는법·가격·추천·차이)를 붙인 꼴을 넣으세요.

[쇼핑 인기검색어 — 건강식품 분야에서 새로 진입했거나 급상승한 검색어 (소비자가 실제로 찾기 시작한 것)]
이 목록이 '아예 새로운 글감'의 1순위 재료입니다. 뉴스는 보도자료(제품 홍보)가 많지만 이 목록은 실제 수요입니다.
- 성분·원료·건강 개념 이름(예: 포스파티딜세린, 매스틱, 하스카프베리, 카무트효소)을 골라 검색형 글감으로 만드세요. 이런 항목은 "source": "shopping".
- 특정 브랜드·상품명(정관장, 뉴케어, ○○에브리타임), 선물세트·명절 상품, 식품 일반(꿀, 오미자)은 건너뛰세요. 단, 브랜드 이름에서 성분이 드러나면 그 성분을 대상으로 삼을 수 있습니다.
- 처음 들어 보는 이름이라도 버리지 마세요. 그게 이 도구가 찾는 것입니다. 무엇인지 짐작이 안 되면 pharma_value 를 낮게 주고 why_now 에 "정체 확인 필요"라고 쓰세요.
{movers_block}

[쇼핑 인기검색어 상위권인데 이 블로그가 아직 한 번도 다루지 않은 것 — 순위가 안 움직여도 '나한테는 새 영역']
브랜드·선물·일반 식품은 건너뛰고, 성분·원료 이름만 보세요. 여기서도 1~3개 골라 검색형 글감으로 만드세요("source": "shopping").
{uncovered_block}

[최근 2주 동안 이미 제안했던 대상 — 새 소식(허가·가격·품절·연구 결과)이 없으면 다시 내지 마세요]
{recent_block}

[내 블로그 기존 글 제목]
{posts_block}

[오늘의 뉴스 — 영양제·성분]
{news_blocks.get("영양제·성분", "수집된 뉴스 없음")}

[오늘의 뉴스 — 약업계·정책]
{news_blocks.get("약업계·정책", "수집된 뉴스 없음")}

[오늘의 뉴스 — 질환·치료]
{news_blocks.get("질환·치료", "수집된 뉴스 없음")}

[오늘의 뉴스 — 소비자건강]
{news_blocks.get("소비자건강", "수집된 뉴스 없음")}

[출력 규칙]
반드시 JSON 배열로만 응답하세요. 최소 8개, 최대 15개 항목.
검색형과 시의형을 모두 포함하세요 (검색형 최소 4개, 시의형 최소 3개 권장). 쇼핑 인기검색어에서 온 글감을 최소 4개 포함하세요(목록이 있을 때).
각 항목:
{{
  "keyword": "짧은 검색어 (예: '감마오리자놀', '바나바잎', '탈모약 건강보험', '위고비 품절')",
  "entity": "핵심 대상 하나 (예: '감마오리자놀')",
  "search_terms": ["실제로 칠 법한 검색어 1", "검색어 2", "검색어 3"],
  "track": "검색형 | 시의형",
  "source": "shopping | news  (쇼핑 인기검색어에서 나온 글감이면 shopping)",
  "category": "영양제·성분 | 약업계·정책 | 질환·치료 | 소비자건강",
  "pharma_value": 1~5 정수 (약사/DDS 전문성으로 남들과 차별화할 여지. 5=약사만 쓸 수 있는 깊은 주제, 1=누구나 쓰는 일반 주제),
  "trend_key": "추이 추적용 핵심어 1~3단어. 같은 성분/개념이면 매번 동일하게. 예: '벤포티아민','활성비타민B1','아로나민' → 모두 '벤포티아민'.",
  "why_now": "왜 지금 이 글을 써야 하는지 2~3문장. 뉴스 맥락과 확장 가치를 구체적으로.",
  "pharmacist_angle": "약사/DDS 연구자로서 차별화할 구체적 앵글 1~2문장",
  "title_idea": "블로그 글 제목 아이디어 1개 (클릭 유도형, 약사 전문성 드러나는)",
  "already_covered": false,
  "covered_posts": [],
  "source_headlines": ["근거가 된 뉴스 제목 1~2개 (위 뉴스에서 발췌)"]
}}

[중요]
- already_covered가 true인 경우, covered_posts에 관련된 기존 글 제목을 넣으세요 (최종 판정은 코드가 글 제목·작성일로 다시 합니다. 쓴 지 15일이 지난 주제는 다시 쓸 수 있습니다)
- 새 글감(already_covered=false)이 전체의 60% 이상이어야 합니다
- "비만", "건강" 같은 너무 포괄적인 단어 단독 사용 금지 — 구체적인 성분명/제품명/정책명
- 한국어로 작성"""

    return prompt


def _extract_json_array(raw):
    """AI 응답에서 JSON 배열 문자열만 뽑아낸다 ( ```json``` 감싸기·앞뒤 잡텍스트 제거 )."""
    json_str = raw
    # 1) ```json ... ``` 감싸기
    if "```" in json_str:
        match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", json_str)
        if match:
            json_str = match.group(1)
    # 2) 배열 부분만 추출 (앞뒤 텍스트 제거)
    if not json_str.lstrip().startswith("["):
        match = re.search(r"\[[\s\S]*\]", json_str)
        if match:
            json_str = match.group(0)
    return json_str


def _salvage_json_objects(text):
    """깨진 JSON 배열에서 온전한 최상위 객체 {..} 만 최대한 건져낸다.

    Haiku가 콤마 하나를 빠뜨려도 그날 스캔 전체를 버리지 않도록,
    문자열/이스케이프를 존중하며 중괄호 깊이를 추적해 객체 단위로 개별 파싱한다.
    깨진 객체는 건너뛰고 나머지는 살린다.
    """
    objs = []
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    frag = text[start : i + 1]
                    try:
                        objs.append(json.loads(frag))
                    except json.JSONDecodeError:
                        pass  # 깨진 객체는 버리고 계속
                    start = None
    return objs


def _call_claude_cli(prompt):
    """구독제 Claude Code CLI 로 실행. 반환: (텍스트, 메타). 실패하면 예외."""
    import shutil
    import subprocess
    exe = shutil.which(CLAUDE_BIN) or CLAUDE_BIN
    args = [exe, "-p", "--output-format", "json"]
    if CLAUDE_MODEL:
        args += ["--model", CLAUDE_MODEL]
    # 프롬프트는 stdin 으로(길이·따옴표 문제 회피). cwd 는 저장소 폴더 — 다른 프로젝트의 메모리가 섞이지 않게.
    started = time.time()
    proc = subprocess.run(args, input=prompt.encode("utf-8"), capture_output=True,
                          timeout=CLAUDE_TIMEOUT_SEC, cwd=BASE_DIR)
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 and not out:
        raise RuntimeError(f"claude 종료 코드 {proc.returncode}: {proc.stderr.decode('utf-8', errors='replace')[:300]}")
    try:
        j = json.loads(out)
    except json.JSONDecodeError:
        return out, {"duration_sec": round(time.time() - started)}
    if j.get("is_error"):
        raise RuntimeError(str(j.get("result") or j.get("subtype") or "claude 오류")[:300])
    usage = j.get("usage") or {}
    return str(j.get("result", "")).strip(), {
        "duration_sec": round(time.time() - started),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
    }


def _call_anthropic_api(prompt):
    """폴백: Anthropic API(Haiku). 과금됨 — CLI 를 쓸 수 없는 환경에서만."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=16000,
                                      messages=[{"role": "user", "content": prompt}])
    cost = (response.usage.input_tokens * 1 + response.usage.output_tokens * 5) / 1_000_000
    return response.content[0].text.strip(), {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cost_usd": round(cost, 4),
    }


def run_ai_analysis(news_by_category, my_posts, movers=None, recent_suggestions=None, uncovered=None):
    """Claude 로 글감 후보 추출. 기본은 구독제 CLI(Opus), 없으면 API(Haiku) 폴백."""
    print("\n" + "=" * 50)
    print("2단계: AI 분석")
    print("=" * 50)

    import shutil
    use_cli = bool(shutil.which(CLAUDE_BIN)) and os.environ.get("TREND_AI_BACKEND", "cli") != "api"
    if not use_cli and not ANTHROPIC_API_KEY:
        print("  [ERROR] claude CLI 도 없고 ANTHROPIC_API_KEY 도 없음 — AI 분석 불가")
        return [], {"error": "no ai backend"}
    backend = f"claude-cli:{CLAUDE_MODEL or 'default'}" if use_cli else "api:claude-haiku-4-5-20251001"
    print(f"  실행 방식: {backend}")

    prompt = build_ai_prompt(news_by_category, my_posts, movers, recent_suggestions, uncovered)
    print(f"  프롬프트 길이: {len(prompt)}자")

    max_attempts = 3          # 파싱 깨지면 새로 생성해 재시도
    last_err = None
    cost_total = 0.0
    for attempt in range(1, max_attempts + 1):
        try:
            raw, call_meta = _call_claude_cli(prompt) if use_cli else _call_anthropic_api(prompt)
        except Exception as e:
            last_err = e
            print(f"  [WARN] AI 호출 실패 (시도 {attempt}/{max_attempts}): {e}")
            if attempt < max_attempts:
                time.sleep(10 * attempt)   # CLI 자동 업데이트 중이면 몇 초간 실행이 안 된다
                continue
            return [], {"model": backend, "error": str(e)}

        cost_total += call_meta.get("cost_usd") or 0
        print(f"  응답 길이: {len(raw)}자 · {call_meta}")
        json_str = _extract_json_array(raw)
        try:
            candidates = json.loads(json_str)
        except json.JSONDecodeError as e:
            last_err = e
            print(f"  [WARN] JSON 파싱 실패 (시도 {attempt}/{max_attempts}): {e}")
            candidates = _salvage_json_objects(json_str)
            if candidates:
                print(f"  [복구] 깨진 응답에서 온전한 글감 {len(candidates)}개 건져냄 (일부 손실 가능)")
            elif attempt < max_attempts:
                time.sleep(2)
                continue
            else:
                print(f"  Raw 응답 첫 500자: {raw[:500]}")
                return [], {"model": backend, "error": str(e)}

        candidates = [c for c in candidates if isinstance(c, dict) and c.get("keyword")]
        print(f"  → AI 추천 글감: {len(candidates)}개")
        meta = {"model": backend, "attempts": attempt, "cost_usd": round(cost_total, 4), **{k: v for k, v in call_meta.items() if k != "cost_usd"}}
        return candidates, meta

    return [], {"model": backend, "error": str(last_err)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3단계: 보강 데이터
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_core_keyword(keyword):
    """AI 키워드에서 DataLab/뉴스 검색용 핵심 단어 추출.

    예: "벤포티아민 (활성비타민 B1)" → "벤포티아민"
        "GLP-1 계열 가짜 다이어트 식품 구별법" → "가짜 다이어트 식품"
        "담석증 - GLP-1 비만치료제 부작용" → "담석증 비만치료제"
    """
    # 괄호 안 내용 제거
    core = re.sub(r"\([^)]*\)", "", keyword).strip()
    # " - ", " + ", " vs " 등 구분자로 분리 후 첫 부분 사용
    core = re.split(r"\s+(?:-|\+|vs\.?)\s+", core)[0].strip()   # 예전 [-+vs] 는 글자 v·s 에서도 잘랐다
    # 너무 길면 앞 4단어만
    words = core.split()
    if len(words) > 4:
        core = " ".join(words[:4])
    return core if core else keyword


def get_news_count_and_headlines(keyword, count=3):
    """키워드 관련 뉴스 총 건수(API total) + 상위 헤드라인 반환"""
    url = "https://openapi.naver.com/v1/search/news.json"
    params = {"query": keyword, "display": count, "sort": "sim"}
    try:
        r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        total = data.get("total", 0)
        items = data.get("items", [])
    except Exception as e:
        print(f"    [WARN] 뉴스 건수 조회 실패 ({keyword}): {e}")
        return 0, []

    headlines = []
    for item in items[:count]:
        title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
        link = item.get("link", "")
        pub_date = item.get("pubDate", "")
        headlines.append({"title": title, "link": link, "date": pub_date})
    return total, headlines


def get_news_recency(keyword):
    """'지금 뜨는가'를 기사 발행일로 측정. sort=date(최신순)로 조회해서
    가장 최근 기사가 몇 시간 전인지 + 최근 24/48시간 기사 다발 정도를 반환.
    시의형 글감을 '속보성'으로 줄 세우기 위한 핵심 신호."""
    url = "https://openapi.naver.com/v1/search/news.json"
    params = {"query": keyword, "display": 30, "sort": "date"}
    try:
        r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])
    except Exception as e:
        print(f"    [WARN] 신선도 조회 실패 ({keyword}): {e}")
        return {"newest_hours": None, "count_24h": 0, "count_48h": 0}

    now = datetime.now().astimezone()
    dates = []
    for it in items:
        try:
            dates.append(parsedate_to_datetime(it.get("pubDate", "")))
        except Exception:
            continue
    if not dates:
        return {"newest_hours": None, "count_24h": 0, "count_48h": 0}

    newest = max(dates)
    newest_hours = (now - newest).total_seconds() / 3600
    c24 = sum(1 for d in dates if (now - d).total_seconds() <= 86400)
    c48 = sum(1 for d in dates if (now - d).total_seconds() <= 172800)
    return {
        "newest_hours": round(newest_hours, 1),
        "count_24h": c24,
        "count_48h": c48,
    }


def _nospace(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def ground_keywords(candidates):
    """AI 가 낸 검색어 후보를 검색광고 API 로 검증해 '사람들이 실제로 치는 검색어'를 대표 keyword 로 고른다.
    (2026-09-17) 예전엔 AI 의 keyword 를 그대로 조회했는데, 최근 14일 주제 391개 중 336개(86%)가 월 100 미만,
    295개가 검색 기록이 없을 때 찍히는 20이었다 — '고단백 다이어트 통풍'처럼 뉴스 단어를 이어 붙인 가짜 검색어라서.
    고르는 순서: 후보(search_terms·keyword) 중 월 100↑ 에서 검색량이 가장 큰 것(두 단어 이상은 1.5배) → 없으면 대상(entity) 단독 → 그래도 없으면 그대로 두고 표시."""
    hints = []
    for c in candidates:
        for t in [c.get("keyword"), c.get("entity"), *(c.get("search_terms") or [])]:
            if isinstance(t, str) and t.strip() and t.strip() not in hints:
                hints.append(t.strip())
    print(f"  검색광고 절대 검색량 조회: 후보 {len(hints)}개")
    volume_map = fetch_search_volume(hints)
    print(f"    → {len(volume_map)}개 키워드 검색량 확보(연관 검색어 포함)")

    grounded = 0
    for c in candidates:
        c["keyword_ai"] = c.get("keyword", "")
        own = [t.strip() for t in [*(c.get("search_terms") or []), c.get("keyword")] if isinstance(t, str) and t.strip()]
        scored = []
        for t in own:
            v = lookup_volume(volume_map, t)
            if v and v["total"] >= DEMAND_MIN:
                # 검색량이 큰 쪽을 고르되, 두 단어 이상(대상+의도)이면 1.5배 쳐준다 — 글 한 편의 주제로는 구체적인 쪽이 낫다.
                # (첫 시험 2026-09-17: '가장 긴 것' 규칙은 통풍 글감에 월 980 '통풍에 나쁜 음식' 대신 150 '요산 수치 낮추는 법'을 골랐다)
                scored.append((v["total"] * (1.5 if len(t.split()) >= 2 else 1.0), v["total"], t))
        ent = (c.get("entity") or "").strip()
        if scored:
            best = max(scored, key=lambda x: x[0])
            c["keyword"], c["grounded_by"] = best[2], "search_term"
        elif ent and (lookup_volume(volume_map, ent) or {}).get("total", 0) >= DEMAND_MIN:
            c["keyword"], c["grounded_by"] = ent, "entity"
        else:
            c["grounded_by"] = None   # 실제 검색 수요를 못 찾음 → 검색형이면 정렬에서 뒤로 간다
        if c["grounded_by"]:
            grounded += 1
        c["search_term_volumes"] = {t: (lookup_volume(volume_map, t) or {}).get("total") for t in own[:4]}
    print(f"    → 실제 검색어에 붙은 글감: {grounded}/{len(candidates)}")
    return volume_map


def run_serp_check(candidates):
    """실제 네이버 모바일 검색 화면 확인(미니PC 에서 돌 때만). video-auto 의 serp-check 를 그대로 부른다.
    검색형 글감의 대표 검색어만 본다 — 시의형은 막 나온 말이라 블로그가 아직 없는 게 오히려 기회여서 자리 점수를 안 쓴다."""
    if not SERP_CHECK_DIR or not os.path.isdir(SERP_CHECK_DIR):
        return {}
    import subprocess
    import tempfile
    kws = [c["keyword"] for c in candidates if c.get("track") != "시의형" and c.get("grounded_by")][:15]
    if not kws:
        return {}
    tmp = tempfile.mkdtemp(prefix="serp_")
    list_path, out_path = os.path.join(tmp, "list.json"), os.path.join(tmp, "out.json")
    with open(list_path, "w", encoding="utf-8") as f:
        json.dump(kws, f, ensure_ascii=False)
    print(f"  검색 화면 확인: {len(kws)}개")
    try:
        subprocess.run(f'npx.cmd tsx scripts/serp-check.mts --list="{list_path}" --out="{out_path}"' if os.name == "nt"
                       else ["npx", "tsx", "scripts/serp-check.mts", f"--list={list_path}", f"--out={out_path}"],
                       cwd=SERP_CHECK_DIR, shell=(os.name == "nt"), timeout=600, capture_output=True)
        with open(out_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"    [WARN] 검색 화면 확인 실패 — 자리 점수 없이 진행: {e}")
        return {}


def position_mult(serp):
    """keyword-deep-dive 와 같은 기준. 블로그 영역이 화면 위에서 몇 px 에 나오나 × 쇼핑 블록이 위를 덮나."""
    if not serp:
        return 1.0
    y = serp.get("first_blog_y")
    pos = 0.7 if not isinstance(y, int) else 1.5 if y < 1000 else 1.25 if y < 2500 else 1.0 if y < 5000 else 0.7
    return round(pos * (0.85 if serp.get("shop_above_blog") else 1.0), 2)


def mark_written(candidates, my_posts):
    """이미 쓴 글 판정을 코드로: 글 제목에 대상(entity)이 있으면 그 글의 작성일로 판단한다.
    쓴 지 15일 안이면 already_covered(읽는 쪽이 후보에서 빼는 표시), 그보다 오래됐으면 다시 쓸 수 있는 재작성 후보.
    대상이 어느 제목에도 없으면 AI 가 짚은 covered_posts 제목이 실제 목록에 있을 때만 그 글로 판단한다."""
    titles = [(p.get("title", ""), p.get("date", "")) for p in my_posts if p.get("title")]
    today = datetime.now()
    for c in candidates:
        ent = _nospace(c.get("entity") or "")
        hits = [(t, d) for t, d in titles if len(ent) >= 2 and ent in _nospace(t)]
        if not hits:
            claimed = {_nospace(x) for x in (c.get("covered_posts") or []) if isinstance(x, str)}
            hits = [(t, d) for t, d in titles if _nospace(t) in claimed]
        if not hits:
            c["already_covered"], c["previously_written"], c["days_since_written"], c["covered_posts"] = False, False, None, []
            continue
        hits.sort(key=lambda x: x[1], reverse=True)
        try:
            days = (today - datetime.strptime(hits[0][1][:10], "%Y-%m-%d")).days
        except ValueError:
            days = None
        c["previously_written"] = True
        c["days_since_written"] = days
        c["already_covered"] = days is None or days < REWRITE_AFTER_DAYS
        c["covered_posts"] = [t for t, _ in hits[:3]]


DEEP_DIVE_ROOTS_URL = "https://raw.githubusercontent.com/justpassthrough/keyword-deep-dive/main/data/root_keywords.json"
NEW_ENTITIES_PATH = os.path.join(DATA_DIR, "new_entities.json")


def load_deep_dive_roots():
    """keyword-deep-dive 가 이미 파고 있는 뿌리 이름(쉬는 것 포함). 실패하면 빈 집합."""
    try:
        r = requests.get(DEEP_DIVE_ROOTS_URL, timeout=15)
        r.raise_for_status()
        return {_nospace(x.get("keyword")) for x in r.json().get("roots", [])}
    except Exception as e:
        print(f"  [WARN] 딥다이브 뿌리 목록 로드 실패: {e}")
        return set()


def recent_suggested_entities(by_date, limit=60):
    """최근 스캔들이 제안했던 대상 이름(프롬프트에 '이미 제안함'으로 알려 주는 용도)."""
    seen = []
    for key in sorted((k for k in by_date if k.endswith("#entities")), reverse=True):
        for name in by_date[key]:
            if name and name not in seen:
                seen.append(name)
    return seen[:limit]


def mark_novelty(candidates, my_posts, roots, by_date, rank_today):
    """'새로움'을 코드로 판정한다 — 이 도구의 본업은 아예 새 영역을 찾는 것.
    새 영역 = 딥다이브 뿌리에도 없고, 내 글 제목에 한 번도 안 나왔고, 전에 제안한 적도 없는 대상.
    검색형 점수 배수: 새 영역 첫 제안 1.15 / 그 밖 1.0 / 최근 2주에 4일 넘게 제안했는데 아직 안 쓴 것 0.85(계속 밀리는 글감)."""
    titles = [_nospace(p.get("title", "")) for p in my_posts]
    days = [d for d in by_date if not d.endswith("#entities")]
    for c in candidates:
        ent = _nospace(c.get("entity") or "")
        # 대상뿐 아니라 대표 검색어에 뿌리 이름이 들어 있어도 기존 영역('위고비 가격'의 대상이 '노보노디스크'로 나와 새 영역이 된 적이 있음)
        kwn = _nospace(c.get("keyword"))
        in_roots = any(len(r) >= 2 and ((len(ent) >= 2 and r in ent) or r in kwn) for r in roots)
        in_posts = len(ent) >= 2 and any(ent in t for t in titles)
        suggested_days = sum(1 for d in days if len(ent) >= 2 and any(ent in b for b in by_date[d]))
        if in_roots or in_posts:
            c["novelty"] = "기존 영역"
        elif suggested_days == 0:
            c["novelty"] = "새 영역"
        else:
            c["novelty"] = "새 영역(다시 제안)"
        c["suggested_days_2w"] = suggested_days
        c["in_deep_dive_roots"] = in_roots
        c["shopping_rank"] = rank_today.get((c.get("entity") or "").replace(" ", "")) or rank_today.get(c.get("keyword", "").replace(" ", ""))
        if c["novelty"] == "새 영역":
            c["novelty_mult"] = 1.15
        elif suggested_days >= 4 and not c.get("previously_written"):
            c["novelty_mult"] = 0.85
        else:
            c["novelty_mult"] = 1.0


def update_new_entities(candidates, movers):
    """딥다이브로 넘길 '새 대상' 장부(data/new_entities.json). 딥다이브 주간 발굴(discover_roots.py 소스 D)이 읽어
    검증(데이터랩 검색량 + 복합 키워드 5종↑) 후 뿌리 후보로 올린다.
    예전엔 딥다이브가 이 스캐너의 주제 중 known_products 에 '이미 있는 이름'만 받아서, 새 이름은 새롭다는 이유로 버려졌다."""
    try:
        with open(NEW_ENTITIES_PATH, "r", encoding="utf-8") as f:
            book = json.load(f)
    except (ValueError, OSError):
        book = {}
    today = datetime.now().strftime("%Y-%m-%d")
    mover_by_kw = {m["keyword"]: m for m in movers}
    for c in candidates:
        ent = (c.get("entity") or "").strip()
        if not c.get("novelty", "").startswith("새 영역") or c.get("track") == "시의형" or not (2 <= len(ent) <= 14):
            continue
        e = book.setdefault(ent, {"first_seen": today, "seen_days": []})
        if today not in e["seen_days"]:
            e["seen_days"].append(today)
        mv = mover_by_kw.get(ent.replace(" ", "")) or {}
        e.update({"last_seen": today, "keyword": c.get("keyword"), "search_volume": c.get("search_volume"),
                  "source": c.get("source") or "news", "shopping_rank": c.get("shopping_rank"),
                  "shopping_move": mv.get("kind"), "pharma_value": c.get("pharma_value"),
                  "blog_position_y": (c.get("serp") or {}).get("first_blog_y")})
    # 60일 넘게 다시 안 보인 것은 정리
    cutoff = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    book = {k: v for k, v in book.items() if v.get("last_seen", today) >= cutoff}
    with open(NEW_ENTITIES_PATH, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=1)
    return book


def enrich_candidates(candidates):
    """AI 후보에 뉴스 건수 + 검색량 트렌드 + 전문가 갭 + 절대 검색량(검색광고) 추가,
    그리고 트랙별 점수(검색형=기회점수 / 시의형=시의점수)를 계산."""
    print("\n" + "=" * 50)
    print("3단계: 보강 데이터 수집")
    print("=" * 50)

    # ── (a) 검색광고 API로 절대 검색량 일괄 조회 (배치, 비용 저렴) ──
    #     keyword가 이제 짧은 검색어라 적중률이 높음. 시의형은 대부분 0건이지만
    #     그 자체로 '검색 수요 없음' 신호라 그대로 둠.
    volume_map = ground_keywords(candidates)
    serp_map = run_serp_check(candidates)

    for i, c in enumerate(candidates):
        kw = c.get("keyword", "")
        core_kw = _extract_core_keyword(kw)
        track = c.get("track", "검색형")
        print(f"  [{i+1}/{len(candidates)}] ({track}) {kw}")

        # 뉴스 건수 + 헤드라인
        news_count, news_headlines = get_news_count_and_headlines(kw, count=3)
        time.sleep(0.1)
        c["news_count"] = news_count
        c["news_headlines"] = news_headlines
        print(f"    뉴스: {news_count}건")

        # 검색량 트렌드 (핵심 키워드로 조회 — DataLab 적중률 향상)
        change_rate, weekly_avg = get_search_trend(core_kw)
        time.sleep(0.15)
        if weekly_avg == 0 and core_kw != kw:
            change_rate2, weekly_avg2 = get_search_trend(kw)
            if weekly_avg2 > weekly_avg:
                change_rate, weekly_avg = change_rate2, weekly_avg2
            time.sleep(0.1)

        if change_rate > 50:
            direction = "급상승"
        elif change_rate > 10:
            direction = "상승"
        elif change_rate > -10:
            direction = "유지"
        else:
            direction = "하락"

        c["search_trend"] = {
            "change_rate": change_rate,
            "direction": direction,
            "weekly_avg": weekly_avg,
        }
        print(f"    검색트렌드: {change_rate:+.1f}% ({direction})")

        # 전문가 갭
        gap = get_expert_gap(core_kw)
        time.sleep(0.15)
        c["expert_gap"] = gap
        print(f"    전문가갭: {gap['label']} (비율 {gap['gap_ratio']}:1)")

        # ── 절대 검색량 (검색광고) ──
        vol = lookup_volume(volume_map, kw)
        search_volume = vol["total"] if vol else None
        comp_idx = vol["comp_idx"] if vol else None
        c["search_volume"] = search_volume
        c["comp_idx"] = comp_idx
        if search_volume is not None:
            print(f"    월검색수: {search_volume:,} / 경쟁 {comp_idx}")

        # ── 약사가치 + 검색형 기회점수 (시의형 점수는 main에서 신규성 반영 후 계산) ──
        pharma_value = calc_pharma_value(c.get("pharma_value"), gap)
        c["pharma_value_calc"] = pharma_value

        serp = serp_map.get(kw.replace(" ", "").upper()) if track != "시의형" else None
        c["serp"] = serp
        c["position_mult"] = position_mult(serp)
        opp = calc_opportunity(search_volume, comp_idx, pharma_value, c["position_mult"] if serp else None)
        c["opportunity_score"] = opp
        c["opportunity_label"] = opportunity_label(search_volume, comp_idx)

        if track == "시의형":
            # 신선도(속보성) 신호 수집 — 기사 발행일 기반
            recency = get_news_recency(kw)
            time.sleep(0.1)
            c["news_recency"] = recency
            c["score"] = None  # main에서 신규성(이미작성/연속일) 반영해 확정
            nh = recency.get("newest_hours")
            print(f"    신선도: 최신기사 {nh}h 전, 24h내 {recency.get('count_24h')}건")
        else:
            c["news_recency"] = {}
            c["score"] = opp if opp is not None else pharma_value
            print(f"    기회점수: {c['score']} (약사가치 {pharma_value})")

    return candidates


def _get_trend_key(topic):
    """연속 등장을 셀 때 쓰는 키 = 대상(entity). 없으면 trend_key, 그것도 없으면 핵심 키워드."""
    for k in ("entity", "trend_key"):
        v = str(topic.get(k) or "").strip()
        if v:
            return v
    return _extract_core_keyword(topic.get("keyword", ""))


def load_scan_history(days=7):
    """날짜별로 그날 스캔에 나온 글감의 글자 뭉치(키워드·trend_key·entity)를 돌려준다.
    (2026-09-17) 예전엔 AI 가 지은 trend_key 가 '완전히 같을 때'만 같은 주제로 쳤는데, 391개 주제에 키가 334가지라
    같은 주제가 9번 나와도 매번 1일로 찍혔다(지속 보너스·신규성 감점이 한 번도 안 걸림). 지금은 대상 이름이 그날 글자 뭉치에 들어 있으면 등장으로 센다."""
    if not os.path.isdir(SCANS_DIR):
        return {}
    import glob as _glob
    cutoff = datetime.now() - timedelta(days=days)
    by_date = {}
    for fpath in sorted(_glob.glob(os.path.join(SCANS_DIR, "*.json"))):
        try:
            ts = datetime.strptime(os.path.basename(fpath).replace(".json", ""), "%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if ts < cutoff:
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        day = ts.strftime("%Y-%m-%d")
        blob = by_date.setdefault(day, [])
        names = by_date.setdefault(day + "#entities", [])
        for t in data.get("topics", []):
            blob.append(_nospace(" ".join(str(t.get(k) or "") for k in ("keyword", "keyword_ai", "trend_key", "entity"))))
            nm = str(t.get("entity") or t.get("trend_key") or "").strip()
            if nm and nm not in names:
                names.append(nm)
    return by_date


def consecutive_days_for(topic, by_date, days=7):
    """어제부터 거꾸로, 이 글감의 대상이 연속으로 나온 날 수(오늘 제외)."""
    key = _nospace(_get_trend_key(topic))
    if len(key) < 2:
        return 0
    today = datetime.now().date()
    count = 0
    for i in range(1, days + 1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        if any(key in b for b in by_date.get(d, [])):
            count += 1
        else:
            break
    return count


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 파이프라인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    print("╔══════════════════════════════════════════╗")
    print("║  건강 트렌드 스캐너 v2                    ║")
    print("╚══════════════════════════════════════════╝")
    print()

    now = datetime.now()
    scan_id = now.strftime("%Y-%m-%d_%H%M")
    print(f"스캔 시작: {scan_id}")
    print()

    # 1단계: 데이터 수집
    news_by_category = collect_news()
    my_posts = load_my_posts()

    total_news = sum(len(v) for v in news_by_category.values())
    if total_news == 0:
        print("\n[ERROR] 수집된 뉴스가 없습니다. 종료.")
        sys.exit(1)

    # 1.5단계: 쇼핑 인기검색어(새 진입·급상승) + 제안 이력
    print("\n" + "=" * 50)
    print("1.5단계: 쇼핑 인기검색어 · 제안 이력")
    print("=" * 50)
    movers, rank_today = ([], {})
    shopping_on = os.environ.get("TREND_SHOPPING") == "1" or (os.environ.get("TREND_SHOPPING") != "0" and os.name == "nt")
    if shopping_on:
        from shopping_rank import collect_movers   # 집 IP(미니PC)에서만. Actions 수동 실행에서는 건너뜀
        movers, rank_today = collect_movers()
    history_2w = load_scan_history(days=14)
    recent_names = recent_suggested_entities(history_2w)
    print(f"  최근 2주 제안 대상 {len(recent_names)}개")
    # 상위 150위 안인데 딥다이브 뿌리에도 내 글 제목에도 없는 검색어 = 나한테 새 영역
    dd_roots = load_deep_dive_roots()
    my_titles = [_nospace(p.get("title", "")) for p in my_posts]
    uncovered = [(k, r) for k, r in sorted(rank_today.items(), key=lambda x: x[1])
                 if r <= 150 and len(k) >= 2
                 and not any(len(root) >= 2 and root in _nospace(k) for root in dd_roots)
                 and not any(_nospace(k) in t for t in my_titles)][:50]
    print(f"  쇼핑 상위 150 중 아직 안 다룬 검색어 {len(uncovered)}개")

    # 2단계: AI 분석
    result = run_ai_analysis(news_by_category, my_posts, movers, recent_names, uncovered)
    if isinstance(result, tuple):
        candidates, meta = result
    else:
        candidates, meta = result, {}

    if not candidates:
        print("\n[ERROR] AI 분석 결과가 없습니다. 종료.")
        sys.exit(1)

    # 3단계: 보강 데이터
    candidates = enrich_candidates(candidates)

    # 연속 등장일수 추가 (trend_key 기준)
    by_date = load_scan_history(days=7)
    for c in candidates:
        if not c.get("trend_key"):
            c["trend_key"] = _get_trend_key(c)
        c["consecutive_days"] = consecutive_days_for(c, by_date) + 1  # 오늘 포함

    # 이미 쓴 글 판정(코드) — 15일 규칙
    mark_written(candidates, my_posts)
    # 새로움 판정 + 딥다이브로 넘길 새 대상 장부
    mark_novelty(candidates, my_posts, dd_roots, history_2w, rank_today)
    book = update_new_entities(candidates, movers)
    print(f"  새 영역 글감 {sum(1 for c in candidates if c.get('novelty') == '새 영역')}개 · 새 대상 장부 {len(book)}개")

    # 트랙 정규화 (AI가 안 넣었으면 검색형으로 간주) + 시의형 점수 확정
    #   (시의형은 신규성=이미작성/연속일수를 반영해야 하므로 consecutive_days 계산 후 여기서 산출)
    for c in candidates:
        if c.get("track") not in ("검색형", "시의형"):
            c["track"] = "검색형"
        c["is_new_topic"] = not c.get("already_covered", False)
        cd = c.get("consecutive_days", 1)
        if c["track"] == "시의형":
            ts = calc_timeliness(
                c.get("pharma_value_calc", 3),
                c.get("news_recency", {}),
                c.get("search_trend", {}).get("change_rate", 0),
                c.get("already_covered", False),
                cd,
                c.get("news_count", 0),
            )
            c["timeliness_score"] = ts
            c["score"] = ts
        else:
            # 검색형: 기회점수에 '지속 보너스' (며칠째 꾸준히 = 진짜 인기, 사용자 관찰)
            base = c.get("opportunity_score")
            if base is None:
                base = c.get("pharma_value_calc", 3)
            if cd >= 5:
                pmult = 1.15
            elif cd >= 3:
                pmult = 1.07
            else:
                pmult = 1.0
            c["persistence_mult"] = pmult
            c["score"] = round(base * pmult * c.get("novelty_mult", 1.0), 1)

    # 정렬: 트랙별로 나눠 각자의 score(검색형=기회점수 / 시의형=시의점수) 내림차순
    #   검색형은 '실수요(월검색 DEMAND_MIN 이상) 있는 글감'을 1차 키로 먼저 올림 →
    #   검색량 없거나 아주 적은(월 20짜리) 키워드가 약사가치만으로 상단 차지하는 것 방지.
    search_topics = sorted(
        [c for c in candidates if c["track"] == "검색형"],
        key=lambda x: (has_demand(x), x.get("score") or 0),
        reverse=True,
    )
    news_topics = sorted(
        [c for c in candidates if c["track"] == "시의형"],
        key=lambda x: (x.get("score") or 0),
        reverse=True,
    )

    # rank는 트랙 내 순위로 부여
    for i, c in enumerate(search_topics):
        c["rank"] = i + 1
    for i, c in enumerate(news_topics):
        c["rank"] = i + 1

    topics = search_topics + news_topics

    # ── 오늘의 1픽 ──
    #   검색형/시의형은 점수 공식이 달라 통합 순위를 못 매김 → 트랙별로 대표 1개씩 뽑아
    #   "오늘 뭐 쓸까"를 한눈에 보여주는 추천 카드. 대시보드 최상단에 표시.
    def _pick(topic, reason):
        return {
            "keyword": topic.get("keyword"),
            "track": topic.get("track"),
            "reason": reason,
            "why_now": topic.get("why_now"),
            "pharmacist_angle": topic.get("pharmacist_angle"),
            "title_idea": topic.get("title_idea"),
            "score": topic.get("score"),
            "search_volume": topic.get("search_volume"),
            "comp_idx": topic.get("comp_idx"),
            "opportunity_label": topic.get("opportunity_label"),
        }

    today_pick = []
    # 검색형 대표 = 실수요 있는 것 중 1위(없으면 그냥 1위)
    search_best = next((c for c in search_topics if has_demand(c)),
                       search_topics[0] if search_topics else None)
    if search_best:
        today_pick.append(_pick(search_best, "검색형 최고 기회 (꾸준히 검색되는 글감)"))
    # 시의형 대표 = 1위(가장 신선한 이슈)
    if news_topics:
        today_pick.append(_pick(news_topics[0], "시의형 최신 이슈 (지금 막 뜨는 주제)"))

    # 통계
    new_topics = [c for c in candidates if not c.get("already_covered", False)]
    existing_topics = [c for c in candidates if c.get("already_covered", False)]
    golden = [c for c in candidates
              if c.get("opportunity_label") and "황금" in c["opportunity_label"]]
    stats = {
        "total_news_collected": total_news,
        "my_posts_count": len(my_posts),
        "ai_candidates": len(candidates),
        "new_topics": len(new_topics),
        "existing_topics_new_issue": len(existing_topics),
        "search_topics": len(search_topics),
        "news_topics": len(news_topics),
        "golden_topics": len(golden),
    }

    # 결과 JSON 구성
    output = {
        "scan_id": scan_id,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "today_pick": today_pick,
        "topics": topics,
        "stats": stats,
        "meta": meta,
        "shopping_movers": movers,
    }

    # 저장
    scan_path = os.path.join(SCANS_DIR, f"{scan_id}.json")
    latest_path = os.path.join(DATA_DIR, "latest.json")

    with open(scan_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    print("완료!")
    print("=" * 50)
    print(f"  스캔 저장: {scan_path}")
    print(f"  최신 저장: {latest_path}")
    print(f"  검색형: {len(search_topics)}개 / 시의형: {len(news_topics)}개")
    print(f"  새 글감: {len(new_topics)}개 / 기존 주제 새 이슈: {len(existing_topics)}개")
    print(f"  💎황금 키워드: {len(golden)}개")
    if today_pick:
        print("  ⭐ 오늘의 1픽:")
        for p in today_pick:
            print(f"     [{p['track']}] {p['keyword']} — {p['reason']}")
    print(f"  AI: {meta.get('model')} · 비용 ${meta.get('cost_usd', 0) or 0:.4f}")


if __name__ == "__main__":
    main()
