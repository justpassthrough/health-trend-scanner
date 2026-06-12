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


def calc_opportunity(search_volume, comp_idx, pharma_value):
    """검색형 기회점수 = 약사가치 × 수요배수(log10 검색량) × 경쟁여유배수.
    검색량 없으면 None(→ 약사가치로 폴백)."""
    if search_volume is None:
        return None
    # log10(검색량)/2: 100회=1.0, 2500회≈1.7, 1.1만회≈2.0, 23만회≈2.7
    demand_mult = math.log10(max(search_volume, 10)) / 2
    comp_mult = {"낮음": 1.2, "중간": 1.0, "높음": 0.8}.get(comp_idx, 1.0)
    return round(pharma_value * demand_mult * comp_mult, 1)


def opportunity_label(search_volume, comp_idx):
    """검색량·경쟁도 조합을 사람이 읽을 라벨로."""
    if search_volume is None:
        return None
    if search_volume < 100:
        return "수요 적음"
    if search_volume >= 1000 and comp_idx == "낮음":
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

def build_ai_prompt(news_by_category, my_posts):
    """AI 프롬프트 구성"""

    # 내 블로그 글 제목 목록
    post_titles = []
    for p in my_posts:
        title = p.get("title", "")
        if title:
            post_titles.append(title)
    posts_block = "\n".join(f"- {t}" for t in post_titles[:50])  # 최근 50개

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
검색형과 시의형을 모두 포함하세요 (검색형 최소 4개, 시의형 최소 3개 권장).
각 항목:
{{
  "keyword": "짧은 검색어 (예: '감마오리자놀', '바나바잎', '탈모약 건강보험', '위고비 품절')",
  "track": "검색형 | 시의형",
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
- already_covered가 true인 경우, covered_posts에 관련된 기존 글 제목을 넣으세요
- 새 글감(already_covered=false)이 전체의 60% 이상이어야 합니다
- "비만", "건강" 같은 너무 포괄적인 단어 단독 사용 금지 — 구체적인 성분명/제품명/정책명
- 한국어로 작성"""

    return prompt


def run_ai_analysis(news_by_category, my_posts):
    """Claude Haiku로 글감 후보 추출"""
    print("\n" + "=" * 50)
    print("2단계: AI 분석")
    print("=" * 50)

    if not ANTHROPIC_API_KEY:
        print("  [ERROR] ANTHROPIC_API_KEY 없음 — AI 분석 스킵")
        return []

    try:
        import anthropic
    except ImportError:
        print("  [ERROR] anthropic 패키지 미설치")
        return []

    prompt = build_ai_prompt(news_by_category, my_posts)

    # 토큰 수 추정 (대략 1토큰 = 3.5자 한국어)
    est_input_tokens = len(prompt) // 3
    print(f"  프롬프트 길이: {len(prompt)}자 (추정 ~{est_input_tokens} 토큰)")

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        # 비용 계산 (Haiku 4.5: $1/M input, $5/M output)
        cost = (input_tokens * 1 + output_tokens * 5) / 1_000_000
        print(f"  API 사용: 입력 {input_tokens}, 출력 {output_tokens} 토큰")
        print(f"  비용: ${cost:.4f}")
        print(f"  응답 길이: {len(raw)}자")
        print(f"  응답 첫 200자: {raw[:200]}")

        # JSON 파싱 — 여러 형식 대응
        json_str = raw

        # 1) ```json ... ``` 감싸기
        if "```" in json_str:
            match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", json_str)
            if match:
                json_str = match.group(1)

        # 2) 배열 부분만 추출 (앞뒤 텍스트 제거)
        if not json_str.startswith("["):
            match = re.search(r"\[[\s\S]*\]", json_str)
            if match:
                json_str = match.group(0)

        candidates = json.loads(json_str)
        print(f"  → AI 추천 글감: {len(candidates)}개")

        # 메타 정보 저장용
        meta = {
            "model": "claude-haiku-4-5-20251001",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": round(cost, 4),
        }

        return candidates, meta

    except json.JSONDecodeError as e:
        print(f"  [ERROR] AI 응답 JSON 파싱 실패: {e}")
        print(f"  Raw 응답 첫 500자: {raw[:500]}")
        return [], {"model": "claude-haiku-4-5-20251001", "error": str(e)}
    except Exception as e:
        print(f"  [ERROR] AI 분석 실패: {e}")
        return [], {"model": "claude-haiku-4-5-20251001", "error": str(e)}


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
    core = re.split(r"\s*[-+vs]\s*", core)[0].strip()
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


def enrich_candidates(candidates):
    """AI 후보에 뉴스 건수 + 검색량 트렌드 + 전문가 갭 + 절대 검색량(검색광고) 추가,
    그리고 트랙별 점수(검색형=기회점수 / 시의형=시의점수)를 계산."""
    print("\n" + "=" * 50)
    print("3단계: 보강 데이터 수집")
    print("=" * 50)

    # ── (a) 검색광고 API로 절대 검색량 일괄 조회 (배치, 비용 저렴) ──
    #     keyword가 이제 짧은 검색어라 적중률이 높음. 시의형은 대부분 0건이지만
    #     그 자체로 '검색 수요 없음' 신호라 그대로 둠.
    kw_list = [c.get("keyword", "") for c in candidates if c.get("keyword")]
    print(f"  검색광고 절대 검색량 조회: {len(kw_list)}개")
    volume_map = fetch_search_volume(kw_list)
    print(f"    → {len(volume_map)}개 키워드 검색량 확보")

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

        opp = calc_opportunity(search_volume, comp_idx, pharma_value)
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
    """토픽에서 trend_key 추출. 없으면 _extract_core_keyword로 fallback"""
    tk = topic.get("trend_key", "").strip()
    if tk:
        return tk
    return _extract_core_keyword(topic.get("keyword", ""))


def load_scan_history(days=7):
    """최근 스캔에서 trend_key 기준 연속 등장일수 계산"""
    if not os.path.isdir(SCANS_DIR):
        return {}

    import glob as _glob
    files = sorted(_glob.glob(os.path.join(SCANS_DIR, "*.json")))
    cutoff = datetime.now() - timedelta(days=days)

    # 날짜별 trend_key 집합
    date_keywords = {}
    for fpath in files:
        fname = os.path.basename(fpath).replace(".json", "")
        try:
            ts = datetime.strptime(fname, "%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if ts < cutoff:
            continue
        date_str = ts.strftime("%Y-%m-%d")
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            keys = {_get_trend_key(t) for t in data.get("topics", [])}
            if date_str not in date_keywords:
                date_keywords[date_str] = set()
            date_keywords[date_str].update(keys)
        except Exception:
            continue

    # 오늘부터 역순으로 연속일수 계산
    today = datetime.now().date()
    consecutive = {}

    # 모든 trend_key 수집
    all_kws = set()
    for kws in date_keywords.values():
        all_kws.update(kws)

    for kw in all_kws:
        count = 0
        for i in range(days):
            check_date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            if check_date in date_keywords and kw in date_keywords[check_date]:
                count += 1
            else:
                break
        consecutive[kw] = count

    return consecutive


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

    # 2단계: AI 분석
    result = run_ai_analysis(news_by_category, my_posts)
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
    consecutive = load_scan_history(days=7)
    for c in candidates:
        tk = _get_trend_key(c)
        # trend_key가 AI에서 안 나온 경우 fallback으로 생성해서 저장
        if not c.get("trend_key"):
            c["trend_key"] = tk
        prev = consecutive.get(tk, 0)
        c["consecutive_days"] = prev + 1  # 오늘 포함

    # 트랙 정규화 (AI가 안 넣었으면 검색형으로 간주) + 시의형 점수 확정
    #   (시의형은 신규성=이미작성/연속일수를 반영해야 하므로 consecutive_days 계산 후 여기서 산출)
    for c in candidates:
        if c.get("track") not in ("검색형", "시의형"):
            c["track"] = "검색형"
        c["is_new_topic"] = not c.get("already_covered", False)
        if c["track"] == "시의형":
            ts = calc_timeliness(
                c.get("pharma_value_calc", 3),
                c.get("news_recency", {}),
                c.get("search_trend", {}).get("change_rate", 0),
                c.get("already_covered", False),
                c.get("consecutive_days", 1),
                c.get("news_count", 0),
            )
            c["timeliness_score"] = ts
            c["score"] = ts

    # 정렬: 트랙별로 나눠 각자의 score(검색형=기회점수 / 시의형=시의점수) 내림차순
    search_topics = sorted(
        [c for c in candidates if c["track"] == "검색형"],
        key=lambda x: (x.get("score") or 0),
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
        "topics": topics,
        "stats": stats,
        "meta": meta,
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
    print(f"  API 비용: ${meta.get('cost_usd', 0):.4f}")


if __name__ == "__main__":
    main()
