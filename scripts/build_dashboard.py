"""
건강·약 트렌드 스캐너 — HTML 대시보드 생성
data/latest.json을 읽어서 모바일 최적화 HTML을 만듭니다.
"""

import json
import os
import glob
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
os.makedirs(DOCS_DIR, exist_ok=True)


def load_history(hours=48):
    """최근 N시간 이내 히스토리 파일들을 로드하여 키워드별 점수 이력 반환"""
    history_dir = os.path.join(DATA_DIR, "history")
    if not os.path.isdir(history_dir):
        return {}

    files = sorted(glob.glob(os.path.join(history_dir, "*.json")))
    cutoff = datetime.now() - timedelta(hours=hours)

    # 키워드 → [(timestamp, score), ...] 시간순
    keyword_history = {}
    for fpath in files:
        fname = os.path.basename(fpath).replace(".json", "")
        try:
            ts = datetime.strptime(fname, "%Y-%m-%d_%H%M")
        except ValueError:
            continue
        if ts < cutoff:
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for t in data.get("topics", []):
                kw = t["keyword"]
                if kw not in keyword_history:
                    keyword_history[kw] = []
                keyword_history[kw].append((fname, t["score"]))
        except Exception:
            continue

    return keyword_history


def calc_trend(keyword, current_score, keyword_history):
    """키워드의 추이 라벨과 점수 이력 반환"""
    history = keyword_history.get(keyword, [])

    if not history:
        return "new", "🆕 신규", []

    # 현재 점수 포함하여 최근 순서 점수 리스트 (오래된 → 최신)
    scores = [s for _, s in history]
    # 마지막이 현재 실행 결과일 수 있으므로, 중복 방지
    if scores and scores[-1] == current_score:
        all_scores = scores
    else:
        all_scores = scores + [current_score]

    if len(all_scores) < 2:
        return "new", "🆕 신규", all_scores

    prev = all_scores[-2]
    curr = all_scores[-1]
    diff = curr - prev

    if len(all_scores) >= 3:
        prev2 = all_scores[-3]
        if curr > prev > prev2:
            return "up2", "↑↑ 상승 중", all_scores[-4:]
        elif curr < prev < prev2:
            return "down2", "↓↓ 하락 중", all_scores[-4:]

    if diff > 3:
        return "up", "↑ 상승", all_scores[-4:]
    elif diff < -3:
        return "down", "↓ 하락", all_scores[-4:]
    else:
        return "flat", "→ 유지", all_scores[-4:]


def trend_badge(trend_type, trend_label):
    css_class = {
        "up2": "trend-up",
        "up": "trend-up",
        "down2": "trend-down",
        "down": "trend-down",
        "flat": "trend-flat",
        "new": "trend-new",
    }.get(trend_type, "trend-flat")
    return f'<span class="{css_class}">{trend_label}</span>'


def verdict_badge(verdict):
    if verdict == "now":
        return '<span class="badge now">지금 써라</span>'
    elif verdict == "good":
        return '<span class="badge good">쓸 만하다</span>'
    elif verdict == "maybe":
        return '<span class="badge maybe">앵글 바꾸면</span>'
    else:
        return '<span class="badge skip">패스</span>'


def intent_badge(intent_type):
    if "의심" in intent_type or "경고" in intent_type:
        return '<span class="intent doubt">의심/경고형</span>'
    elif "구매" in intent_type or "추천" in intent_type:
        return '<span class="intent shop">구매/추천형</span>'
    else:
        return '<span class="intent neutral">중립</span>'


def format_views(n):
    if n >= 10000:
        return f"{n/10000:.1f}만"
    elif n >= 1000:
        return f"{n/1000:.1f}천"
    return str(n)


