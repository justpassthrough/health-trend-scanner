"""
건강 트렌드 스캐너 v2 — 대시보드 HTML 생성
data/latest.json + data/scans/*.json → docs/index.html
"""

import os
import sys
import json
import glob
from datetime import datetime

# ── 인코딩 ──
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SCANS_DIR = os.path.join(DATA_DIR, "scans")
DOCS_DIR = os.path.join(BASE_DIR, "docs")
os.makedirs(DOCS_DIR, exist_ok=True)


def load_scan_list():
    """스캔 파일 목록 (최근 14일)"""
    files = sorted(glob.glob(os.path.join(SCANS_DIR, "*.json")), reverse=True)
    scans = []
    for f in files[:28]:  # 최대 28개 (14일 × 2회)
        name = os.path.basename(f).replace(".json", "")
        scans.append(name)
    return scans


def load_scan_data(scan_id):
    """특정 스캔 데이터 로드"""
    path = os.path.join(SCANS_DIR, f"{scan_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_html(scan_list, all_scans_data):
    """대시보드 HTML 생성"""

    # 스캔 데이터를 JS에서 사용할 수 있도록 JSON으로 임베드
    scans_json = json.dumps(all_scans_data, ensure_ascii=False)
    scan_list_json = json.dumps(scan_list, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>건강 트렌드 스캐너 v2</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #0d1117;
  color: #e6edf3;
  min-height: 100vh;
  padding: 16px;
  padding-bottom: 80px;
}}

/* 헤더 */
.header {{
  text-align: center;
  padding: 20px 0 12px;
}}
.header h1 {{
  font-size: 22px;
  color: #58a6ff;
  margin-bottom: 4px;
}}
.header .subtitle {{
  font-size: 13px;
  color: #8b949e;
}}

