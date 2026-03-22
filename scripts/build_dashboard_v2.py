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
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
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

/* 뷰 전환 탭 */
.view-tabs {{
  display: flex;
  justify-content: center;
  gap: 4px;
  margin: 16px 0 12px;
}}
.view-tab {{
  background: #21262d;
  color: #8b949e;
  border: 1px solid #30363d;
  padding: 8px 20px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}}
.view-tab:first-child {{ border-radius: 8px 0 0 8px; }}
.view-tab:last-child {{ border-radius: 0 8px 8px 0; }}
.view-tab.active {{
  background: #1f6feb33;
  color: #58a6ff;
  border-color: #1f6feb;
}}
.view-tab:hover:not(.active) {{ color: #e6edf3; }}

/* 추이 그래프 컨테이너 */
.trend-container {{
  background: #161b22;
  border: 1px solid #30363d;
  border-radius: 10px;
  padding: 20px;
  margin-bottom: 16px;
}}
.trend-container h3 {{
  color: #58a6ff;
  font-size: 15px;
  margin-bottom: 12px;
}}
.trend-chart-wrap {{
  position: relative;
  height: 350px;
  margin-bottom: 16px;
}}
.trend-legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}}
.trend-legend-item {{
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #8b949e;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
  transition: opacity 0.2s;
}}
.trend-legend-item:hover {{ opacity: 0.8; }}
.trend-legend-dot {{
  width: 10px;
  height: 10px;
  border-radius: 50%;
}}
.trend-info {{
  text-align: center;
  color: #484f58;
  font-size: 12px;
  margin-top: 8px;
}}
#trendView {{ display: none; }}

