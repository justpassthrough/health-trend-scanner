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
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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
# 건강/의약 맥락 확인용 단어 (키워드 필터링에 사용)
HEALTH_CONTEXT_WORDS = {
    "건강", "의약", "약국", "약사", "병원", "치료", "진료", "처방", "복용",
    "영양", "비타민", "식품", "성분", "부작용", "효과", "증상", "효능",
    "질환", "감염", "백신", "면역", "진단", "수술", "환자", "임상", "허가",
    "식약처", "다이어트", "비만", "체중", "혈압", "혈당", "콜레스테롤",
    "유산균", "프로바이오틱스", "오메가", "콜라겐", "글루타치온",
    "영양제", "건기식", "의약품", "처방전", "약물", "투약", "제형",
    "코로나", "독감", "예방접종", "항생제", "항바이러스", "진통제",
    "당뇨", "고혈압", "암", "종양", "간", "신장", "폐렴", "알레르기",
}

GLOBAL_DRUGS = ["Ozempic", "Wegovy", "Mounjaro", "GLP-1", "Tirzepatide",
                "Semaglutide", "ozempic", "wegovy", "mounjaro",
                "위고비", "오젬픽", "마운자로", "삭센다"]

# 일반명사 블랙리스트 — 단독으로 글감 가치 없는 단어
BLACKLIST = {
    "논란", "환자", "열풍", "전문가", "효과", "위험",
    "주의", "경고", "연구", "발표", "결과", "사용", "복용",
    "치료", "증상", "원인", "방법", "예방", "관리",
    "식품", "제품", "성분", "골드", "남보라",
    "셀트리온", "애경산업",
    # 건강 맥락이지만 단독 글감 가치 없음
    "건강", "영양", "허가", "변경", "임신", "진단",
    "유발", "섭취", "권장", "개선", "함유", "표시",
    "구조", "손상", "재생", "기간", "가능", "필요",
    "확인", "검사", "투여", "조절", "기능", "작용",
    "발견", "정지", "상담", "특별", "선택", "즉시",
    "최초", "가장", "현재", "지속", "완전", "가능성",
    "수술", "특별점검", "특별", "점검",
    "금지", "재배포", "연결", "법적", "주의보",
    "없이", "즉각", "전용", "최신",
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 0단계: 히스토리 기반 신규성 판단
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_recent_history(days=7):
    """최근 N일 히스토리에서 키워드 등장 횟수 집계.

    반환: (keyword → appearance_count dict, total_scan_count)
    """
    history_dir = os.path.join(DATA_DIR, "history")
    if not os.path.isdir(history_dir):
        return {}, 0

    import glob as _glob
    files = sorted(_glob.glob(os.path.join(history_dir, "*.json")))
    cutoff = datetime.now() - timedelta(days=days)

    counts = Counter()
    total_scans = 0

    for fpath in files:
        fname = os.path.basename(fpath).replace(".json", "")
        try:
            ts = datetime.strptime(fname, "%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if ts < cutoff:
            continue
        total_scans += 1
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for t in data.get("topics", []):
                counts[t["keyword"]] += 1
        except Exception:
            continue

    return dict(counts), total_scans


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1단계: 네이버 뉴스에서 급등 키워드 자동 추출
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 한국어 조사/어미 패턴 (긴 것부터 매칭해야 "에서는"이 "는"보다 먼저 걸림)
_JOSA_SUFFIXES = [
    # 5음절+
    "이라는", "이라고", "에서는", "에서의", "으로는", "으로의", "에서도",
    # 3~4음절
    "에서", "으로", "하여", "하는", "하고", "에게", "한테", "까지",
    "부터", "처럼", "같이", "보다", "에는", "에도", "라는", "라고",
    "이라", "만의", "과의", "와의", "로의", "로는", "이나", "이며",
    "이고", "이든", "이면", "에의",
    # 2음절 조사
    "은", "는", "을", "를", "의", "에", "과", "와",
    "도", "만", "께", "며", "면",
    # 1음절 조사 — "로", "가", "이"는 고유명사 손상 위험이 높아 제외
    # (예: 마운자"로", 남보"라" → 체언이 아니라 이름 일부)
]

# "로"로 끝나는 건강 고유명사 보호 (조사 "로"를 떼면 안 되는 단어)
_PROTECTED_ENDINGS_RO = {
    "마운자로", "오젬픽", "삭센다", "위고비", "플라자로",
}

# 동사 어미 패턴 (복합어 끝에서 제거)
_VERB_ENDINGS = re.compile(
    r"(하|할|한|된|된다|하는|하고|하여|했던|하며|이다|된다|인지|인가|일까|라면|라서|해야|해서|해도|되어|되는|되면|됩니다|해요|돼요|없이|있어)$"
)

# 1음절 단독 불허 일반명사
_SINGLE_CHAR_BLOCK = {
    "수", "것", "때", "중", "등", "내", "더", "및", "각", "간",
    "약", "말", "위", "후", "전", "용", "형", "량", "제", "법",
}

# 불용어 (extract_keywords_from_news + get_autocomplete_keywords 공용)
_STOPWORDS = {
    "기자", "뉴스", "보도", "관련", "대한", "통해", "위해", "이상",
    "이하", "최근", "현재", "오늘", "내일", "올해", "지난", "다음",
    "경우", "가능", "정도", "사진", "제공", "연합", "한겨레", "조선",
    "중앙", "동아", "매일", "한국", "서울", "국내", "세계", "글로벌",
    "시장", "업계", "기업", "회사", "사업", "발표", "조사", "연구",
    "결과", "분석", "전문", "관계", "이번", "표방", "주장", "설명",
    "확인", "특히", "이후", "대해", "가운데", "통한", "따른", "나온",
    "개월", "원료", "혼합", "주원료",
    # 연예/엔터/게임/스포츠/정치
    "배우", "감독", "영화", "드라마", "출연", "방송", "예능", "아이돌",
    "콘서트", "앨범", "데뷔", "컴백", "팬미팅",
    "게임", "하자드", "레퀴엠", "플레이", "업데이트", "시즌",
    "축구", "야구", "배드민턴", "올림픽", "경기", "우승", "선수",
    "대통령", "국회", "정부", "총선", "대선", "후보", "탄핵",
    "주가", "코스피", "코스닥", "투자", "상장", "펀드",
    "후원", "공식", "운영", "지정", "최대", "진행", "출시",
    # 연예인/인물명
    "홍현희", "제이쓴", "박봄", "산다라박", "제시", "화사", "선미",
    "송지효", "전현무", "김종국", "유재석", "이광수",
}


def _strip_josa(word):
    """한국어 어절에서 조사/어미를 제거하여 체언(명사)만 반환.

    예: "세포가" → "세포", "원료로" → "원료", "식물성" → "식물성"
    결과가 1글자이면 원래 단어 반환 (과도한 제거 방지).
    고유명사 보호: "마운자로" 등은 조사 제거하지 않음.
    """
    # 고유명사 보호
    if word in _PROTECTED_ENDINGS_RO:
        return word

    # 구두점/괄호 등 먼저 제거
    word = word.strip(".,;:!?…·()[]{}\"'`~")

    for suffix in _JOSA_SUFFIXES:
        if word.endswith(suffix) and len(word) > len(suffix):
            stem = word[:-len(suffix)]
            if len(stem) >= 2:
                return stem

    # "로"로 끝나는 단어: 4글자 이상이고 보호 목록에 없으면 조사로 간주
    # "마운자로"(4글자)도 보호해야 하므로 보호 목록 체크 필수
    if word.endswith("로") and len(word) >= 4 and word not in _PROTECTED_ENDINGS_RO:
        stem = word[:-1]
        if len(stem) >= 2:
            return stem

    # "가", "이"로 끝나는 3글자+ 단어 (보수적 적용)
    if len(word) >= 3:
        if word.endswith("가") and word not in _PROTECTED_ENDINGS_RO:
            stem = word[:-1]
            if len(stem) >= 2:
                return stem
        if word.endswith("이") and word not in _PROTECTED_ENDINGS_RO:
            stem = word[:-1]
            if len(stem) >= 2:
                return stem

    return word


def _is_health_title(title):
    """뉴스 제목이 건강/의약 맥락인지 판별"""
    return any(hw in title for hw in HEALTH_CONTEXT_WORDS)


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
    """건강/의약 뉴스 제목에서 키워드 자동 추출.

    핵심 변경: 건강 기사 필터 → 키워드 추출 (순서 역전)
    """
    print("=" * 50)
    print("1단계: 네이버 뉴스에서 키워드 추출")
    print("=" * 50)

    seed_queries = [
        "건강기능식품", "영양제", "비타민", "유산균",
        "다이어트약", "비만치료제", "GLP-1",
        "처방약", "의약품", "식약처",
        "영양제 부작용", "건강식품 논란",
        "약국", "약사", "의약품 허가",
    ]

    # ── 수집 + 건강 기사 선필터 ──
    all_titles = []       # 건강 맥락 기사만
    total_fetched = 0
    for q in seed_queries:
        items = fetch_naver_news(q, display=100)
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            total_fetched += 1
            # 건강/의약 맥락이 있는 기사만 통과
            if _is_health_title(title):
                all_titles.append(title)
        time.sleep(0.1)

    print(f"  수집 뉴스: {total_fetched}건 → 건강 맥락 통과: {len(all_titles)}건")

    # ── 제목에서 명사 추출 (조사 제거) ──
    word_counter = Counter()

    for title in all_titles:
        # 한글 어절 추출
        raw_words = re.findall(r"[가-힣]{2,}", title)
        for raw in raw_words:
            w = _strip_josa(raw)
            # 1글자 일반명사 차단
            if len(w) < 2:
                continue
            if len(w) == 1 and w in _SINGLE_CHAR_BLOCK:
                continue
            if w in _STOPWORDS or w in BLACKLIST:
                continue
            word_counter[w] += 1

    # 빈도 3회 이상 (여러 기사에서 언급 = 이슈)
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
# 2단계 (신규): N, T, W, R 점수 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def calc_novelty(keyword, history_counts, total_scans):
    """N — 신규성 점수 (0~40). 과거 등장 횟수가 적을수록 높음."""
    appearances = history_counts.get(keyword, 0)
    if appearances == 0:
        return 40
    elif appearances == 1:
        return 30
    elif appearances <= 3:
        return 15
    elif total_scans > 0 and appearances <= total_scans * 0.5:
        return 5
    else:
        return 0


def calc_trend_momentum(change_rate):
    """T — 트렌드 모멘텀 (0~30). DataLab 변화율 기반."""
    if change_rate <= 0:
        return 0
    elif change_rate <= 5:
        return 5
    elif change_rate <= 15:
        return 10
    elif change_rate <= 30:
        return 15
    elif change_rate <= 50:
        return 20
    elif change_rate <= 100:
        return 25
    else:
        return 30


def calc_wave(keyword, news_count, pharma_news):
    """W — 뉴스 파동 (0~30). 뉴스 등장 횟수 + 약업계 뉴스 매칭."""
    # 기본 뉴스 빈도 점수
    if news_count >= 20:
        w = 20
    elif news_count >= 10:
        w = 15
    elif news_count >= 5:
        w = 10
    elif news_count >= 3:
        w = 5
    else:
        w = 0

    # 약업계 뉴스에서 키워드가 제목에 포함되면 +10
    for item in pharma_news:
        if keyword in item.get("title", ""):
            w += 10
            break

    return min(w, 30)


def calc_relevance(keyword, related_text):
    """R — 적합도 배수 (0.5~1.5). 기존 I, P, G를 통합한 배수."""
    # Intent 조정 (±0.15)
    a = sum(1 for w in DOUBT_KEYWORDS if w in related_text)
    b = sum(1 for w in SHOPPING_KEYWORDS if w in related_text)
    if a + b == 0:
        intent_adjust = 0
    else:
        intent_adjust = 0.15 * (a - b) / (a + b)

    # Pharma 조정 (0~0.15)
    pharma_n = sum(1 for w in PHARMA_KEYWORDS if w in related_text)
    pharma_adjust = 0.15 * min(pharma_n, 3) / 3

    # Gap 조정 (-0.3~+0.2)
    g_score, g_total, g_expert, g_ratio, g_label = calc_g_score(keyword)
    if g_label == "전문가 갭 큼":
        gap_adjust = 0.2
    elif g_label == "전문가 부족":
        gap_adjust = 0.1
    elif g_label == "보통":
        gap_adjust = 0.0
    elif g_label == "수요 없음":
        gap_adjust = -0.2
    else:  # 전문가 포화
        gap_adjust = -0.3

    r = 1.0 + intent_adjust + pharma_adjust + gap_adjust
    r = max(0.5, min(1.5, r))

    intent_type = "의심/경고형" if a > b else ("구매/추천형" if b > a else "중립")
    pharma_matched = [w for w in PHARMA_KEYWORDS if w in related_text]

    return round(r, 2), intent_type, pharma_matched, g_total, g_expert, g_label


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3단계: I, P — 동반 검색어 분석 (기존 함수 유지)
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

def _is_relevant_yt_video(title, keyword=""):
    """유튜브 영상 제목이 건강/의약 관련인지 검증.

    필터 기준 (순서대로):
    1. 한글 포함 — 외국어 전용 영상 제거
    2. 오탐 패턴 차단 — 펫/예능/게임/비유적 사용 제거
    3. 건강 맥락 확인 — 제목에 건강 단어가 있어야 통과
    """
    # 1) 한글이 하나도 없으면 탈락 (러시아어, 영어 전용 영상 등)
    if not re.search(r"[가-힣]", title):
        return False

    # 2) 오탐 패턴 차단 — 건강 단어가 있더라도 이 패턴에 걸리면 탈락
    noise_patterns = [
        # 비유적 사용 (예: "비타민 우리 왕자님", "웃음 비타민")
        r"왕자", r"공주", r"웃음\s*비타민", r"비타민\s*같은",
        # 펫/반려동물
        r"강아지", r"고양이", r"반려[견묘]", r"펫", r"사료", r"애견",
        # 예능/먹방/언박싱
        r"먹방", r"ASMR", r"asmr", r"언박싱", r"하울", r"챌린지",
        # 게임/스포츠/아이돌
        r"게임", r"리그오브레전드", r"피파", r"아이돌",
        # 댄스/대결 (예: "비타민vs피어스 댄스 대결")
        r"댄스\s*대결", r"vs.*댄스", r"댄스.*vs",
    ]
    for pat in noise_patterns:
        if re.search(pat, title, re.IGNORECASE):
            return False

    # 3) 건강/의약 맥락 확인
    # 제목에서 한글 추출
    title_text = " ".join(re.findall(r"[가-힣]+", title))

    # 제목 자체에 건강 단어가 있으면 통과
    has_health = any(hw in title_text for hw in HEALTH_CONTEXT_WORDS)

    # 검색 키워드가 건강 단어이면 맥락 체크 생략 (이미 건강 검색임)
    if not has_health and keyword:
        has_health = any(hw in keyword for hw in HEALTH_CONTEXT_WORDS)

    return has_health


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
        "maxResults": 10,
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
            title = v.get("snippet", {}).get("title", "")

            # 관련성 필터: 건강/의약 무관 영상 제거
            if not _is_relevant_yt_video(title, keyword=keyword):
                continue

            views = int(v.get("statistics", {}).get("viewCount", 0))
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

def _clean_compound(combo):
    """복합 키워드 정제: 각 어절에서 조사/어미 제거, 노이즈 어절 삭제.

    예: "세포 재생을" → "세포 재생", "손상 유발할" → "손상 유발"
        "유발 가능성." → "유발 가능성"
    """
    parts = []
    for w in combo.split():
        # 구두점/괄호/해시태그 제거
        w = w.strip(".,;:!?…·()[]{}\"'`~#@")
        if not w:
            continue
        # 한글 어절만 처리
        if not re.search(r"[가-힣]", w):
            parts.append(w)
            continue
        cleaned = _strip_josa(w)
        # 동사 어미 제거 ("유발할" → "유발")
        cleaned = _VERB_ENDINGS.sub("", cleaned)
        if len(cleaned) >= 2 and cleaned not in _STOPWORDS and cleaned not in BLACKLIST:
            parts.append(cleaned)
    result = " ".join(parts) if parts else ""
    # 최종 결과가 1어절이고 2글자 미만이면 빈 문자열
    if result and len(result.replace(" ", "")) < 2:
        return ""
    return result


def _is_valid_compound(combo, parent_keyword):
    """복합 키워드 품질 검증.

    기준:
    - 한글 명사가 2개 이상 포함 (parent 포함해서 OK)
    - 조사/어미로 끝나지 않음
    - 불용어/블로그 용어 미포함
    - 구두점 미포함
    """
    if not combo or combo == parent_keyword:
        return False

    # 구두점/특수문자가 남아있으면 탈락
    if re.search(r"[.,;:!?…#@()[\]{}]", combo):
        return False

    # 한글 명사(2글자+) 추출
    korean_parts = re.findall(r"[가-힣]{2,}", combo)
    if len(korean_parts) < 2:
        return False

    # 마지막 어절이 조사/어미로 끝나면 탈락
    last_word = combo.split()[-1]
    for suffix in _JOSA_SUFFIXES:
        if last_word.endswith(suffix) and len(last_word) > len(suffix):
            return False
    if _VERB_ENDINGS.search(last_word):
        return False

    # 블로그/불용어 포함 시 탈락
    blog_noise = {"블로그", "포스팅", "리뷰", "안녕", "여러분", "공유",
                  "합니다", "있습니다", "입니다", "됩니다", "같습니다",
                  "이렇게", "그래서", "하지만", "그리고", "때문에",
                  "해방촌", "맛집", "레스토랑", "카페"}
    for part in combo.split():
        if part in blog_noise or part in _STOPWORDS or part in BLACKLIST:
            return False
        # "~입니다", "~합니다" 등 종결어미 포함 어절 탈락
        if part.endswith("입니다") or part.endswith("합니다") or part.endswith("됩니다"):
            return False

    # SEO 스팸 탈락: 7글자 이상 한글 단일 어절 (예: "부산마운자로가격")
    for part in combo.split():
        korean_only = re.sub(r"[^가-힣]", "", part)
        if len(korean_only) >= 7:
            return False

    return True


def get_autocomplete_keywords(keyword, max_results=5):
    """네이버 블로그 검색 동반 키워드에서 연관 키워드 추출.

    자동완성 API(ac.search.naver.com)는 해외 IP 차단으로 GitHub Actions에서 사용 불가.
    대안: 블로그 검색 결과 제목/설명에서 "키워드 + X" 패턴의 복합어를 추출.
    """
    url = "https://openapi.naver.com/v1/search/blog.json"
    params = {"query": keyword, "display": 50, "sort": "date"}
    try:
        r = requests.get(url, headers=NAVER_HEADERS, params=params, timeout=10)
        r.raise_for_status()
        items = r.json().get("items", [])

        compound_counter = Counter()
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            desc = re.sub(r"<[^>]+>", "", item.get("description", ""))
            text = f"{title} {desc}"
            words = text.split()
            for j, w in enumerate(words):
                if keyword in w or w in keyword:
                    # 앞뒤 단어와 조합 → 조사 정제
                    if j > 0:
                        raw_combo = f"{words[j-1]} {w}"
                        combo = _clean_compound(raw_combo)
                        if combo and combo != keyword and len(combo) > len(keyword) + 1:
                            compound_counter[combo] += 1
                    if j < len(words) - 1:
                        raw_combo = f"{w} {words[j+1]}"
                        combo = _clean_compound(raw_combo)
                        if combo and combo != keyword and len(combo) > len(keyword) + 1:
                            compound_counter[combo] += 1

        results = []
        seen_normalized = set()
        for combo, count in compound_counter.most_common(30):
            if count < 2:
                continue
            if not _is_valid_compound(combo, keyword):
                continue
            # 정규화 중복 체크 (띄어쓰기 무시)
            norm = combo.replace(" ", "")
            if norm in seen_normalized:
                continue
            seen_normalized.add(norm)
            results.append(combo)

        return results[:max_results]
    except Exception as e:
        print(f"  [ERROR] 연관키워드 추출 실패 ({keyword}): {e}")
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
                title = v["snippet"]["title"]
                # 관련성 필터: 건강/의약 무관 영상 제거
                if not _is_relevant_yt_video(title, keyword=q):
                    continue
                if views >= 30000:
                    hot_videos.append({
                        "title": title,
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
# 7.5단계: 중복 키워드 병합
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def merge_duplicate_topics(topics):
    """점수순 정렬된 topics에서 중복 키워드를 병합.

    규칙 (순서대로):
    1. 포함 관계: "백신" ⊂ "코로나 백신" → 점수 높은 쪽만 남김
    2. 띄어쓰기 제거 후 동일: "비만치료제" == "비만 치료제"
    3. 뉴스 헤드라인 2개가 동일: 같은 이슈

    점수 높은 쪽이 대표, 낮은 쪽은 aliases에 기록.
    """
    if not topics:
        return topics

    print("\n" + "=" * 50)
    print("7.5단계: 중복 키워드 병합")
    print("=" * 50)

    merged = []  # 최종 결과
    absorbed = set()  # 이미 흡수된 인덱스

    for i, t in enumerate(topics):
        if i in absorbed:
            continue

        aliases = []
        t_kw = t["keyword"]
        t_norm = t_kw.replace(" ", "")
        t_news = set(nh.get("title", "") for nh in t.get("news_headlines", [])[:2])

        for j in range(i + 1, len(topics)):
            if j in absorbed:
                continue

            o = topics[j]
            o_kw = o["keyword"]
            o_norm = o_kw.replace(" ", "")
            is_dup = False

            # 규칙 1: 포함 관계 (짧은 쪽이 3글자 이상이어야 함, 오탐 방지)
            shorter = min(len(t_kw), len(o_kw))
            if shorter >= 3 and (t_kw in o_kw or o_kw in t_kw):
                is_dup = True

            # 규칙 2: 띄어쓰기 제거 후 동일
            if not is_dup and t_norm == o_norm:
                is_dup = True

            # 규칙 3: 뉴스 헤드라인 2개가 동일
            if not is_dup and t_news and len(t_news) >= 2:
                o_news = set(nh.get("title", "") for nh in o.get("news_headlines", [])[:2])
                if o_news and t_news == o_news:
                    is_dup = True

            if is_dup:
                aliases.append(o_kw)
                absorbed.add(j)
                print(f"  병합: '{o_kw}' → '{t_kw}' (대표)")

        if aliases:
            t["aliases"] = aliases
        merged.append(t)

    removed = len(topics) - len(merged)
    if removed > 0:
        print(f"  결과: {len(topics)}개 → {len(merged)}개 ({removed}개 중복 제거)")
    else:
        print(f"  중복 없음")

    return merged


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8단계: AI 해석 (블로그 기획 포인트)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generate_interpretations(topics):
    """상위 15개 토픽에 대해 Claude Haiku로 블로그 기획 포인트를 생성.

    각 키워드별로:
    - 뒤집을 상식: 대중이 흔히 믿는 오해 (→ 블로그 후킹 소재)
    - 약사 앵글: 병원 약사/DDS 연구자 관점의 차별화 포인트

    API 키가 없거나 실패 시 빈 문자열로 graceful fallback.
    """
    if not ANTHROPIC_API_KEY:
        print("\n  [SKIP] AI 해석 — ANTHROPIC_API_KEY 없음")
        return

    try:
        import anthropic
    except ImportError:
        print("\n  [SKIP] AI 해석 — anthropic 패키지 미설치")
        return

    top = topics[:15]
    if not top:
        return

    print("\n" + "=" * 50)
    print("8단계: AI 해석 (블로그 기획 포인트)")
    print("=" * 50)

    # 키워드별 맥락 데이터 구성
    keyword_lines = []
    for t in top:
        headlines = " / ".join(nh["title"][:40] for nh in t.get("news_headlines", []))
        keyword_lines.append(
            f"- {t['keyword']} | 점수:{t['score']} (N:{t.get('n',0)} T:{t.get('t',0)} W:{t.get('w',0)} R:{t.get('r',1.0)}) | "
            f"{t['intent_type']} | 변화율:{t['change_rate']:+.0f}% | 전문가갭:{t.get('g_label','보통')} | "
            f"뉴스: {headlines or '없음'}"
        )

    keywords_block = "\n".join(keyword_lines)

    prompt = f"""당신은 병원 약사이자 약물전달(DDS) 연구자가 운영하는 네이버 건강 블로그의 콘텐츠 기획 어시스턴트입니다.

이 블로그의 핵심 공식: "다들 ~라고 알잖아요. 근데 그거, 좀 달라요."
(대중의 흔한 오해를 뒤집고, 약사/연구자만의 전문 관점으로 차별화)

아래 트렌딩 키워드들을 보고, 각각에 대해 블로그 기획에 바로 쓸 수 있는 포인트를 뽑아주세요.

[트렌딩 키워드]
{keywords_block}

[출력 규칙]
- 반드시 JSON 배열로만 응답
- 각 항목: {{"keyword": "키워드", "summary": "뒤집을 상식 + 약사 앵글 2줄"}}
- summary 형식 (줄바꿈 \\n 사용):
  1줄: 뒤집기 — 대중이 믿는 오해와 실제가 다른 포인트 (예: "공복에 먹어야 좋다고 알려졌지만, 균주에 따라 다름")
  2줄: 앵글 — 약사/DDS 연구자로서 다룰 수 있는 차별화 소재 (예: "코팅 기술별 위산 생존율 비교 → 성분표 읽는 법으로 풀면 좋음")
- 건강/의약과 직접 관련 없는 키워드는 summary를 빈 문자열로
- 한국어로 작성"""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()

        # JSON 배열 추출 (```json ... ``` 감싸기 대응)
        if "```" in raw:
            match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
            if match:
                raw = match.group(1)

        interpretations = json.loads(raw)

        # topic dict에 ai_summary 필드 추가
        interp_map = {item["keyword"]: item.get("summary", "") for item in interpretations}
        matched = 0
        for t in topics:
            summary = interp_map.get(t["keyword"], "")
            t["ai_summary"] = summary
            if summary:
                matched += 1

        print(f"  AI 해석 완료: {matched}/{len(top)}개 키워드에 해석 추가")

    except json.JSONDecodeError as e:
        print(f"  [ERROR] AI 응답 JSON 파싱 실패: {e}")
        for t in topics:
            t["ai_summary"] = ""
    except Exception as e:
        print(f"  [ERROR] AI 해석 실패: {e}")
        for t in topics:
            t["ai_summary"] = ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인: 전체 파이프라인
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def judge(score):
    if score >= 70:
        return "now"
    elif score >= 45:
        return "hot"
    elif score >= 25:
        return "warm"
    else:
        return "pass"


def score_keyword(kw, news_count, skip_youtube, parent=None,
                  history_counts=None, total_scans=0, pharma_news=None):
    """단일 키워드의 N, T, W, R 점수를 산출하고 결과 dict 반환."""
    if history_counts is None:
        history_counts = {}
    if pharma_news is None:
        pharma_news = []

    prefix = f"    [{'+' if parent else ''}] " if parent else "    "

    # N — 신규성
    n = calc_novelty(kw, history_counts, total_scans)
    print(f"{prefix}N={n} (신규성)")

    # T — 트렌드 모멘텀
    change_rate, current_vol = get_search_trend(kw)
    t = calc_trend_momentum(change_rate)
    print(f"{prefix}T={t} (변화율 {change_rate:+.0f}%)")
    time.sleep(0.15)

    # W — 뉴스 파동
    w = calc_wave(kw, news_count, pharma_news)
    print(f"{prefix}W={w} (뉴스 {news_count}건)")

    # N+T+W 합산이 0이면 스킵
    ntw = n + t + w
    if ntw == 0:
        print(f"{prefix}→ N+T+W=0이므로 스킵")
        return None

    # 관련 뉴스 헤드라인
    news_headlines = get_keyword_news(kw, count=2)
    for nh in news_headlines:
        print(f"{prefix}📰 {nh['title'][:50]}")
    time.sleep(0.1)

    # R — 적합도 (I, P, G 통합)
    related = get_related_keywords(kw)
    time.sleep(0.15)
    r, intent_type, pharma_matched, g_total, g_expert, g_label = calc_relevance(kw, related)
    print(f"{prefix}R={r} ({intent_type}, 갭:{g_label})")
    time.sleep(0.15)

    # 최종 점수: (N + T + W) × R
    total = round(ntw * r, 1)
    verdict = judge(total)
    print(f"{prefix}★ ({n}+{t}+{w})×{r} = {total} → {verdict}")

    result = {
        "keyword": kw,
        "score": total,
        "verdict": verdict,
        "n": n, "t": t, "w": w, "r": r,
        "change_rate": round(change_rate, 1),
        "intent_type": intent_type,
        "pharma_keywords": pharma_matched,
        "g_total": g_total, "g_expert": g_expert,
        "g_label": g_label,
        "news_count": news_count,
        "news_headlines": news_headlines,
    }
    if parent:
        result["parent"] = parent
    return result


def main():
    skip_youtube = "--skip-youtube" in sys.argv

    print(f"\n{'#' * 50}")
    print(f"  건강·약 트렌드 스캐너 v2 — {datetime.now().strftime('%Y.%m.%d %H:%M')}")
    print(f"  점수 공식: (N신규성 + T모멘텀 + W뉴스파동) × R적합도")
    if skip_youtube:
        print(f"  [모드] 실시간 갱신 (유튜브 스킵)")
    print(f"{'#' * 50}\n")

    # 0. 히스토리 로드 (신규성 판단용)
    history_counts, total_scans = load_recent_history(days=7)
    print(f"  [히스토리] 최근 7일 스캔 {total_scans}회, 키워드 {len(history_counts)}종 추적 중")

    # 1. 키워드 자동 추출
    keyword_data = extract_keywords_from_news()  # [(keyword, news_count), ...]

    if not keyword_data:
        print("\n[!] 추출된 키워드가 없습니다. 시드 키워드로 대체합니다.")
        keyword_data = [(kw, 5) for kw in
                        ["마운자로", "위고비", "오젬픽", "비타민D", "유산균",
                         "글루타치온", "콜라겐", "오메가3", "NMN", "코엔자임Q10"]]

    # BLACKLIST 필터: 단독 일반명사 제거
    before_bl = len(keyword_data)
    keyword_data = [(kw, cnt) for kw, cnt in keyword_data if kw not in BLACKLIST]
    bl_removed = before_bl - len(keyword_data)
    if bl_removed > 0:
        print(f"  [블랙리스트] {bl_removed}개 일반명사 제거")

    # 1.5. 약업계 뉴스 먼저 수집 (W 산출에 필요)
    pharma_news = collect_pharma_news()

    # 1.6. 이전 스캔의 유효 키워드 유지 (점수 25+ = "패스"가 아닌 것만)
    prev_path = os.path.join(DATA_DIR, "latest.json")
    prev_topic_scores = {}  # keyword → previous score
    prev_data = None
    if os.path.exists(prev_path):
        try:
            with open(prev_path, "r", encoding="utf-8") as f:
                prev_data = json.load(f)
            for t in prev_data.get("topics", []):
                if t.get("score", 0) >= 25:
                    prev_topic_scores[t["keyword"]] = t["score"]
            print(f"\n  [이전 스캔] 유효 키워드 {len(prev_topic_scores)}개 로드")
        except Exception as e:
            print(f"\n  [이전 스캔] 로드 실패: {e}")

    # 새 키워드: 최대 20개 (뉴스 빈도순, 이미 정렬됨)
    new_keywords = keyword_data[:20]
    new_kw_set = set(kw for kw, _ in new_keywords)
    print(f"  [새 키워드] {len(new_keywords)}개 (전체 추출: {len(keyword_data)}개)")

    # 이월 키워드: 이전 스캔에서 점수 25+ 였지만 이번에 새로 추출되지 않은 것
    def is_health_keyword(kw):
        return any(hw in kw for hw in HEALTH_CONTEXT_WORDS)

    carried_candidates = [kw for kw in sorted(
        prev_topic_scores.keys(),
        key=lambda k: prev_topic_scores[k],
        reverse=True
    ) if kw not in new_kw_set]

    prev_ai = set()
    if prev_data:
        for t in prev_data.get("topics", []):
            if t.get("ai_summary", ""):
                prev_ai.add(t["keyword"])

    carried = []
    for kw in carried_candidates:
        if kw in BLACKLIST:
            continue
        if is_health_keyword(kw) or kw in prev_ai:
            carried.append((kw, 3))
        else:
            print(f"  [이월 제외] {kw} (건강 무관, 이전 점수: {prev_topic_scores[kw]:.1f})")

    remaining_slots = 30 - len(new_keywords)
    carried = carried[:remaining_slots]

    if carried:
        print(f"  [이월] {len(carried)}개 키워드 유지 (이전 점수순)")
        for kw, _ in carried:
            print(f"    ↩ {kw} (이전 점수: {prev_topic_scores[kw]:.1f})")

    keyword_data = new_keywords + carried
    print(f"  [최종] 분석 대상: {len(keyword_data)}개 (새 {len(new_keywords)} + 이월 {len(carried)})")

    # 2~5. 각 키워드별 점수 산출
    print("\n" + "=" * 50)
    print("2~5단계: 키워드별 점수 산출 (N+T+W)×R")
    print("=" * 50)

    topics = []
    scored_keywords = set()

    for i, (kw, news_count) in enumerate(keyword_data):
        print(f"\n  [{i+1}/{len(keyword_data)}] {kw} (뉴스 {news_count}건)")
        scored_keywords.add(kw)

        result = score_keyword(kw, news_count, skip_youtube,
                               history_counts=history_counts,
                               total_scans=total_scans,
                               pharma_news=pharma_news)
        if result:
            topics.append(result)

    # 5.5단계: 연관 키워드 확장 (상위 10개 키워드)
    print("\n" + "=" * 50)
    print("5.5단계: 연관 키워드 확장")
    print("=" * 50)

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
            if rel_kw in scored_keywords or rel_kw in BLACKLIST:
                if rel_kw in scored_keywords:
                    print(f"    [{rel_kw}] 이미 분석됨, 스킵")
                continue
            scored_keywords.add(rel_kw)

            print(f"\n    + 연관: {rel_kw} (← {parent_kw})")
            result = score_keyword(rel_kw, 0, skip_youtube, parent=parent_kw,
                                   history_counts=history_counts,
                                   total_scans=total_scans,
                                   pharma_news=pharma_news)
            if result:
                related_topics.append(result)

    print(f"\n  연관 키워드에서 {len(related_topics)}개 추가 발견")

    # 기존 + 연관 키워드 합쳐서 점수순 정렬
    topics.extend(related_topics)
    topics.sort(key=lambda x: x["score"], reverse=True)

    # 7.5. 중복 키워드 병합
    topics = merge_duplicate_topics(topics)

    # 8. AI 해석 (블로그 기획 포인트)
    generate_interpretations(topics)

    # 7. 유튜브 급등
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