/* 날짜 네비게이터 */
.nav {{
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  margin: 16px 0;
  flex-wrap: wrap;
}}
.nav button {{
  background: #21262d;
  color: #e6edf3;
  border: 1px solid #30363d;
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}}
.nav button:hover {{ background: #30363d; }}
.nav button:disabled {{ opacity: 0.4; cursor: default; }}
.nav select {{
  background: #21262d;
  color: #e6edf3;
  border: 1px solid #30363d;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 14px;
}}

/* 통계 바 */
.stats {{
  display: flex;
  justify-content: center;
  gap: 12px;
  margin: 12px 0 20px;
  flex-wrap: wrap;
}}
.stat-badge {{
  background: #161b22;
  border: 1px solid #30363d;
  padding: 6px 14px;
  border-radius: 20px;
  font-size: 13px;
}}
.stat-badge.new {{ border-color: #2ea043; color: #3fb950; }}
.stat-badge.existing {{ border-color: #d29922; color: #e3b341; }}

/* 카테고리 필터 */
.filters {{
  display: flex;
  justify-content: center;
  gap: 6px;
  margin: 0 0 20px;
  flex-wrap: wrap;
}}
.filter-btn {{
  background: #21262d;
  color: #8b949e;
  border: 1px solid #30363d;
  padding: 5px 12px;
  border-radius: 14px;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}}
.filter-btn:hover {{ color: #e6edf3; }}
.filter-btn.active {{
  background: #1f6feb33;
  color: #58a6ff;
  border-color: #1f6feb;
}}

/* 섹션 */
.section-title {{
  font-size: 16px;
  font-weight: 600;
  padding: 12px 0 8px;
  border-bottom: 1px solid #21262d;
  margin-bottom: 12px;
}}
.section-title.new {{ color: #3fb950; }}
.section-title.existing {{ color: #e3b341; }}

/* 카드 */
.card {{
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 12px;
  transition: border-color 0.2s;
}}
.card:hover {{ border-color: #58a6ff44; }}

.card-header {{
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
  gap: 8px;
}}
.card-rank {{
  font-size: 13px;
  color: #8b949e;
  min-width: 24px;
}}
.card-keyword {{
  font-size: 17px;
  font-weight: 600;
  flex: 1;
}}
.card-category {{
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 10px;
  white-space: nowrap;
}}
.cat-supplement {{ background: #2ea04322; color: #3fb950; border: 1px solid #2ea04366; }}
.cat-pharma {{ background: #f8514922; color: #f85149; border: 1px solid #f8514966; }}
.cat-disease {{ background: #58a6ff22; color: #58a6ff; border: 1px solid #58a6ff66; }}
.cat-consumer {{ background: #d2992222; color: #e3b341; border: 1px solid #d2992266; }}

.card-section {{
  margin: 10px 0;
  padding: 10px 12px;
  background: #0d111799;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
}}
.card-section .label {{
  font-weight: 600;
  margin-bottom: 4px;
  font-size: 12px;
}}
.label-why {{ color: #58a6ff; }}
.label-angle {{ color: #bc8cff; }}
.label-title {{ color: #3fb950; }}

.card-meta {{
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  font-size: 12px;
  color: #8b949e;
}}
.meta-tag {{
  background: #21262d;
  padding: 3px 8px;
  border-radius: 4px;
}}
.meta-tag.rising {{ color: #3fb950; }}
.meta-tag.falling {{ color: #f85149; }}
.meta-tag.gap-big {{ color: #e3b341; }}

.covered-badge {{
  display: inline-block;
  background: #d2992222;
  color: #e3b341;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 8px;
}}
.covered-posts {{
  font-size: 12px;
  color: #8b949e;
  margin-top: 6px;
  padding-left: 12px;
  border-left: 2px solid #30363d;
}}

/* 이슈 지표 바 */
.buzz-bar {{
  display: flex;
  gap: 8px;
  margin: 10px 0;
  padding: 8px 12px;
  background: #21262d;
  border-radius: 8px;
  font-size: 12px;
  flex-wrap: wrap;
  align-items: center;
}}
.buzz-item {{
  display: flex;
  align-items: center;
  gap: 4px;
}}
.buzz-value {{
  font-weight: 700;
  font-size: 14px;
}}
.buzz-value.hot {{ color: #f85149; }}
.buzz-value.warm {{ color: #e3b341; }}
.buzz-value.cool {{ color: #8b949e; }}
.buzz-label {{
  color: #8b949e;
}}
.buzz-divider {{
  color: #30363d;
  margin: 0 2px;
}}

.source-headlines {{
  font-size: 12px;
  color: #8b949e;
  margin-top: 8px;
}}
.source-headlines a {{
  color: #58a6ff;
  text-decoration: none;
}}
.source-headlines a:hover {{ text-decoration: underline; }}

.consecutive-badge {{
  display: inline-block;
  background: #58a6ff22;
  color: #58a6ff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 4px;
}}

/* 푸터 */
.footer {{
  text-align: center;
  color: #484f58;
  font-size: 12px;
  padding: 20px 0;
}}

/* 빈 상태 */
.empty {{
  text-align: center;
  color: #484f58;
  padding: 40px;
  font-size: 14px;
}}

/* 반응형 */
@media (max-width: 480px) {{
  body {{ padding: 10px; }}
  .card {{ padding: 12px; }}
  .card-keyword {{ font-size: 15px; }}
}}
</style>
</head>
<body>

<div class="header">
  <h1>건강 트렌드 스캐너 v2</h1>
  <div class="subtitle">약사 블로거를 위한 AI 글감 발굴기</div>
</div>

<div class="nav">
  <button id="prevBtn" onclick="navigate(-1)">&#9664; 이전</button>
  <select id="scanSelect" onchange="loadScan(this.value)"></select>
  <button id="nextBtn" onclick="navigate(1)">다음 &#9654;</button>
</div>

<div class="stats" id="statsBar"></div>

<div class="filters" id="filterBar"></div>

<div id="content"></div>

<div class="footer">
  <span id="costInfo"></span><br>
  건강 트렌드 스캐너 v2 · AI-powered blog topic discovery
</div>

<script>
// ── 데이터 ──
const SCAN_LIST = {scan_list_json};
const ALL_SCANS = {scans_json};

let currentIndex = 0;
let currentFilter = "전체";

// ── 초기화 ──
function init() {{
  const select = document.getElementById("scanSelect");
  SCAN_LIST.forEach((id, i) => {{
    const opt = document.createElement("option");
    opt.value = i;
    // 표시 형식: "3/13 08:00"
    const parts = id.split("_");
    const dateParts = parts[0].split("-");
    const timePart = parts[1] ? parts[1].slice(0,2) + ":" + parts[1].slice(2) : "";
    opt.textContent = dateParts[1] + "/" + dateParts[2] + " " + timePart;
    select.appendChild(opt);
  }});
  if (SCAN_LIST.length > 0) {{
    loadScan(0);
  }} else {{
    document.getElementById("content").innerHTML = '<div class="empty">아직 스캔 데이터가 없습니다.</div>';
  }}
}}

// ── 네비게이션 ──
function navigate(delta) {{
  const newIdx = currentIndex + delta;
  if (newIdx >= 0 && newIdx < SCAN_LIST.length) {{
    document.getElementById("scanSelect").value = newIdx;
    loadScan(newIdx);
  }}
}}

function loadScan(idx) {{
  idx = parseInt(idx);
  currentIndex = idx;
  const scanId = SCAN_LIST[idx];
  const data = ALL_SCANS[scanId];

  document.getElementById("prevBtn").disabled = (idx <= 0);
  document.getElementById("nextBtn").disabled = (idx >= SCAN_LIST.length - 1);

  if (!data) {{
    document.getElementById("content").innerHTML = '<div class="empty">데이터 로드 실패</div>';
    return;
  }}

  renderStats(data);
  renderFilters(data);
  renderTopics(data);
  renderCost(data);
}}

// ── 통계 바 ──
function renderStats(data) {{
  const s = data.stats || {{}};
  document.getElementById("statsBar").innerHTML = `
    <span class="stat-badge new">🆕 새 글감 ${{s.new_topics || 0}}개</span>
    <span class="stat-badge existing">🔥 기존주제 새이슈 ${{s.existing_topics_new_issue || 0}}개</span>
    <span class="stat-badge">📰 분석 뉴스 ${{s.total_news_collected || 0}}건</span>
  `;
}}

// ── 카테고리 필터 ──
function renderFilters(data) {{
  const categories = ["전체", "영양제·성분", "약업계·정책", "질환·치료", "소비자건강"];
  const html = categories.map(c => {{
    const active = c === currentFilter ? "active" : "";
    return `<button class="filter-btn ${{active}}" onclick="setFilter('${{c}}')">${{c}}</button>`;
  }}).join("");
  document.getElementById("filterBar").innerHTML = html;
}}

function setFilter(cat) {{
  currentFilter = cat;
  loadScan(currentIndex);
}}

// ── 카테고리 → CSS 클래스 ──
function catClass(category) {{
  if (category && category.includes("영양제")) return "cat-supplement";
  if (category && category.includes("약업계")) return "cat-pharma";
  if (category && category.includes("질환")) return "cat-disease";
  if (category && category.includes("소비자")) return "cat-consumer";
  return "cat-supplement";
}}

// ── 토픽 렌더링 ──
function renderTopics(data) {{
  const topics = data.topics || [];
  let filtered = topics;
  if (currentFilter !== "전체") {{
    filtered = topics.filter(t => t.category === currentFilter);
  }}

  const newTopics = filtered.filter(t => t.is_new_topic);
  const existingTopics = filtered.filter(t => !t.is_new_topic);

  let html = "";

  if (newTopics.length > 0) {{
    html += '<div class="section-title new">🆕 새 글감 발굴</div>';
    newTopics.forEach(t => {{ html += renderCard(t); }});
  }}

  if (existingTopics.length > 0) {{
    html += '<div class="section-title existing">🔥 기존 주제 — 새 이슈</div>';
    existingTopics.forEach(t => {{ html += renderCard(t); }});
  }}

  if (filtered.length === 0) {{
    html = '<div class="empty">이 카테고리에 해당하는 글감이 없습니다.</div>';
  }}

  document.getElementById("content").innerHTML = html;
}}

function renderCard(t) {{
  const trend = t.search_trend || {{}};
  const gap = t.expert_gap || {{}};
  const newsCount = t.news_count || 0;
  const newsHeadlines = t.news_headlines || [];

  // ── 이슈 지표 바 ──
  // 뉴스 건수
  let newsClass = "cool";
  if (newsCount >= 50) newsClass = "hot";
  else if (newsCount >= 10) newsClass = "warm";

  // 검색 트렌드
  let trendText = "";
  let trendClass = "cool";
  const cr = trend.change_rate || 0;
  if (cr > 50) {{ trendText = `+${{cr}}%`; trendClass = "hot"; }}
  else if (cr > 10) {{ trendText = `+${{cr}}%`; trendClass = "warm"; }}
  else if (cr < -10) {{ trendText = `${{cr}}%`; trendClass = "cool"; }}
  else {{ trendText = cr > 0 ? `+${{cr}}%` : `${{cr}}%`; }}

  // 검색량 절대치
  const avg = trend.weekly_avg || 0;
  let avgText = "";
  let avgClass = "cool";
  if (avg >= 50) {{ avgText = `${{avg.toFixed(0)}}`; avgClass = "hot"; }}
  else if (avg >= 20) {{ avgText = `${{avg.toFixed(0)}}`; avgClass = "warm"; }}
  else if (avg > 0) {{ avgText = `${{avg.toFixed(0)}}`; }}
  else {{ avgText = "-"; }}

  // 전문가갭
  let gapText = gap.label || "";
  let gapClass = "cool";
  if (gap.label === "전문가 갭 큼") gapClass = "warm";
  else if (gap.label === "전문가 부족") gapClass = "warm";

  const buzzBar = `
    <div class="buzz-bar">
      <div class="buzz-item">
        <span class="buzz-label">뉴스</span>
        <span class="buzz-value ${{newsClass}}">${{newsCount}}건</span>
      </div>
      <span class="buzz-divider">|</span>
      <div class="buzz-item">
        <span class="buzz-label">검색량</span>
        <span class="buzz-value ${{avgClass}}">${{avgText}}</span>
      </div>
      <span class="buzz-divider">|</span>
      <div class="buzz-item">
        <span class="buzz-label">변화</span>
        <span class="buzz-value ${{trendClass}}">${{trendText}}</span>
      </div>
      <span class="buzz-divider">|</span>
      <div class="buzz-item">
        <span class="buzz-label">전문가갭</span>
        <span class="buzz-value ${{gapClass}}">${{gapText}}</span>
      </div>
    </div>
  `;

  // 연속 등장
  let consecBadge = "";
  if (t.consecutive_days && t.consecutive_days >= 2) {{
    consecBadge = `<span class="consecutive-badge">${{t.consecutive_days}}일 연속</span>`;
  }}

  // 이미 작성 배지
  let coveredBadge = "";
  let coveredPosts = "";
  if (t.already_covered) {{
    const count = (t.covered_posts || []).length;
    coveredBadge = `<span class="covered-badge">이미 작성 ${{count}}편</span>`;
    if (t.covered_posts && t.covered_posts.length > 0) {{
      coveredPosts = '<div class="covered-posts">' +
        t.covered_posts.map(p => `· ${{escHtml(p)}}`).join("<br>") +
        '</div>';
    }}
  }}

  // 뉴스 헤드라인: AI가 근거로 삼은 source_headlines 우선 표시
  let headlinesHtml = "";
  if (t.source_headlines && t.source_headlines.length > 0) {{
    headlinesHtml = '<div class="source-headlines">' +
      t.source_headlines.map(h => `📰 ${{escHtml(h)}}`).join("<br>") +
      '</div>';
  }}

  return `
    <div class="card" data-category="${{t.category || ""}}">
      <div class="card-header">
        <span class="card-rank">${{t.rank}}</span>
        <span class="card-keyword">${{escHtml(t.keyword)}}${{coveredBadge}}${{consecBadge}}</span>
        <span class="card-category ${{catClass(t.category)}}">${{t.category || ""}}</span>
      </div>

      ${{buzzBar}}

      <div class="card-section">
        <div class="label label-why">💡 왜 지금?</div>
        ${{escHtml(t.why_now || "")}}
      </div>

      <div class="card-section">
        <div class="label label-angle">🎯 약사 앵글</div>
        ${{escHtml(t.pharmacist_angle || "")}}
      </div>

      <div class="card-section">
        <div class="label label-title">📝 제목 아이디어</div>
        <strong>${{escHtml(t.title_idea || "")}}</strong>
      </div>

      ${{coveredPosts}}
      ${{headlinesHtml}}
    </div>
  `;
}}

function escHtml(str) {{
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
}}

// ── 비용 ──
function renderCost(data) {{
  const meta = data.meta || {{}};
  const cost = meta.cost_usd || 0;
  document.getElementById("costInfo").textContent =
    `이 스캔 비용: $${{cost.toFixed(4)}} · ${{data.date || ""}} ${{data.time || ""}}`;
}}

// 시작
init();
</script>
</body>
</html>""";

    return html


def main():
    print("대시보드 생성 시작...")

    # 스캔 목록 로드
    scan_list = load_scan_list()
    print(f"  스캔 파일: {len(scan_list)}개")

    if not scan_list:
        # latest.json이라도 있으면 사용
        latest_path = os.path.join(DATA_DIR, "latest.json")
        if os.path.exists(latest_path):
            with open(latest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            scan_id = data.get("scan_id", "latest")
            scan_list = [scan_id]
            all_scans = {scan_id: data}
            print("  → latest.json에서 로드")
        else:
            print("  → 스캔 데이터 없음. 빈 대시보드 생성.")
            scan_list = []
            all_scans = {}
    else:
        # 모든 스캔 데이터 로드 (최근 28개)
        all_scans = {}
        for sid in scan_list:
            data = load_scan_data(sid)
            if data:
                all_scans[sid] = data
        print(f"  로드 완료: {len(all_scans)}개")

    # HTML 생성
    html = generate_html(scan_list, all_scans)

    out_path = os.path.join(DOCS_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  → {out_path}")
    print("대시보드 생성 완료!")


if __name__ == "__main__":
    main()