def build_html(data, keyword_history=None):
    if keyword_history is None:
        keyword_history = {}
    date = data.get("date", "")
    updated = data.get("updated_at", "")
    topics = data.get("topics", [])
    pharma_news = data.get("pharma_news", [])
    youtube_trends = data.get("youtube_trends", [])

    # 글감 카드 HTML
    topic_cards = ""
    for i, t in enumerate(topics[:15]):
        change_sign = "+" if t["change_rate"] > 0 else ""
        pharma_tags = ""
        if t["pharma_keywords"]:
            pharma_tags = " ".join(
                f'<span class="tag pharma">{k}</span>' for k in t["pharma_keywords"][:3]
            )

        # 관련 뉴스 헤드라인 (왜 급등했는지)
        news_html = ""
        for nh in t.get("news_headlines", [])[:2]:
            title = nh["title"][:55]
            link = nh.get("link", "#")
            news_html += f'<div class="news-context"><a href="{link}" target="_blank">📰 {title}</a></div>'

        # 전문가 갭 표시
        g_total = t.get("g_total", 0)
        g_expert = t.get("g_expert", 0)
        g_label = t.get("g_label", "보통")
        if g_label == "전문가 갭 큼":
            g_color_cls = "gap-high"
        elif g_label == "전문가 부족":
            g_color_cls = "gap-mid"
        elif g_label == "전문가 포화" or g_label == "수요 없음":
            g_color_cls = "gap-low"
        else:
            g_color_cls = "gap-normal"

        # 연관 키워드 parent 표시
        parent_html = ""
        parent_kw = t.get("parent", "")
        if parent_kw:
            parent_html = f'<div class="parent-note">↑ "{parent_kw}" 연관검색어에서 발견</div>'

        yt_note = ""
        if t["yt_videos"]:
            v = t["yt_videos"][0]
            yt_note = f'<div class="yt-note">🎬 YT: {v["title"][:30]}… ({format_views(v["views"])}회)</div>'

        # 추이 계산
        t_type, t_label, t_scores = calc_trend(t["keyword"], t["score"], keyword_history)
        trend_html = ""
        if t_scores:
            scores_str = " → ".join(str(s) for s in t_scores)
            trend_html = f'<div class="trend-line">{trend_badge(t_type, t_label)} {scores_str}</div>'

        topic_cards += f"""
        <div class="card">
          <div class="card-header">
            <span class="rank">#{i+1}</span>
            <span class="keyword">{t["keyword"]}</span>
            <span class="score">{t["score"]}</span>
            {verdict_badge(t["verdict"])}
          </div>
          <div class="card-body">
            {parent_html}
            {trend_html}
            {news_html}
            <div class="metrics">
              <span class="metric">급등 {change_sign}{t["change_rate"]}%</span>
              {intent_badge(t["intent_type"])}
              <span class="metric {g_color_cls}">후기 {g_total}건 vs 전문가 {g_expert}건 → {g_label}</span>
            </div>
            <div class="pharma-tags">{pharma_tags}</div>
            {yt_note}
          </div>
        </div>"""

    # 유튜브 급등 HTML
    yt_cards = ""
    for v in youtube_trends[:5]:
        yt_cards += f"""
        <div class="yt-card">
          <div class="yt-title">🎬 {v["title"][:50]}</div>
          <div class="yt-meta">{v["channel"]} · {format_views(v["views"])}회</div>
        </div>"""

    if not yt_cards:
        yt_cards = '<div class="empty">최근 48시간 내 급등 영상 없음</div>'

    # 약업계 뉴스 HTML
    news_items = ""
    for h in pharma_news[:10]:
        if h["signal"] == "strong":
            icon = "🔴"
        elif h["signal"] == "normal":
            icon = "🟡"
        else:
            icon = "🌐"
        news_items += f"""
        <div class="news-item">
          <span class="news-icon">{icon}</span>
          <a href="{h["link"]}" target="_blank" class="news-title">{h["title"][:60]}</a>
          <span class="news-tag">{h["trigger"]}</span>
        </div>"""

    if not news_items:
        news_items = '<div class="empty">오늘 약업계 주요 뉴스 없음</div>'

    # 데이터 시점
    naver_updated = data.get("naver_updated_at", updated)
    yt_updated = data.get("youtube_updated_at", updated)

    # 통계 요약
    now_count = sum(1 for t in topics if t["verdict"] == "now")
    good_count = sum(1 for t in topics if t["verdict"] == "good")

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>건강·약 트렌드 스캐너</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0d1117;
    color: #e6edf3;
    padding: 16px;
    max-width: 600px;
    margin: 0 auto;
    -webkit-font-smoothing: antialiased;
  }}
  .header {{
    text-align: center;
    padding: 20px 0 12px;
    border-bottom: 1px solid #21262d;
    margin-bottom: 16px;
  }}
  .header h1 {{
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 4px;
  }}
  .header .date {{ font-size: 13px; color: #8b949e; }}
  .summary {{
    display: flex;
    gap: 10px;
    justify-content: center;
    margin: 12px 0 20px;
  }}
  .summary-box {{
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 10px 18px;
    text-align: center;
  }}
  .summary-box .num {{ font-size: 22px; font-weight: 700; }}
  .summary-box .label {{ font-size: 11px; color: #8b949e; }}
  .section-title {{
    font-size: 15px;
    font-weight: 700;
    margin: 24px 0 12px;
    padding-left: 4px;
  }}
  .card {{
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 10px;
  }}
  .card-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }}
  .rank {{ color: #8b949e; font-size: 13px; font-weight: 600; }}
  .keyword {{ font-size: 15px; font-weight: 700; flex: 1; }}
  .score {{
    font-size: 18px;
    font-weight: 800;
    color: #58a6ff;
  }}
  .badge {{
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 12px;
    font-weight: 600;
  }}
  .badge.now {{ background: #1a7f37; color: #fff; }}
  .badge.good {{ background: #9e6a03; color: #fff; }}
  .badge.maybe {{ background: #333; color: #aaa; }}
  .badge.skip {{ background: #21262d; color: #666; }}
  .metrics {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    font-size: 12px;
  }}
  .metric {{
    background: #21262d;
    padding: 3px 8px;
    border-radius: 6px;
    color: #8b949e;
  }}
  .intent {{
    padding: 3px 8px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
  }}
  .intent.doubt {{ background: #1a3a1a; color: #3fb950; }}
  .intent.shop {{ background: #3a1a1a; color: #f85149; }}
  .intent.neutral {{ background: #21262d; color: #8b949e; }}
  .gap-high {{ background: #1a3a1a !important; color: #3fb950 !important; }}
  .gap-mid {{ background: #3a2a0a !important; color: #d29922 !important; }}
  .gap-low {{ background: #3a1a1a !important; color: #f85149 !important; }}
  .gap-normal {{ background: #21262d !important; color: #8b949e !important; }}
  .pharma-tags {{ margin-top: 6px; }}
  .tag.pharma {{
    font-size: 11px;
    background: #1c2541;
    color: #58a6ff;
    padding: 2px 6px;
    border-radius: 4px;
    margin-right: 4px;
  }}
  .parent-note {{
    font-size: 12px;
    color: #58a6ff;
    margin-bottom: 6px;
    padding: 3px 8px;
    background: #0d1117;
    border-radius: 6px;
    border-left: 3px solid #58a6ff;
  }}
  .trend-line {{
    font-size: 12px;
    color: #8b949e;
    margin-bottom: 6px;
    padding: 4px 8px;
    background: #0d1117;
    border-radius: 6px;
    border-left: 3px solid #21262d;
  }}
  .trend-up {{
    color: #3fb950;
    font-weight: 600;
    margin-right: 6px;
  }}
  .trend-down {{
    color: #f85149;
    font-weight: 600;
    margin-right: 6px;
  }}
  .trend-flat {{
    color: #8b949e;
    font-weight: 600;
    margin-right: 6px;
  }}
  .trend-new {{
    color: #58a6ff;
    font-weight: 600;
    margin-right: 6px;
  }}
  .news-context {{
    margin-bottom: 6px;
  }}
  .news-context a {{
    font-size: 12px;
    color: #c9d1d9;
    text-decoration: none;
    line-height: 1.5;
  }}
  .news-context a:hover {{ color: #58a6ff; }}
  .yt-note {{
    font-size: 11px;
    color: #8b949e;
    margin-top: 6px;
    padding: 4px 8px;
    background: #1a1a2e;
    border-radius: 6px;
  }}
  .yt-card {{
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 12px;
    margin-bottom: 8px;
  }}
  .yt-title {{ font-size: 13px; font-weight: 600; margin-bottom: 4px; }}
  .yt-meta {{ font-size: 11px; color: #8b949e; }}
  .news-item {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 0;
    border-bottom: 1px solid #21262d;
    font-size: 13px;
  }}
  .news-icon {{ font-size: 14px; }}
  .news-title {{
    flex: 1;
    color: #e6edf3;
    text-decoration: none;
  }}
  .news-title:hover {{ color: #58a6ff; }}
  .news-tag {{
    font-size: 10px;
    background: #21262d;
    padding: 2px 6px;
    border-radius: 4px;
    color: #8b949e;
    white-space: nowrap;
  }}
  .empty {{
    text-align: center;
    color: #484f58;
    padding: 20px;
    font-size: 13px;
  }}
  .refresh-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 16px;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .refresh-info {{
    font-size: 11px;
    color: #8b949e;
    line-height: 1.6;
  }}
  .refresh-btn {{
    background: #238636;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }}
  .refresh-btn:hover {{ background: #2ea043; }}
  .refresh-btn:disabled {{
    background: #21262d;
    color: #484f58;
    cursor: not-allowed;
  }}
  .token-setup {{
    font-size: 11px;
    color: #484f58;
    text-align: center;
    margin-top: 6px;
  }}
  .token-setup a {{ color: #58a6ff; text-decoration: none; }}
  .token-input {{
    width: 100%;
    background: #0d1117;
    border: 1px solid #21262d;
    border-radius: 6px;
    color: #e6edf3;
    padding: 6px 10px;
    font-size: 12px;
    margin-top: 6px;
  }}
  .token-save-btn {{
    background: #238636;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }}
  .token-save-btn:hover {{ background: #2ea043; }}
  .status-msg {{
    font-size: 11px;
    color: #8b949e;
    margin-top: 6px;
    text-align: center;
  }}
  .footer {{
    text-align: center;
    font-size: 11px;
    color: #484f58;
    margin-top: 30px;
    padding: 20px 0;
    border-top: 1px solid #21262d;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>건강·약 트렌드 스캐너</h1>
  <div class="date">{date}</div>
</div>

<div class="refresh-bar">
  <div class="refresh-info">
    네이버: {naver_updated}<br>
    유튜브: {yt_updated}
  </div>
  <button class="refresh-btn" id="refreshBtn" onclick="triggerRefresh()">실시간 갱신</button>
</div>
<div class="token-setup" id="tokenSetup" style="display:none;">
  <span>GitHub PAT 입력 (최초 1회):</span>
  <div style="display:flex;gap:6px;margin-top:6px;">
    <input type="password" class="token-input" id="tokenInput" placeholder="ghp_xxxx 또는 github_pat_xxxx" style="margin-top:0;flex:1;">
    <button class="token-save-btn" onclick="saveToken(document.getElementById('tokenInput').value)">저장</button>
  </div>
</div>

<div class="summary">
  <div class="summary-box">
    <div class="num" style="color:#3fb950">{now_count}</div>
    <div class="label">지금 써라</div>
  </div>
  <div class="summary-box">
    <div class="num" style="color:#d29922">{good_count}</div>
    <div class="label">쓸 만하다</div>
  </div>
  <div class="summary-box">
    <div class="num">{len(topics)}</div>
    <div class="label">분석 키워드</div>
  </div>
</div>

<div class="section-title">🔥 오늘의 글감 (점수순)</div>
{topic_cards if topic_cards else '<div class="empty">오늘 분석된 글감 없음</div>'}

<div class="section-title">🎬 유튜브 급등 (네이버에 아직 안 옴)</div>
{yt_cards}

<div class="section-title">📰 약업계 헤드라인</div>
{news_items}

<div class="footer">
  건강·약 트렌드 스캐너 · 매일 07:30 / 13:00 / 19:00 / 00:00 자동 갱신<br>
  점수 = H(주제온도) × I(검색의도) × P(약사근거) × G(전문가갭) × Y(유튜브)
</div>

<script>
const REPO = 'justpassthrough/health-trend-scanner';
const WORKFLOW = 'daily_scan.yml';

function getToken() {{
  return localStorage.getItem('ht_github_token') || '';
}}

function saveToken(val) {{
  if (val && val.trim()) {{
    localStorage.setItem('ht_github_token', val.trim());
    document.getElementById('tokenSetup').style.display = 'none';
    document.getElementById('tokenInput').value = '';
    triggerRefresh();
  }}
}}

function showStatus(msg) {{
  let el = document.getElementById('statusMsg');
  if (!el) {{
    el = document.createElement('div');
    el.id = 'statusMsg';
    el.className = 'status-msg';
    document.querySelector('.refresh-bar').after(el);
  }}
  el.textContent = msg;
}}

async function triggerRefresh() {{
  const btn = document.getElementById('refreshBtn');
  const token = getToken();
  if (!token) {{
    document.getElementById('tokenSetup').style.display = 'block';
    showStatus('GitHub PAT를 먼저 입력하세요.');
    return;
  }}
  btn.disabled = true;
  btn.textContent = '갱신 중...';
  showStatus('GitHub Actions 트리거 요청 중...');

  // fine-grained PAT(github_pat_) → Bearer, classic PAT(ghp_) → token
  const authPrefix = token.startsWith('github_pat_') ? 'Bearer' : 'token';

  try {{
    const resp = await fetch(
      `https://api.github.com/repos/${{REPO}}/actions/workflows/${{WORKFLOW}}/dispatches`,
      {{
        method: 'POST',
        headers: {{
          'Authorization': `${{authPrefix}} ${{token}}`,
          'Accept': 'application/vnd.github.v3+json',
        }},
        body: JSON.stringify({{ ref: 'main', inputs: {{ skip_youtube: 'true' }} }}),
      }}
    );
    if (resp.status === 204) {{
      btn.textContent = '실행됨!';
      showStatus('Actions 실행 시작됨. 약 3~4분 후 자동 새로고침합니다...');
      // 데이터 수집 ~3분 + Pages 배포 ~1분 = 약 4분
      let sec = 240;
      const timer = setInterval(() => {{
        sec--;
        if (sec <= 0) {{
          clearInterval(timer);
          location.reload();
        }} else {{
          showStatus(`새로고침까지 ${{sec}}초... (수집+배포 진행 중)`);
        }}
      }}, 1000);
    }} else if (resp.status === 401 || resp.status === 403) {{
      localStorage.removeItem('ht_github_token');
      document.getElementById('tokenSetup').style.display = 'block';
      btn.textContent = '토큰 오류';
      btn.disabled = false;
      const errText = await resp.text().catch(() => '');
      if (resp.status === 403) {{
        showStatus('권한 부족. PAT에 Actions 읽기/쓰기 권한이 필요합니다.');
      }} else {{
        showStatus('토큰이 유효하지 않습니다. 다시 입력해주세요.');
      }}
    }} else {{
      btn.textContent = '실패 (' + resp.status + ')';
      showStatus('요청 실패. 상태 코드: ' + resp.status);
      setTimeout(() => {{ btn.textContent = '실시간 갱신'; btn.disabled = false; }}, 3000);
    }}
  }} catch (e) {{
    btn.textContent = '네트워크 오류';
    showStatus('네트워크 오류: ' + e.message);
    setTimeout(() => {{ btn.textContent = '실시간 갱신'; btn.disabled = false; }}, 3000);
  }}
}}

// 토큰이 없으면 안내 표시
if (!getToken()) {{
  document.getElementById('tokenSetup').style.display = 'block';
}} else {{
  // 토큰이 있으면 저장됨 표시
  showStatus('');
}}
</script>

</body>
</html>"""

    return html


def main():
    json_path = os.path.join(DATA_DIR, "latest.json")
    if not os.path.exists(json_path):
        print("[ERROR] data/latest.json이 없습니다. collect.py를 먼저 실행하세요.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    keyword_history = load_history(hours=48)
    print(f"히스토리 로드: {len(keyword_history)}개 키워드 추적 중")

    html = build_html(data, keyword_history)

    output_path = os.path.join(DOCS_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"대시보드 생성 완료: {output_path}")


if __name__ == "__main__":
    main()