/* Dot Matrix 레이아웃 */
.dot-matrix-row {{
  display: flex;
  align-items: center;
  border-bottom: 1px solid #21262d;
}}
.dot-matrix-row:last-child {{ border-bottom: none; }}
.dot-matrix-label {{
  width: 220px;
  min-width: 220px;
  padding: 8px 12px 8px 0;
  font-size: 13px;
  color: #e6edf3;
  text-align: right;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.dot-matrix-label .days-badge {{
  font-size: 11px;
  color: #8b949e;
  margin-left: 4px;
}}
.dot-matrix-cells {{
  display: flex;
  flex: 1;
  align-items: center;
}}
.dot-matrix-cell {{
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  height: 36px;
}}
.dot-matrix-dot {{
  width: 14px;
  height: 14px;
  border-radius: 50%;
  transition: transform 0.15s;
}}
.dot-matrix-dot:hover {{
  transform: scale(1.4);
}}
.dot-matrix-header {{
  display: flex;
  align-items: center;
  margin-bottom: 4px;
}}
.dot-matrix-header-spacer {{
  width: 220px;
  min-width: 220px;
}}
.dot-matrix-header-cells {{
  display: flex;
  flex: 1;
}}
.dot-matrix-header-cell {{
  flex: 1;
  text-align: center;
  font-size: 11px;
  color: #8b949e;
  padding: 4px 0;
}}

/* 반응형 */
@media (max-width: 480px) {{
  body {{ padding: 10px; }}
  .card {{ padding: 12px; }}
  .card-keyword {{ font-size: 15px; }}
  .trend-chart-wrap {{ height: 250px; }}
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

<div class="view-tabs">
  <button class="view-tab active" onclick="switchView('daily')">📋 일별 글감</button>
  <button class="view-tab" onclick="switchView('trend')">📈 키워드 추이</button>
</div>

<div id="dailyView">
  <div class="stats" id="statsBar"></div>
  <div class="filters" id="filterBar"></div>
  <div id="content"></div>
</div>

<div id="trendView">
  <div class="nav" id="trendNav">
    <button id="trendPrevBtn" onclick="trendNavigate(-1)">&#9664; 1일 전</button>
    <span id="trendDateRange" style="color:#e6edf3;font-size:14px;padding:0 12px;"></span>
    <button id="trendNextBtn" onclick="trendNavigate(1)">1일 후 &#9654;</button>
  </div>
  <div class="trend-container">
    <h3>📈 키워드 등장 추이 (3회 이상 등장한 키워드)</h3>
    <div id="dotMatrixWrap"></div>
    <div class="trend-info" id="trendInfo"></div>
  </div>
  <div class="nav" id="trendNav2">
    <button id="trendPrevBtn2" onclick="trendNavigate(-1)">&#9664; 1일 전</button>
    <span id="trendDateRange2" style="color:#e6edf3;font-size:14px;padding:0 12px;"></span>
    <button id="trendNextBtn2" onclick="trendNavigate(1)">1일 후 &#9654;</button>
  </div>
  <div class="trend-container" id="newsHighContainer" style="display:none;">
    <h3>📊 뉴스 건수 추이 — 주요 키워드 (1,000건 이상)</h3>
    <div class="trend-chart-wrap">
      <canvas id="newsCountHighChart"></canvas>
    </div>
  </div>
  <div class="trend-container">
    <h3>📊 뉴스 건수 추이 — 일반 키워드 (1,000건 미만)</h3>
    <div class="trend-chart-wrap">
      <canvas id="newsCountLowChart"></canvas>
    </div>
    <div class="trend-info" id="newsCountInfo"></div>
  </div>
</div>

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

// ── 뷰 전환 ──
let currentView = "daily";
let newsHighChartInstance = null;
let newsLowChartInstance = null;

// 추이 데이터 (전체 기간, 한 번만 계산)
let allDates = [];
let allDateMap = {{}};
let allNewsCountMap = {{}};
let allKeyCount = {{}};
let allFrequentKeys = [];
let trendWindowEnd = -1; // allDates 인덱스 (마지막 날)

function switchView(view) {{
  currentView = view;
  document.querySelectorAll(".view-tab").forEach((btn, i) => {{
    btn.classList.toggle("active", (i === 0 && view === "daily") || (i === 1 && view === "trend"));
  }});
  document.getElementById("dailyView").style.display = view === "daily" ? "block" : "none";
  document.getElementById("trendView").style.display = view === "trend" ? "block" : "none";
  // 일별 글감 네비게이터
  document.querySelector(".nav").style.display = view === "daily" ? "flex" : "none";

  if (view === "trend") {{
    if (allDates.length === 0) buildTrendData();
    trendWindowEnd = allDates.length - 1;
    renderTrendWindow();
  }}
}}

// ── 키워드 정규화 (trend_key 없는 기존 데이터용 fallback) ──
function normalizeTrendKey(topic) {{
  if (topic.trend_key && topic.trend_key.trim()) {{
    return topic.trend_key.trim();
  }}
  let kw = (topic.keyword || "");
  kw = kw.replace(/\([^)]*\)/g, "").trim();
  kw = kw.split(/\s+[-+]\s+|\s+vs\s+/i)[0].trim();
  const words = kw.split(/\s+/);
  if (words.length > 3) kw = words.slice(0, 3).join(" ");
  return kw || topic.keyword || "";
}}

// ── 추이 그래프 ──
const TREND_COLORS = [
  "#58a6ff", "#3fb950", "#f85149", "#e3b341", "#bc8cff",
  "#f778ba", "#79c0ff", "#56d364", "#ff7b72", "#d2a8ff",
  "#ffa657", "#7ee787", "#ff9bce", "#a5d6ff", "#ffc680"
];

// 전체 기간 데이터 한 번 계산
function buildTrendData() {{
  const sortedScans = [...SCAN_LIST].reverse();
  sortedScans.forEach(scanId => {{
    const data = ALL_SCANS[scanId];
    if (!data) return;
    const date = data.date || scanId.split("_")[0];
    if (!allDateMap[date]) allDateMap[date] = {{}};
    if (!allNewsCountMap[date]) allNewsCountMap[date] = {{}};
    (data.topics || []).forEach(t => {{
      const tk = normalizeTrendKey(t);
      allDateMap[date][tk] = true;
      const nc = t.news_count || 0;
      if (!allNewsCountMap[date][tk] || nc > allNewsCountMap[date][tk]) {{
        allNewsCountMap[date][tk] = nc;
      }}
    }});
  }});
  allDates = Object.keys(allDateMap).sort();

  // prefix 기반 병합: "리포좀 NMN 신제품" → "리포좀 NMN"으로 통합
  const allKeys = new Set();
  allDates.forEach(d => Object.keys(allDateMap[d]).forEach(tk => allKeys.add(tk)));
  const keyList = [...allKeys].sort((a, b) => a.length - b.length); // 짧은 것 먼저
  const mergeMap = {{}}; // 긴 키 → 짧은 키
  for (let i = 0; i < keyList.length; i++) {{
    for (let j = i + 1; j < keyList.length; j++) {{
      const short = keyList[i];
      const long = keyList[j];
      // 짧은 키가 긴 키의 시작 부분이면 병합 (최소 2글자 이상 일치)
      if (short.length >= 2 && long.startsWith(short + " ") && !mergeMap[short]) {{
        mergeMap[long] = mergeMap[short] || short;
      }}
    }}
  }}
  // 병합 적용
  if (Object.keys(mergeMap).length > 0) {{
    allDates.forEach(d => {{
      const keys = Object.keys(allDateMap[d]);
      keys.forEach(tk => {{
        const target = mergeMap[tk];
        if (target && target !== tk) {{
          allDateMap[d][target] = true;
          delete allDateMap[d][tk];
          // 뉴스 건수도 병합 (최대값)
          if (allNewsCountMap[d] && allNewsCountMap[d][tk]) {{
            const nc = allNewsCountMap[d][tk];
            if (!allNewsCountMap[d][target] || nc > allNewsCountMap[d][target]) {{
              allNewsCountMap[d][target] = nc;
            }}
            delete allNewsCountMap[d][tk];
          }}
        }}
      }});
    }});
  }}

  // 전체 기간 등장일수
  allDates.forEach(d => {{
    Object.keys(allDateMap[d]).forEach(tk => {{
      allKeyCount[tk] = (allKeyCount[tk] || 0) + 1;
    }});
  }});
  allFrequentKeys = Object.entries(allKeyCount)
    .filter(([k, c]) => c >= 3)
    .sort((a, b) => b[1] - a[1])
    .map(([k]) => k);
}}

// ── 추이 날짜 네비게이션 ──
function trendNavigate(delta) {{
  const newEnd = trendWindowEnd + delta;
  if (newEnd >= 0 && newEnd < allDates.length) {{
    trendWindowEnd = newEnd;
    renderTrendWindow();
  }}
}}

function renderTrendWindow() {{
  // 14일 윈도우 계산
  const WINDOW_DAYS = 14;
  const winStart = Math.max(0, trendWindowEnd - WINDOW_DAYS + 1);
  const windowDates = allDates.slice(winStart, trendWindowEnd + 1);

  // 네비게이션 버튼 상태 (상단 + 하단 동기화)
  const prevDisabled = (trendWindowEnd <= 2);
  const nextDisabled = (trendWindowEnd >= allDates.length - 1);
  document.getElementById("trendPrevBtn").disabled = prevDisabled;
  document.getElementById("trendNextBtn").disabled = nextDisabled;
  document.getElementById("trendPrevBtn2").disabled = prevDisabled;
  document.getElementById("trendNextBtn2").disabled = nextDisabled;

  // 날짜 범위 표시
  const fmt = d => {{ const p = d.split("-"); return parseInt(p[1]) + "/" + parseInt(p[2]); }};
  const rangeText = fmt(windowDates[0]) + " ~ " + fmt(windowDates[windowDates.length - 1]) +
    " (" + windowDates.length + "일)";
  document.getElementById("trendDateRange").textContent = rangeText;
  document.getElementById("trendDateRange2").textContent = rangeText;

  const labels = windowDates.map(fmt);

  // 이 윈도우에 등장한 frequent 키워드만 필터
  const windowKeys = allFrequentKeys.filter(tk =>
    windowDates.some(d => allDateMap[d] && allDateMap[d][tk])
  );

  if (windowKeys.length === 0) {{
    document.getElementById("trendInfo").textContent = "이 기간에 3회 이상 등장한 키워드가 없습니다.";
    return;
  }}

  // ── 차트 1: HTML Dot Matrix ──
  let matrixHtml = "";
  // 헤더 (날짜)
  matrixHtml += '<div class="dot-matrix-header">';
  matrixHtml += '<div class="dot-matrix-header-spacer"></div>';
  matrixHtml += '<div class="dot-matrix-header-cells">';
  labels.forEach(l => {{
    matrixHtml += `<div class="dot-matrix-header-cell">${{l}}</div>`;
  }});
  matrixHtml += '</div></div>';
  // 각 키워드 행
  windowKeys.forEach((tk, i) => {{
    const color = TREND_COLORS[i % TREND_COLORS.length];
    matrixHtml += '<div class="dot-matrix-row">';
    matrixHtml += `<div class="dot-matrix-label" title="${{escHtml(tk)}}">${{escHtml(tk)}} <span class="days-badge">${{allKeyCount[tk]}}일</span></div>`;
    matrixHtml += '<div class="dot-matrix-cells">';
    windowDates.forEach(d => {{
      if (allDateMap[d] && allDateMap[d][tk]) {{
        matrixHtml += `<div class="dot-matrix-cell"><div class="dot-matrix-dot" style="background:${{color}}" title="${{tk}} (${{d}})"></div></div>`;
      }} else {{
        matrixHtml += '<div class="dot-matrix-cell"></div>';
      }}
    }});
    matrixHtml += '</div></div>';
  }});

  document.getElementById("dotMatrixWrap").innerHTML = matrixHtml;
  document.getElementById("trendInfo").textContent =
    `전체 ${{allDates.length}}일 중 ${{windowDates.length}}일 표시 · ${{windowKeys.length}}개 키워드`;

  // ── 차트 2 & 3: 뉴스 건수 (1000건 기준 분할) ──
  const NEWS_OUTLIER_CAP = 5000;
  const NEWS_SPLIT = 1000;

  // 유효한 뉴스 건수가 있는 키워드
  const newsKeysAll = windowKeys.filter(tk =>
    windowDates.some(d => {{
      const nc = allNewsCountMap[d] && allNewsCountMap[d][tk];
      return nc && nc > 0 && nc <= NEWS_OUTLIER_CAP;
    }})
  );

  // 최대 뉴스 건수 기준으로 분류
  const getMaxNews = (tk) => {{
    let mx = 0;
    windowDates.forEach(d => {{
      const nc = (allNewsCountMap[d] && allNewsCountMap[d][tk]) || 0;
      if (nc <= NEWS_OUTLIER_CAP && nc > mx) mx = nc;
    }});
    return mx;
  }};

  const highKeys = newsKeysAll.filter(tk => getMaxNews(tk) >= NEWS_SPLIT);
  const lowKeys = newsKeysAll.filter(tk => getMaxNews(tk) < NEWS_SPLIT);

  // 주요 키워드 차트 (1000건 이상)
  const highContainer = document.getElementById("newsHighContainer");
  if (highKeys.length > 0) {{
    highContainer.style.display = "block";
    const ds = highKeys.map((tk, i) => {{
      const color = TREND_COLORS[i % TREND_COLORS.length];
      return {{
        label: tk,
        data: windowDates.map(d => {{
          const nc = (allNewsCountMap[d] && allNewsCountMap[d][tk]) || null;
          return (nc && nc <= NEWS_OUTLIER_CAP) ? nc : null;
        }}),
        borderColor: color,
        backgroundColor: color + "33",
        borderWidth: 2, pointRadius: 4, pointHoverRadius: 6,
        tension: 0.3, fill: false, spanGaps: true,
      }};
    }});
    if (newsHighChartInstance) newsHighChartInstance.destroy();
    newsHighChartInstance = new Chart(
      document.getElementById("newsCountHighChart").getContext("2d"),
      buildNewsChartConfig(labels, ds)
    );
  }} else {{
    highContainer.style.display = "none";
  }}

  // 일반 키워드 차트 (1000건 미만)
  if (lowKeys.length > 0) {{
    const ds = lowKeys.map((tk, i) => {{
      const ci = highKeys.length + i;
      const color = TREND_COLORS[ci % TREND_COLORS.length];
      return {{
        label: tk,
        data: windowDates.map(d => {{
          const nc = (allNewsCountMap[d] && allNewsCountMap[d][tk]) || null;
          return (nc && nc <= NEWS_OUTLIER_CAP) ? nc : null;
        }}),
        borderColor: color,
        backgroundColor: color + "33",
        borderWidth: 2, pointRadius: 4, pointHoverRadius: 6,
        tension: 0.3, fill: false, spanGaps: true,
      }};
    }});
    if (newsLowChartInstance) newsLowChartInstance.destroy();
    newsLowChartInstance = new Chart(
      document.getElementById("newsCountLowChart").getContext("2d"),
      buildNewsChartConfig(labels, ds)
    );
    document.getElementById("newsCountInfo").textContent =
      `범례를 클릭하면 특정 키워드를 숨기거나 표시할 수 있습니다`;
  }} else {{
    document.getElementById("newsCountInfo").textContent = "이 기간에 뉴스 건수 데이터가 없습니다.";
  }}
}}

function buildNewsChartConfig(labels, datasets) {{
  return {{
    type: "line",
    data: {{ labels, datasets }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: "index", intersect: false }},
      plugins: {{
        legend: {{
          display: true,
          position: "bottom",
          labels: {{
            color: "#8b949e",
            font: {{ size: 11 }},
            boxWidth: 12,
            padding: 8,
          }},
        }},
      }},
      scales: {{
        x: {{
          ticks: {{ color: "#8b949e", font: {{ size: 12 }} }},
          grid: {{ color: "#21262d" }},
        }},
        y: {{
          ticks: {{ color: "#8b949e", font: {{ size: 11 }} }},
          grid: {{ color: "#21262d" }},
          beginAtZero: true,
          title: {{
            display: true,
            text: "뉴스 건수",
            color: "#8b949e",
          }},
        }},
      }},
    }},
  }};
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
