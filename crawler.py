import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from pathlib import Path

# ── 경로 설정
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
SEEN_PATH   = BASE_DIR / "seen_posts.json"
POSTS_PATH  = BASE_DIR / "docs" / "posts.json"
OUTPUT_PATH = BASE_DIR / "docs" / "index.html"

KST = timezone(timedelta(hours=9))

KAKAO_REST_API_KEY = "6faa56f775c540ab4b7f57a364d82e49"


# ── 설정 로드
def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)

def load_seen():
    if SEEN_PATH.exists():
        with open(SEEN_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_seen(seen):
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


# ── 카카오 토큰 자동 갱신
def refresh_kakao_token(refresh_token: str) -> str | None:
    """refresh_token으로 새 access_token 발급"""
    try:
        res = requests.post(
            "https://kauth.kakao.com/oauth/token",
            data={
                "grant_type": "refresh_token",
                "client_id": KAKAO_REST_API_KEY,
                "refresh_token": refresh_token,
            },
            timeout=10,
        )
        data = res.json()
        if "access_token" in data:
            new_token = data["access_token"]
            print(f"[KAKAO] 토큰 갱신 성공")

            # GitHub Actions 환경에서 새 토큰을 환경변수에 반영
            # (실제 Secret 업데이트는 GitHub API로 별도 처리)
            # refresh_token이 새로 발급된 경우 저장
            if "refresh_token" in data:
                print(f"[KAKAO] refresh_token 도 새로 발급됨 — Secrets 업데이트 필요")

            return new_token
        else:
            print(f"[KAKAO] 토큰 갱신 실패: {data}")
            return None
    except Exception as e:
        print(f"[KAKAO] 토큰 갱신 오류: {e}")
        return None


def get_valid_kakao_token() -> str:
    """유효한 access_token 반환 (만료 시 refresh_token으로 갱신)"""
    access_token  = os.environ.get("KAKAO_TOKEN", "")
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "")

    if not access_token and not refresh_token:
        print("[KAKAO] 토큰 없음 — Secrets에 KAKAO_TOKEN, KAKAO_REFRESH_TOKEN 설정 필요")
        return ""

    # 토큰 유효성 체크
    if access_token:
        res = requests.get(
            "https://kapi.kakao.com/v1/user/access_token_info",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if res.status_code == 200:
            info = res.json()
            expires_in = info.get("expires_in", 0)
            print(f"[KAKAO] 토큰 유효 (만료까지 {expires_in}초)")
            return access_token
        else:
            print(f"[KAKAO] 토큰 만료 또는 무효 ({res.status_code}) — refresh 시도")

    # refresh_token으로 갱신
    if refresh_token:
        new_token = refresh_kakao_token(refresh_token)
        if new_token:
            return new_token

    print("[KAKAO] 유효한 토큰을 가져올 수 없음")
    return ""


# ── 크롤링
def fetch_posts(source: dict) -> list[dict]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(source["url"], headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        posts = []
        rows = soup.select("table.board-list tbody tr, ul.board-list li, .board-list-wrap .item")
        if not rows:
            rows = soup.select("tr[class*='list'], .listArea tr, tbody tr")

        for row in rows:
            title_el = (
                row.select_one("td.subject a, td.title a, .title a, a.subject")
                or row.select_one("td:nth-child(2) a, td:nth-child(3) a")
            )
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title:
                continue

            href = title_el.get("href", "")
            if href.startswith("/"):
                href = "https://www.hongik.ac.kr" + href
            elif not href.startswith("http"):
                href = source["url"].split("?")[0] + href

            date_el = row.select_one("td.date, td.reg-date, .date, td:last-child")
            date_str = date_el.get_text(strip=True) if date_el else ""

            post_id = hashlib.md5(f"{source['id']}::{title}".encode()).hexdigest()[:12]
            posts.append({
                "id": post_id,
                "source_id": source["id"],
                "source_name": source["name"],
                "title": title,
                "url": href,
                "date": date_str,
            })

        return posts[:20]
    except Exception as e:
        print(f"[ERROR] {source['name']} 크롤링 실패: {e}")
        return []


# ── 키워드 매칭
def match_keywords(title: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if kw in title]


# ── 카카오톡 전송
def send_kakao(token: str, message: str):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": message,
            "link": {
                "web_url": "https://areumjin.github.io/hongik-monitor",
                "mobile_web_url": "https://areumjin.github.io/hongik-monitor"
            },
        })
    }
    try:
        res = requests.post(url, headers=headers, data=data, timeout=10)
        if res.status_code == 200:
            print(f"[KAKAO] 전송 성공 ✓")
        else:
            print(f"[KAKAO] 전송 실패: {res.status_code} {res.text}")
    except Exception as e:
        print(f"[KAKAO] 오류: {e}")


# ── HTML 생성 (기존 유지)
def generate_html(all_posts, keywords, sources):
    now = datetime.now(KST).strftime("%Y.%m.%d %H:%M")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # docs/index.html은 대시보드 전용이라 덮어쓰지 않음
    print(f"[HTML] 스킵 (대시보드 전용 index.html 유지)")


# ── 메인
def main():
    config   = load_config()
    seen     = load_seen()

    # 유효한 카카오 토큰 가져오기 (자동 갱신 포함)
    kakao_token = get_valid_kakao_token()

    all_posts     = []
    new_posts     = []
    keyword_posts = []

    for source in config["sources"]:
        if not source.get("enabled", True):
            continue
        posts = fetch_posts(source)
        all_posts.extend(posts)
        print(f"[{source['name']}] {len(posts)}개 수집")

        for post in posts:
            is_new = post["id"] not in seen.get(source["id"], [])
            if is_new:
                new_posts.append(post)
                matched = match_keywords(post["title"], config["keywords"])
                if matched:
                    keyword_posts.append((post, matched))

    # seen 업데이트
    for source in config["sources"]:
        sid = source["id"]
        existing = set(seen.get(sid, []))
        for post in all_posts:
            if post["source_id"] == sid:
                existing.add(post["id"])
        seen[sid] = list(existing)[-200:]
    save_seen(seen)

    # 카카오 알림
    if kakao_token and keyword_posts:
        limit = config.get("kakao_message_limit", 5)
        msgs = []
        for post, matched in keyword_posts[:limit]:
            kw_str = " · ".join(matched)
            msgs.append(f"🔔 [{post['source_name']}] {kw_str}\n{post['title']}\n{post['url']}")
        full_msg = f"📌 홍익대 공지 키워드 알림\n{'─' * 20}\n\n" + "\n\n".join(msgs)
        send_kakao(kakao_token, full_msg)
        print(f"[KAKAO] {len(keyword_posts)}개 키워드 게시물 알림 전송")
    elif not kakao_token:
        print("[KAKAO] 토큰 없음 — 알림 생략")
    else:
        print("[KAKAO] 키워드 매칭 없음")

    print(f"\n신규: {len(new_posts)}개 / 키워드 매칭: {len(keyword_posts)}개")

    # posts.json 저장
    POSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(KST).strftime("%Y.%m.%d %H:%M")
    with open(POSTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"updated": now_str, "posts": all_posts}, f, ensure_ascii=False, indent=2)
    print(f"[JSON] posts.json 저장 완료 ({len(all_posts)}개)")

    generate_html(all_posts, config["keywords"], config["sources"])


if __name__ == "__main__":
    main()
