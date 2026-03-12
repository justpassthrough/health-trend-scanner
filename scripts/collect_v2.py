"""
건강 트렌드 스캐너 v2 — AI 기반 글감 발굴 파이프라인
GitHub Actions에서 하루 2회 (08:00, 20:00 KST) 자동 실행
"""

import os
import sys
import json
import re
import time
from datetime import datetime, timedelta

import requests

# ── 인코딩 (Windows cp949 방지) ──
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

# ── API 키 ──
NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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

우선순위:
1. 내 블로그에 전혀 없는 영양제/성분 이름 → 최우선 (예: 아직 안 다룬 루테인, 크릴오일, 아연, 비타민D 등)
2. 소비자에게 직접 영향 주는 약업계 뉴스 (건보 적용, 품절, 리콜, 가격 변동) → 높음
3. 갑자기 검색량이 급등하는 성분이나 건강 이슈 → 높음
4. 이미 다룬 주제지만 새 이슈가 터진 경우 → 보통 (already_covered=true 표시)
5. "비만", "건강" 같은 포괄적 키워드는 제외 — 구체적인 성분명/제품명/정책명일수록 좋음

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
각 항목:
{{
  "keyword": "구체적 키워드 (예: '루테인', '탈모약 건보 적용', '크릴오일 vs 오메가3')",
  "category": "영양제·성분 | 약업계·정책 | 질환·치료 | 소비자건강",
  "why_now": "왜 지금 이 글을 써야 하는지 2~3문장. 뉴스 맥락과 블로그 확장 가치를 구체적으로 설명.",
  "pharmacist_angle": "약사/DDS 연구자로서 차별화할 수 있는 구체적 앵글 1~2문장",
  "title_idea": "블로그 글 제목 아이디어 1개 (클릭 유도형, 약사 전문성 드러나는)",
  "already_covered": false,
  "covered_posts": [],
  "source_headlines": ["근거가 된 뉴스 제목 1~2개 (위 뉴스에서 발췌)"]
}}

[중요]
- already_covered가 true인 경우, covered_posts에 관련된 기존 글 제목을 넣으세요
- 새 글감(already_covered=false)이 전체의 60% 이상이어야 합니다
- keyword는 블로그 제목에 쓸 수 있을 정도로 구체적이어야 합니다
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
            max_tokens=8000,
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
    """키워드 관련 뉴스 건수 + 상위 헤드라인 반환"""
    items = fetch_naver_news(keyword, display=100, sort="sim")
    headlines = []
    for item in items[:count]:
        title = re.sub(r"<[^>]+>", "", item.get("title", "")).strip()
        link = item.get("link", "")
        pub_date = item.get("pubDate", "")
        headlines.append({"title": title, "link": link, "date": pub_date})
    return len(items), headlines


def enrich_candidates(candidates):
    """AI 후보에 뉴스 건수 + 검색량 트렌드 + 전문가 갭 데이터 추가"""
    print("\n" + "=" * 50)
    print("3단계: 보강 데이터 수집")
    print("=" * 50)

    for i, c in enumerate(candidates):
        kw = c.get("keyword", "")
        core_kw = _extract_core_keyword(kw)
        print(f"  [{i+1}/{len(candidates)}] {kw}")
        if core_kw != kw:
            print(f"    핵심 키워드: {core_kw}")

        # 뉴스 건수 + 헤드라인
        news_count, news_headlines = get_news_count_and_headlines(core_kw, count=3)
        time.sleep(0.1)
        c["news_count"] = news_count
        c["news_headlines"] = news_headlines
        print(f"    뉴스: {news_count}건")

        # 검색량 트렌드 (핵심 키워드로 조회 — DataLab 적중률 향상)
        change_rate, weekly_avg = get_search_trend(core_kw)
        time.sleep(0.15)

        # 핵심 키워드로도 0이면 원본으로 재시도
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
        print(f"    검색: {change_rate:+.1f}% ({direction}, avg={weekly_avg})")

        # 전문가 갭
        gap = get_expert_gap(core_kw)
        time.sleep(0.15)
        c["expert_gap"] = gap
        print(f"    전문가갭: {gap['label']} (비율 {gap['gap_ratio']}:1)")

    return candidates


def load_scan_history(days=7):
    """최근 스캔에서 키워드 연속 등장일수 계산"""
    if not os.path.isdir(SCANS_DIR):
        return {}

    import glob as _glob
    files = sorted(_glob.glob(os.path.join(SCANS_DIR, "*.json")))
    cutoff = datetime.now() - timedelta(days=days)

    # 날짜별 키워드 집합
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
            keywords = {t["keyword"] for t in data.get("topics", [])}
            if date_str not in date_keywords:
                date_keywords[date_str] = set()
            date_keywords[date_str].update(keywords)
        except Exception:
            continue

    # 오늘부터 역순으로 연속일수 계산
    today = datetime.now().date()
    consecutive = {}
    dates_sorted = sorted(date_keywords.keys(), reverse=True)

    # 모든 키워드 수집
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
        return

    # 2단계: AI 분석
    result = run_ai_analysis(news_by_category, my_posts)
    if isinstance(result, tuple):
        candidates, meta = result
    else:
        candidates, meta = result, {}

    if not candidates:
        print("\n[ERROR] AI 분석 결과가 없습니다. 종료.")
        return

    # 3단계: 보강 데이터
    candidates = enrich_candidates(candidates)

    # 연속 등장일수 추가
    consecutive = load_scan_history(days=7)
    for c in candidates:
        prev = consecutive.get(c["keyword"], 0)
        c["consecutive_days"] = prev + 1  # 오늘 포함

    # 정렬: 새 글감(already_covered=false) 먼저, 그 안에서는 순서 유지
    new_topics = [c for c in candidates if not c.get("already_covered", False)]
    existing_topics = [c for c in candidates if c.get("already_covered", False)]

    topics = []
    for i, c in enumerate(new_topics + existing_topics):
        c["rank"] = i + 1
        c["is_new_topic"] = not c.get("already_covered", False)
        topics.append(c)

    # 통계
    stats = {
        "total_news_collected": total_news,
        "my_posts_count": len(my_posts),
        "ai_candidates": len(candidates),
        "new_topics": len(new_topics),
        "existing_topics_new_issue": len(existing_topics),
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
    print(f"  새 글감: {len(new_topics)}개")
    print(f"  기존 주제 새 이슈: {len(existing_topics)}개")
    print(f"  API 비용: ${meta.get('cost_usd', 0):.4f}")


if __name__ == "__main__":
    main()
