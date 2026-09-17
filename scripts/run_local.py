#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""미니PC 로컬 실행기 (2026-09-17). 작업 스케줄러 Auto_TrendScan 이 하루 2회(08:00·20:00) 부른다.

왜 로컬인가: AI 분석을 구독제 Claude Code CLI(Opus)로 돌려 API 과금을 없애고, 집 IP 라서 실제 네이버 검색 화면도 같이 확인한다.
GitHub Actions 의 자동 스케줄은 껐다(scan_v2.yml 은 수동 실행 + API 폴백용으로만 남김).

순서: git pull → collect_v2.py → build_dashboard_v2.py → data/·docs/ 커밋 → push.
실패하면 텔레그램으로 알린다 — 예전에 조용히 실패해 한 달(04-09~05-07) 동안 몰랐던 적이 있고, 로컬 실행은 GitHub 실패 메일도 안 온다.
비밀값은 저장소에 두지 않는다: 네이버 키는 이 폴더의 .env(.gitignore), GitHub 토큰·텔레그램은 video-auto 의 .env.local 을 읽는다.
"""
import base64
import os
import re
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_ENV = os.environ.get("SHARED_ENV", r"C:\auto\video-auto\.env.local")
LOG = os.path.join(BASE, "run_local.log")


def read_env(path):
    out = {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                m = re.match(r"\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
                if m:
                    out[m.group(1)] = m.group(2).strip('"')
    except OSError:
        pass
    return out


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run(args, env=None, timeout=3600):
    p = subprocess.run(args, cwd=BASE, env=env, capture_output=True, timeout=timeout)
    out = (p.stdout + p.stderr).decode("utf-8", errors="replace")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(out[-6000:] + "\n")
    return p.returncode, out


def notify(shared, text):
    token, chat = shared.get("TELEGRAM_BOT_TOKEN"), shared.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    try:
        import requests
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text[:3500]}, timeout=15)
    except Exception:
        pass


def main():
    shared = read_env(SHARED_ENV)
    env = {**os.environ, **read_env(os.path.join(BASE, ".env")), "PYTHONIOENCODING": "utf-8",
           "SERP_CHECK_DIR": os.environ.get("SERP_CHECK_DIR", r"C:\auto\video-auto")}
    gh = shared.get("INFLOW_GITHUB_TOKEN", "")
    auth = ["-c", "http.extraheader=AUTHORIZATION: basic " + base64.b64encode(f"x-access-token:{gh}".encode()).decode()] if gh else []
    dry = "--no-push" in sys.argv

    log("=== 트렌드 스캔 시작 ===")
    code, out = run(["git", *auth, "pull", "--rebase", "--autostash"])
    if code != 0:
        log("git pull 실패 — 그대로 진행")

    code, out = run([sys.executable, "scripts/collect_v2.py"], env=env)
    if code != 0:
        tail = "\n".join(out.strip().splitlines()[-6:])
        log("collect_v2 실패")
        notify(shared, f"⚠️ 트렌드 스캐너 실패(미니PC) — 수집/AI 단계\n{tail}")
        return 1
    code, out2 = run([sys.executable, "scripts/build_dashboard_v2.py"], env=env)
    if code != 0:
        log("대시보드 빌드 실패")
        notify(shared, "⚠️ 트렌드 스캐너: 대시보드 빌드 실패(데이터는 저장됨)")

    m = re.search(r"실제 검색어에 붙은 글감: (\d+)/(\d+)", out)
    log("수집 완료" + (f" · 실제 검색어에 붙은 글감 {m.group(1)}/{m.group(2)}" if m else ""))
    if dry:
        log("--no-push: 커밋·push 생략")
        return 0

    run(["git", "add", "data", "docs"])
    code, _ = run(["git", "-c", "user.name=trend-scanner(minipc)", "-c", "user.email=trend-scanner@users.noreply.github.com",
                   "commit", "-m", f"scan v2(local): {datetime.now():%Y-%m-%d %H:%M}"])
    for attempt in range(3):
        code, out3 = run(["git", *auth, "push"])
        if code == 0:
            log("push 완료")
            return 0
        run(["git", *auth, "pull", "--rebase", "--autostash"])
    log("push 실패")
    notify(shared, "⚠️ 트렌드 스캐너: 스캔은 됐는데 GitHub push 실패(미니PC)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
