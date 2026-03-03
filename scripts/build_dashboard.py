"""
건강·약 트렌드 스캐너 — HTML 대시보드 생성
data/latest.json을 읽어서 모바일 최적화 HTML을 만듭니다.
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs")
os.makedirs(DOCS_DIR, exist_ok=True)


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


def build_html(data):
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

        # 경쟁도 쿼리 표시
        c_query = t.get("c_query", t["keyword"])
        c_display = f'"{c_query}" {t["blog_count"]}건' if c_query != t["keyword"] else f'{t["blog_count"]}건'

        yt_note = ""
        if t["yt_videos"]:
            v = t["yt_videos"][0]
            yt_note = f'<div class="yt-note">🎬 YT: {v["title"][:30]}… ({format_views(v["views"])}회)</div>'

        topic_cards += f"""
        <div class="card">
          <div class="card-header">
            <span class="rank">#{i+1}</span>
            <span class="keyword">{t["keyword"]}</span>
            <span class="score">{t["score"]}</span>
            {verdict_badge(t["verdict"])}
          </div>
          <div class="card-body">
            {news_html}
            <div class="metrics">
              <span class="metric">급등 {change_sign}{t["change_rate"]}%</span>
              {intent_badge(t["intent_type"])}
              <span class="metric">블로그 {c_display} ({t["c_level"]})</span>
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
  .pharma-tags {{ margin-top: 6px; }}
  .tag.pharma {{
    font-size: 11px;
    background: #1c2541;
    color: #58a6ff;
    padding: 2px 6px;
    border-radius: 4px;
    margin-right: 4px;
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
  <div class="date">{date} · {updated} 갱신</div>
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
  건강·약 트렌드 스캐너 · GitHub Actions 자동 갱신<br>
  점수 = H(주제온도) × I(검색의도) × P(약사근거) × C(경쟁도) × Y(유튜브)
</div>

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

    html = build_html(data)

    output_path = os.path.join(DOCS_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"대시보드 생성 완료: {output_path}")


if __name__ == "__main__":
    main()
