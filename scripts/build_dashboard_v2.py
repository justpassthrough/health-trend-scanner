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
    """스캔 파일 목록 (최근 90일) — 추이 그래프에서 과거로 탐색 가능하도록"""
    files = sorted(glob.glob(os.path.join(SCANS_DIR, "*.json")), reverse=True)
    scans = []
    for f in files[:180]:  # 최대 180개 (90일 × 2회)
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
.section-title.search {{ color: #58a6ff; }}
.section-title.news {{ color: #f0883e; }}
.section-desc {{
  font-size: 12px;
  color: #8b949e;
  font-weight: 400;
  margin-left: 6px;
}}

/* 오늘의 1픽 */
.today-pick {{
  background: linear-gradient(135deg, #1c2333, #161b22);
  border: 1px solid #d2992255;
  border-radius: 12px;
  padding: 16px 18px;
  margin-bottom: 22px;
}}
.today-pick .tp-head {{
  font-size: 15px; font-weight: 700; color: #f0c000; margin-bottom: 12px;
}}
.today-pick .tp-item {{
  padding: 10px 0; border-top: 1px solid #21262d;
}}
.today-pick .tp-item:first-of-type {{ border-top: none; }}
.today-pick .tp-kw {{ font-size: 15px; font-weight: 600; color: #e6edf3; }}
.today-pick .tp-reason {{ font-size: 12px; color: #8b949e; margin-left: 8px; }}
.today-pick .tp-title {{ font-size: 13px; color: #58a6ff; margin-top: 4px; }}
.today-pick .tp-why {{ font-size: 12px; color: #8b949e; margin-top: 3px; line-height: 1.5; }}

/* 점수/황금/경쟁도 배지 */
.score-badge {{
  display: inline-block;
  background: #1f6feb22;
  color: #58a6ff;
  border: 1px solid #1f6feb55;
  font-size: 12px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
}}
.score-badge.news {{ background: #f0883e22; color: #f0883e; border-color: #f0883e55; }}
.golden-badge {{
  display: inline-block;
  background: #d2992233;
  color: #f0c000;
  border: 1px solid #d2992288;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  margin-left: 6px;
}}
.buzz-value.comp-low {{ color: #3fb950; }}
.buzz-value.comp-mid {{ color: #e3b341; }}
.buzz-value.comp-high {{ color: #f85149; }}
.stat-badge.search {{ border-color: #1f6feb; color: #58a6ff; }}
.stat-badge.news {{ border-color: #f0883e; color: #f0883e; }}
.stat-badge.golden {{ border-color: #d29922; color: #f0c000; }}

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

/* 기회 사분면 차트 컨테이너 */
.chart-wrap {{ position: relative; height: 400px; }}

/* 지속 리더보드 */
.lead-card {{ padding: 10px 2px; border-bottom: 1px solid #21262d; }}
.lead-card:last-child {{ border-bottom: none; }}
.lead-top {{ display: flex; align-items: center; gap: 8px; }}
.lead-rank {{ width: 20px; color: #8b949e; font-size: 13px; text-align: center; }}
.lead-name {{ font-weight: 600; font-size: 15px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.trk {{ font-size: 10px; padding: 2px 7px; border-radius: 9px; white-space: nowrap; }}
.trk.s {{ background: #1f6feb22; color: #58a6ff; border: 1px solid #1f6feb66; }}
.trk.n {{ background: #f0883e22; color: #f0883e; border: 1px solid #f0883e66; }}
.lead-bottom {{ display: grid; grid-template-columns: 132px 96px 1fr; align-items: center; gap: 8px; margin-top: 7px; padding-left: 28px; }}
.streak {{ letter-spacing: 1px; font-size: 12px; white-space: nowrap; }}
.streak .on-s {{ color: #58a6ff; }}
.streak .on-n {{ color: #f0883e; }}
.streak .off {{ color: #30363d; }}
.streak b {{ color: #e6edf3; margin-left: 2px; }}
.lead-meta {{ font-size: 12px; color: #8b949e; }}
.lead-meta .gold {{ color: #f0c000; }}
.spark {{ vertical-align: middle; }}
.spark-empty {{ display: inline-block; width: 90px; text-align: center; color: #484f58; font-size: 12px; }}
@media (max-width: 480px) {{
  .lead-bottom {{ grid-template-columns: 120px 70px 1fr; padding-left: 22px; gap: 6px; }}
  .lead-meta {{ font-size: 11px; }}
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
  <div class="trend-container" id="oppContainer" style="display:none;">
    <h3>💎 오늘의 기회 사분면 <span style="font-size:12px;color:#8b949e;font-weight:400;">검색형 · 오른쪽 위(초록)일수록 알짜</span></h3>
    <div class="chart-wrap"><canvas id="oppBubble"></canvas></div>
    <div class="trend-info">버블 크기 = 기회점수 · 가로 = 월검색량 · 세로 = 경쟁(위=낮음)</div>
  </div>
  <div class="filters" id="filterBar"></div>
  <div id="content"></div>
</div>

<div id="trendView">
  <div class="nav" id="trendNav">
    <button id="trendPrevBtn" onclick="trendNavigate(-1)">&#9664; 1일 전</button>
    <span id="trendDateRange" style="color:#e6edf3;font-size:14px;padding:0 12px;"></span>
    <button id="trendNextBtn" onclick="trendNavigate(1)">1일 후 &#9654;</button>
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
  <div class="nav" id="trendNav2">
    <button id="trendPrevBtn2" onclick="trendNavigate(-1)">&#9664; 1일 전</button>
    <span id="trendDateRange2" style="color:#e6edf3;font-size:14px;padding:0 12px;"></span>
    <button id="trendNextBtn2" onclick="trendNavigate(1)">1일 후 &#9654;</button>
  </div>
  <div class="trend-container">
    <h3>📈 지속 키워드 리더보드 <span style="font-size:12px;color:#8b949e;font-weight:400;">월검색량 많은 순 · 며칠째 뜨는지 + 미니 추이</span></h3>
    <div id="leaderboard"></div>
    <div class="trend-info" id="trendInfo"></div>
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
  renderOppBubble(data);
  renderFilters(data);
  renderTopics(data);
  renderCost(data);
}}

// ── 기회 사분면 버블 (검색형 전용, 오늘 스냅샷) ──
const FRESH_S = "#58a6ff", GOLD = "#f0c000";
const DEMAND_SPLIT = 500, COMP_SPLIT = 1.5;  // 절대 기준: 월 500회 이상=수요 많음 / 경쟁 "낮음"만 좋음

function compToNum(comp) {{
  return {{"낮음": 1, "중간": 2, "높음": 3}}[comp] || null;
}}

const quadrantPlugin = {{
  id: "quad",
  beforeDraw(chart, args, opts) {{
    const a = chart.chartArea, x = chart.scales.x, y = chart.scales.y;
    if (!a || !x || !y) return;
    const split = (opts && opts.split) || DEMAND_SPLIT;
    const xs = x.getPixelForValue(split), ys = y.getPixelForValue(COMP_SPLIT);
    const ctx = chart.ctx;
    ctx.save();
    ctx.fillStyle = "rgba(63,185,80,0.10)"; ctx.fillRect(xs, a.top, a.right - xs, ys - a.top);
    ctx.fillStyle = "rgba(248,81,73,0.08)"; ctx.fillRect(xs, ys, a.right - xs, a.bottom - ys);
    ctx.strokeStyle = "#30363d"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(xs, a.top); ctx.lineTo(xs, a.bottom); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(a.left, ys); ctx.lineTo(a.right, ys); ctx.stroke();
    ctx.setLineDash([]);
    // 수요 분할선이 어떤 절대 기준인지 표시 (예: 월 500)
    ctx.fillStyle = "#6e7681"; ctx.font = "10px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "bottom";
    ctx.fillText("기준 월 " + split, xs, a.bottom - 2);
    ctx.font = "bold 12px sans-serif"; ctx.textBaseline = "top";
    ctx.fillStyle = "rgba(63,185,80,0.85)"; ctx.textAlign = "right";
    ctx.fillText("💎 황금 (수요多·경쟁低)", a.right - 8, a.top + 6);
    ctx.fillStyle = "rgba(248,81,73,0.7)";
    ctx.fillText("포화 (레드오션)", a.right - 8, a.bottom - 20);
    ctx.fillStyle = "rgba(139,148,158,0.6)"; ctx.textAlign = "left";
    ctx.fillText("틈새", a.left + 8, a.top + 6);
    ctx.restore();
  }}
}};

const labelPlugin = {{
  id: "blabel",
  afterDatasetsDraw(chart) {{
    const area = chart.chartArea, ctx = chart.ctx;
    if (!area) return;
    ctx.save();
    ctx.font = "12px sans-serif"; ctx.textBaseline = "middle";
    const pts = [];
    chart.data.datasets.forEach((d, di) => {{
      chart.getDatasetMeta(di).data.forEach((p, i) => {{
        pts.push({{ x: p.x, y: p.y, r: p.options.radius, name: d._kw[i].name }});
      }});
    }});
    pts.sort((a, b) => a.x - b.x);
    const placed = [];
    pts.forEach(p => {{
      const w = ctx.measureText(p.name).width, h = 15;
      const cands = [
        {{ tx: p.x, ty: p.y - p.r - 9, a: "center" }}, {{ tx: p.x, ty: p.y + p.r + 9, a: "center" }},
        {{ tx: p.x + p.r + 6, ty: p.y, a: "left" }}, {{ tx: p.x - p.r - 6, ty: p.y, a: "right" }},
        {{ tx: p.x, ty: p.y - p.r - 24, a: "center" }}, {{ tx: p.x, ty: p.y + p.r + 24, a: "center" }},
      ];
      let ch = null;
      for (const c of cands) {{
        const l = c.a === "center" ? c.tx - w / 2 : c.a === "left" ? c.tx : c.tx - w;
        const r = l + w, t = c.ty - h / 2, b = c.ty + h / 2;
        if (l < area.left || r > area.right || t < area.top || b > area.bottom) continue;
        if (placed.some(q => !(r < q.l || l > q.r || b < q.t || t > q.b))) continue;
        ch = {{ tx: c.tx, ty: c.ty, a: c.a, box: {{ l, r, t, b }} }}; break;
      }}
      if (!ch) {{ const c = cands[0], l = c.tx - w / 2; ch = {{ tx: c.tx, ty: c.ty, a: c.a, box: {{ l, r: l + w, t: c.ty - h / 2, b: c.ty + h / 2 }} }}; }}
      if (Math.abs(ch.ty - p.y) > p.r + 14) {{
        ctx.strokeStyle = "#484f58"; ctx.lineWidth = 0.8;
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(ch.tx, ch.ty); ctx.stroke();
      }}
      ctx.fillStyle = "#e6edf3"; ctx.textAlign = ch.a; ctx.fillText(p.name, ch.tx, ch.ty);
      placed.push(ch.box);
    }});
    ctx.restore();
  }}
}};

let oppBubbleInstance = null;
function renderOppBubble(data) {{
  const container = document.getElementById("oppContainer");
  const topics = (data.topics || []).filter(t =>
    (t.track || "검색형") === "검색형" && t.search_volume != null && compToNum(t.comp_idx)
  );
  if (topics.length === 0) {{
    container.style.display = "none";
    if (oppBubbleInstance) {{ oppBubbleInstance.destroy(); oppBubbleInstance = null; }}
    return;
  }}
  container.style.display = "block";

  // 축 범위(줌)는 데이터에 맞춰 동적. 단 절대 분할선(DEMAND_SPLIT)은 항상 화면에 포함시켜
  // '황금이냐 아니냐' 기준선이 매번 같은 의미를 갖도록 함.
  const svs = topics.map(t => t.search_volume).filter(v => v != null && v > 0);
  const dmin = Math.min(...svs), dmax = Math.max(...svs);
  const axMin = Math.max(1, Math.pow(10, Math.floor(Math.log10(dmin))));
  const axMax = Math.pow(10, Math.ceil(Math.log10(Math.max(dmax, DEMAND_SPLIT))));

  // 금색(황금) 판정 = 사분면 우상단(검색량 ≥ 분할선 & 경쟁 "낮음"=1). 차트 분할선과 100% 일치시켜
  // 데이터 라벨이 옛 기준(1000)으로 박혀 있어도 그림이 어긋나지 않게 함.
  const isGold = t => t.search_volume >= DEMAND_SPLIT && compToNum(t.comp_idx) === 1;
  const gold = topics.filter(isGold);
  const norm = topics.filter(t => !isGold(t));
  const mk = (list, color) => {{
    const d = {{
      data: list.map(t => ({{ x: Math.max(t.search_volume, axMin), y: compToNum(t.comp_idx), r: Math.min(26, Math.max(8, (t.score || t.opportunity_score || 3) * 2.2)) }})),
      backgroundColor: color + "cc", borderColor: color, borderWidth: 2,
    }};
    d._kw = list.map(t => ({{ name: t.keyword }}));
    return d;
  }};
  if (oppBubbleInstance) oppBubbleInstance.destroy();
  oppBubbleInstance = new Chart(document.getElementById("oppBubble").getContext("2d"), {{
    type: "bubble",
    data: {{ datasets: [mk(norm, FRESH_S), mk(gold, GOLD)] }},
    options: {{
      responsive: true, maintainAspectRatio: false, layout: {{ padding: {{ top: 28, right: 28, bottom: 16, left: 16 }} }},
      plugins: {{
        legend: {{ display: false }},
        quad: {{ split: DEMAND_SPLIT }},
        tooltip: {{ callbacks: {{ label: (c) => {{
          const all = c.datasetIndex === 1 ? gold : norm; const t = all[c.dataIndex];
          return `${{t.keyword}}: 월검색 ${{(t.search_volume||0).toLocaleString()}} · 경쟁 ${{t.comp_idx}} · 기회 ${{t.score||t.opportunity_score}}`;
        }} }} }},
      }},
      scales: {{
        x: {{ type: "logarithmic", min: axMin, max: axMax,
          title: {{ display: true, text: "월검색량 (오른쪽=수요↑)", color: "#8b949e" }},
          ticks: {{ color: "#8b949e", callback: v => ({{1:"1",10:"10",100:"100",1000:"1천",10000:"1만",100000:"10만"}}[v] || "") }}, grid: {{ color: "#21262d" }} }},
        y: {{ min: 0.5, max: 3.5, reverse: true,
          title: {{ display: true, text: "경쟁 (위=낮음, 좋음)", color: "#8b949e" }},
          ticks: {{ color: "#8b949e", stepSize: 1, callback: v => ({{1:"낮음",2:"중간",3:"높음"}}[v] || "") }}, grid: {{ display: false }} }},
      }},
    }},
    plugins: [quadrantPlugin, labelPlugin],
  }});
}}

// ── 통계 바 ──
function renderStats(data) {{
  const s = data.stats || {{}};
  // 구버전 스캔(트랙 없음) 대비 fallback 계산
  const topics = data.topics || [];
  const searchN = (s.search_topics != null) ? s.search_topics
    : topics.filter(t => (t.track || "검색형") === "검색형").length;
  const newsN = (s.news_topics != null) ? s.news_topics
    : topics.filter(t => t.track === "시의형").length;
  const goldenN = (s.golden_topics != null) ? s.golden_topics
    : topics.filter(t => (t.opportunity_label || "").includes("황금")).length;
  let goldenBadge = goldenN > 0
    ? `<span class="stat-badge golden">💎 황금 ${{goldenN}}개</span>` : "";
  document.getElementById("statsBar").innerHTML = `
    <span class="stat-badge search">🔍 검색형 ${{searchN}}개</span>
    <span class="stat-badge news">📰 시의형 ${{newsN}}개</span>
    ${{goldenBadge}}
    <span class="stat-badge">🆕 새 글감 ${{s.new_topics || 0}}개</span>
    <span class="stat-badge">📑 분석 뉴스 ${{s.total_news_collected || 0}}건</span>
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

// ── 오늘의 1픽 ──
function renderTodayPick(data) {{
  const picks = data.today_pick || [];
  if (picks.length === 0) return "";
  let items = picks.map(p => {{
    const trk = (p.track === "시의형") ? "n" : "s";
    const vol = (p.search_volume != null)
      ? `<span class="tp-reason">· 월 ${{Number(p.search_volume).toLocaleString()}}회</span>` : "";
    const title = p.title_idea ? `<div class="tp-title">💡 ${{p.title_idea}}</div>` : "";
    const why = p.why_now ? `<div class="tp-why">${{p.why_now}}</div>` : "";
    return `<div class="tp-item">`
      + `<span class="trk ${{trk}}">${{p.track || "검색형"}}</span> `
      + `<span class="tp-kw">${{p.keyword || ""}}</span>`
      + `<span class="tp-reason">${{p.reason || ""}}</span>${{vol}}`
      + title + why + `</div>`;
  }}).join("");
  return `<div class="today-pick"><div class="tp-head">⭐ 오늘의 1픽</div>${{items}}</div>`;
}}

// ── 토픽 렌더링 ──
function renderTopics(data) {{
  const topics = data.topics || [];
  let filtered = topics;
  if (currentFilter !== "전체") {{
    filtered = topics.filter(t => t.category === currentFilter);
  }}

  // 트랙으로 1차 분리 (트랙 없는 구버전 데이터는 검색형으로 간주)
  const searchTopics = filtered.filter(t => (t.track || "검색형") === "검색형");
  const newsTopics = filtered.filter(t => t.track === "시의형");

  let html = "";

  // 오늘의 1픽은 전체 보기에서만 (카테고리 필터 시 숨김)
  if (currentFilter === "전체") {{
    html += renderTodayPick(data);
  }}

  if (searchTopics.length > 0) {{
    html += '<div class="section-title search">🔍 검색형 글감'
      + '<span class="section-desc">사람들이 검색하는 성분·증상 · 실검색량 기준 정렬</span></div>';
    searchTopics.forEach(t => {{ html += renderCard(t); }});
  }}

  if (newsTopics.length > 0) {{
    html += '<div class="section-title news">📰 시의형 글감'
      + '<span class="section-desc">지금 터진 산업·정책·신약 이슈 · 뉴스 규모 기준 정렬</span></div>';
    newsTopics.forEach(t => {{ html += renderCard(t); }});
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
  const track = t.track || "검색형";

  // 뉴스 건수 색상
  let newsClass = "cool";
  if (newsCount >= 50) newsClass = "hot";
  else if (newsCount >= 10) newsClass = "warm";

  // 검색 트렌드(변화율)
  const cr = trend.change_rate || 0;
  let trendText = cr > 0 ? `+${{cr}}%` : `${{cr}}%`;
  let trendClass = "cool";
  if (cr > 50) trendClass = "hot";
  else if (cr > 10) trendClass = "warm";

  // 전문가갭
  let gapText = gap.label || "-";
  let gapClass = "cool";
  if (gap.label === "전문가 갭 큼" || gap.label === "전문가 부족") gapClass = "warm";

  // 절대 월검색수 + 경쟁도
  const sv = t.search_volume;
  let svText = (sv == null) ? "-" : sv.toLocaleString();
  let svClass = "cool";
  if (sv != null && sv >= 5000) svClass = "hot";
  else if (sv != null && sv >= 1000) svClass = "warm";
  const comp = t.comp_idx || "";
  let compClass = "cool";
  if (comp === "낮음") compClass = "comp-low";
  else if (comp === "중간") compClass = "comp-mid";
  else if (comp === "높음") compClass = "comp-high";

  // 신선도(최신 기사 경과시간) — 시의형 정렬의 핵심 신호
  const rec = t.news_recency || {{}};
  const nh = rec.newest_hours;
  let freshText = "-";
  let freshClass = "cool";
  if (nh != null) {{
    if (nh < 24) {{ freshText = `${{Math.round(nh)}}시간 전`; freshClass = "hot"; }}
    else if (nh < 72) {{ freshText = `${{Math.round(nh/24)}}일 전`; freshClass = "warm"; }}
    else {{ freshText = `${{Math.round(nh/24)}}일 전`; }}
  }}
  const c24 = rec.count_24h || 0;

  const item = (label, valHtml) =>
    `<div class="buzz-item"><span class="buzz-label">${{label}}</span>${{valHtml}}</div>`;
  const div = '<span class="buzz-divider">|</span>';
  let buzzBar;
  if (track === "시의형") {{
    // 시의형: 신선도(최신기사) + 24h 기사다발 + 뉴스규모 + 전문가갭
    buzzBar = `<div class="buzz-bar">`
      + item("최신기사", `<span class="buzz-value ${{freshClass}}">${{freshText}}</span>`) + div
      + item("24h내", `<span class="buzz-value ${{c24>=3?'warm':'cool'}}">${{c24}}건</span>`) + div
      + item("뉴스", `<span class="buzz-value ${{newsClass}}">${{newsCount}}건</span>`) + div
      + item("전문가갭", `<span class="buzz-value ${{gapClass}}">${{gapText}}</span>`)
      + `</div>`;
  }} else {{
    // 검색형: 월검색수 + 경쟁 + 변화 + 전문가갭
    buzzBar = `<div class="buzz-bar">`
      + item("월검색", `<span class="buzz-value ${{svClass}}">${{svText}}</span>`) + div
      + item("경쟁", `<span class="buzz-value ${{compClass}}">${{comp || "-"}}</span>`) + div
      + item("변화", `<span class="buzz-value ${{trendClass}}">${{trendText}}</span>`) + div
      + item("전문가갭", `<span class="buzz-value ${{gapClass}}">${{gapText}}</span>`)
      + `</div>`;
  }}

  // 점수 배지 (검색형=기회점수 / 시의형=시의점수)
  const scoreVal = (t.score != null) ? t.score : "";
  const scoreLabel = (track === "시의형") ? "시의점수" : "기회점수";
  const scoreBadge = (scoreVal !== "")
    ? `<span class="score-badge ${{track === "시의형" ? "news" : ""}}">${{scoreLabel}} ${{scoreVal}}</span>` : "";

  // 황금 키워드 배지
  const goldBadge = (t.opportunity_label && t.opportunity_label.includes("황금"))
    ? `<span class="golden-badge">💎 ${{escHtml(t.opportunity_label)}}</span>` : "";

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
        <span class="card-keyword">${{escHtml(t.keyword)}}${{goldBadge}}${{coveredBadge}}${{consecBadge}}</span>
        <span class="card-category ${{catClass(t.category)}}">${{t.category || ""}}</span>
      </div>

      <div style="margin:6px 0 2px;">${{scoreBadge}}</div>
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
let allMetaMap = {{}};   // [date][tk] = {{track, search_volume, score, comp_idx, opportunity_label, newest_hours}}
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
    if (!allMetaMap[date]) allMetaMap[date] = {{}};
    (data.topics || []).forEach(t => {{
      const tk = normalizeTrendKey(t);
      allDateMap[date][tk] = true;
      const nc = t.news_count || 0;
      if (!allNewsCountMap[date][tk] || nc > allNewsCountMap[date][tk]) {{
        allNewsCountMap[date][tk] = nc;
      }}
      allMetaMap[date][tk] = {{
        track: t.track || "검색형",
        search_volume: (t.search_volume != null) ? t.search_volume : null,
        score: (t.score != null) ? t.score : null,
        comp_idx: t.comp_idx || "",
        opportunity_label: t.opportunity_label || "",
        newest_hours: (t.news_recency && t.news_recency.newest_hours != null) ? t.news_recency.newest_hours : null,
      }};
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
          // 메타도 병합 (target 우선)
          if (allMetaMap[d] && allMetaMap[d][tk]) {{
            if (!allMetaMap[d][target]) allMetaMap[d][target] = allMetaMap[d][tk];
            delete allMetaMap[d][tk];
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
    .filter(([k, c]) => c >= 2)
    .sort((a, b) => b[1] - a[1])
    .map(([k]) => k);
}}

// trendKey의 윈도우 내 최신 메타 반환 (가장 늦은 날짜의 값)
function latestMeta(tk, windowDates) {{
  for (let i = windowDates.length - 1; i >= 0; i--) {{
    const d = windowDates[i];
    if (allMetaMap[d] && allMetaMap[d][tk]) return allMetaMap[d][tk];
  }}
  return null;
}}

// 미니 스파크라인 SVG (검색형=검색량 추이 / 시의형=뉴스건수 추이)
function sparkSVG(values, color) {{
  const w = 90, h = 24;
  // 데이터 있는 날만 점으로 사용 (없는 날을 0으로 채우면 마지막 하루만 솟는 '절벽'이 됨)
  const valid = values.map((v, i) => ({{ v, i }})).filter(o => o.v != null);
  if (valid.length === 0) return `<span class="spark-empty">—</span>`;
  const nums = valid.map(o => o.v);
  const mx = Math.max(...nums), mn = Math.min(...nums), n = values.length;
  const xy = o => `${{(o.i / (n - 1 || 1)) * w}},${{h - ((o.v - mn) / (mx - mn || 1)) * (h - 4) - 2}}`;
  if (valid.length === 1) {{
    const [cx, cy] = xy(valid[0]).split(",");
    return `<svg class="spark" width="${{w}}" height="${{h}}"><circle cx="${{cx}}" cy="${{cy}}" r="2.2" fill="${{color}}"/></svg>`;
  }}
  const pts = valid.map(xy).join(" ");
  return `<svg class="spark" width="${{w}}" height="${{h}}"><polyline points="${{pts}}" fill="none" stroke="${{color}}" stroke-width="1.8"/></svg>`;
}}

// ── 추이 날짜 네비게이션 ──
function trendNavigate(delta) {{
  // 윈도우 끝(trendWindowEnd)을 [최소끝, 마지막날] 범위로 제한해서
  // 과거로 가도 항상 14일 폭이 유지되도록 함 (끝에서 줄어들지 않게)
  const WINDOW_DAYS = 14;
  const minEnd = Math.min(allDates.length - 1, WINDOW_DAYS - 1);
  let newEnd = trendWindowEnd + delta;
  if (newEnd < minEnd) newEnd = minEnd;
  if (newEnd > allDates.length - 1) newEnd = allDates.length - 1;
  if (newEnd !== trendWindowEnd) {{
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
  // 가장 오래된 14일 윈도우(winStart=0)에 닿으면 prev 비활성화
  const prevDisabled = (winStart <= 0);
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
    document.getElementById("leaderboard").innerHTML =
      '<div class="empty">이 기간에 2일 이상 등장한 키워드가 없습니다. (데이터가 며칠 더 쌓이면 채워집니다)</div>';
    document.getElementById("trendInfo").textContent = "";
  }} else {{
  // ── 지속 리더보드 (월검색량 많은 순, 동률은 등장일수순) ──
  // 검색량 없는 키워드(시의형 등)는 맨 뒤로
  const svOf = (tk) => {{
    const m = latestMeta(tk, windowDates) || {{}};
    return (m.search_volume != null) ? m.search_volume : -1;
  }};
  const ranked = windowKeys.slice().sort((a, b) => {{
    const dv = svOf(b) - svOf(a);
    if (dv !== 0) return dv;
    return (allKeyCount[b] || 0) - (allKeyCount[a] || 0);
  }});
  let lbHtml = "";
  ranked.forEach((tk, i) => {{
    const meta = latestMeta(tk, windowDates) || {{}};
    const isNews = meta.track === "시의형";
    const trkCls = isNews ? "n" : "s";
    const col = isNews ? "#f0883e" : "#58a6ff";
    const days = allKeyCount[tk] || 0;

    // 연속(윈도우 내) 점 표시
    let streak = "";
    windowDates.forEach(d => {{
      const on = allDateMap[d] && allDateMap[d][tk];
      streak += on ? `<span class="on-${{trkCls}}">●</span>` : `<span class="off">·</span>`;
    }});

    // 스파크라인: 검색형=검색량 / 시의형=뉴스건수
    const series = windowDates.map(d => {{
      const m = allMetaMap[d] && allMetaMap[d][tk];
      if (isNews) return (allNewsCountMap[d] && allNewsCountMap[d][tk] != null) ? allNewsCountMap[d][tk] : null;
      return (m && m.search_volume != null) ? m.search_volume : null;
    }});

    // 메타 텍스트
    let metaTxt;
    if (isNews) {{
      const nh = meta.newest_hours;
      const fresh = (nh == null) ? "-" : (nh < 24 ? `${{Math.round(nh)}}h 전` : `${{Math.round(nh/24)}}일 전`);
      metaTxt = `시의 <b>${{meta.score != null ? meta.score : "-"}}</b> · 최신 ${{fresh}}`;
    }} else {{
      const sv = meta.search_volume;
      const gold = (meta.opportunity_label || "").includes("황금") ? '<span class="gold">💎</span> ' : "";
      metaTxt = `${{gold}}월검색 <b>${{sv != null ? sv.toLocaleString() : "-"}}</b> · 기회 ${{meta.score != null ? meta.score : "-"}}`;
    }}

    lbHtml += `<div class="lead-card">
      <div class="lead-top">
        <span class="lead-rank">${{i + 1}}</span>
        <span class="lead-name" title="${{escHtml(tk)}}">${{escHtml(tk)}}</span>
        <span class="trk ${{trkCls}}">${{isNews ? "시의형" : "검색형"}}</span>
      </div>
      <div class="lead-bottom">
        <span class="streak">${{streak}} <b>${{days}}일</b></span>
        ${{sparkSVG(series, col)}}
        <span class="lead-meta">${{metaTxt}}</span>
      </div>
    </div>`;
  }});
  document.getElementById("leaderboard").innerHTML = lbHtml;
  document.getElementById("trendInfo").textContent =
    `전체 ${{allDates.length}}일 중 ${{windowDates.length}}일 · 2일 이상 등장 ${{ranked.length}}개`;
  }}

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

  // 뉴스 건수(최대값) 많은 순으로 정렬 → 범례/색 순서가 큰 것부터 작은 것 순으로 정돈
  const highKeys = newsKeysAll.filter(tk => getMaxNews(tk) >= NEWS_SPLIT)
    .sort((a, b) => getMaxNews(b) - getMaxNews(a));
  const lowKeys = newsKeysAll.filter(tk => getMaxNews(tk) < NEWS_SPLIT)
    .sort((a, b) => getMaxNews(b) - getMaxNews(a));

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
        tooltip: {{
          // 마우스 올린 그 날짜의 실제 건수 기준으로 내림차순 정렬
          itemSort: function(a, b) {{ return (b.parsed.y || 0) - (a.parsed.y || 0); }},
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
