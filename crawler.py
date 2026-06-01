import os
import json
import hashlib
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
from pathlib import Path

# ── 경로 설정 ────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
SEEN_PATH = BASE_DIR / "seen_posts.json"
OUTPUT_PATH = BASE_DIR / "docs" / "index.html"

KST = timezone(timedelta(hours=9))


# ── 설정 로드 ────────────────────────────────────────────────
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


# ── 크롤링 ───────────────────────────────────────────────────
def fetch_posts(source: dict) -> list[dict]:
    """사이트별 게시물 크롤링"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        res = requests.get(source["url"], headers=headers, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        posts = []

        # 홍익대 공통 게시판 구조
        rows = soup.select("table.board-list tbody tr, ul.board-list li, .board-list-wrap .item")

        if not rows:
            # 대체 셀렉터 시도
            rows = soup.select("tr[class*='list'], .listArea tr, tbody tr")

        for row in rows:
            # 제목 추출
            title_el = (
                row.select_one("td.subject a, td.title a, .title a, a.subject")
                or row.select_one("td:nth-child(2) a, td:nth-child(3) a")
            )
            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            if not title or title in ("", " "):
                continue

            # 링크 추출
            href = title_el.get("href", "")
            if href.startswith("/"):
                href = "https://www.hongik.ac.kr" + href
            elif not href.startswith("http"):
                href = source["url"].split("?")[0] + href

            # 날짜 추출
            date_el = row.select_one("td.date, td.reg-date, .date, td:last-child")
            date_str = date_el.get_text(strip=True) if date_el else ""

            # 고유 ID 생성
            post_id = hashlib.md5(f"{source['id']}::{title}".encode()).hexdigest()[:12]

            posts.append({
                "id": post_id,
                "source_id": source["id"],
                "source_name": source["name"],
                "title": title,
                "url": href,
                "date": date_str,
            })

        return posts[:20]  # 최신 20개만

    except Exception as e:
        print(f"[ERROR] {source['name']} 크롤링 실패: {e}")
        return []


# ── 키워드 매칭 ──────────────────────────────────────────────
def match_keywords(title: str, keywords: list[str]) -> list[str]:
    return [kw for kw in keywords if kw in title]


# ── 카카오톡 알림 ────────────────────────────────────────────
def send_kakao(token: str, message: str):
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": f"Bearer {token}"}
    data = {
        "template_object": json.dumps({
            "object_type": "text",
            "text": message,
            "link": {"web_url": "https://www.hongik.ac.kr", "mobile_web_url": "https://www.hongik.ac.kr"},
        })
    }
    try:
        res = requests.post(url, headers=headers, data=data, timeout=10)
        if res.status_code == 200:
            print(f"[KAKAO] 전송 성공")
        else:
            print(f"[KAKAO] 전송 실패: {res.status_code} {res.text}")
    except Exception as e:
        print(f"[KAKAO] 오류: {e}")


# ── HTML 대시보드 생성 ───────────────────────────────────────
def generate_html(all_posts: list[dict], keywords: list[str], sources: list[dict]):
    now = datetime.now(KST).strftime("%Y.%m.%d %H:%M")

    source_tabs = ""
    for s in sources:
        if s["enabled"]:
            source_tabs += f'<button class="tab-btn" data-source="{s["id"]}">{s["name"]}</button>\n'

    cards_html = ""
    for post in all_posts:
        matched = match_keywords(post["title"], keywords)
        keyword_badges = "".join(
            f'<span class="badge">{kw}</span>' for kw in matched
        )
        highlight_class = "highlight" if matched else ""

        cards_html += f"""
        <article class="card {highlight_class}" data-source="{post['source_id']}">
            <div class="card-meta">
                <span class="source-tag">{post['source_name']}</span>
                <span class="date">{post['date']}</span>
            </div>
            <a class="card-title" href="{post['url']}" target="_blank" rel="noopener">
                {post['title']}
            </a>
            {f'<div class="badges">{keyword_badges}</div>' if keyword_badges else ''}
        </article>
        """

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>홍익대 공지 모니터</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Pretendard:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0a0f;
    --surface: #13131a;
    --surface2: #1c1c26;
    --border: #2a2a38;
    --accent: #6c63ff;
    --accent2: #ff6584;
    --text: #e8e8f0;
    --text-muted: #6b6b80;
    --keyword: #ffd166;
    --radius: 12px;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Pretendard', -apple-system, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }}

  /* 헤더 */
  header {{
    padding: 2.5rem 2rem 1.5rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
  }}

  .logo {{
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }}

  .logo-dot {{
    width: 10px; height: 10px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 12px var(--accent);
    animation: pulse 2s infinite;
  }}

  @keyframes pulse {{
    0%, 100% {{ opacity: 1; box-shadow: 0 0 12px var(--accent); }}
    50% {{ opacity: 0.6; box-shadow: 0 0 24px var(--accent); }}
  }}

  h1 {{
    font-size: 1.35rem;
    font-weight: 700;
    letter-spacing: -0.03em;
    color: var(--text);
  }}

  .updated {{
    font-size: 0.75rem;
    color: var(--text-muted);
    letter-spacing: 0.02em;
  }}

  /* 탭 */
  .tabs {{
    display: flex;
    gap: 0.5rem;
    padding: 1.25rem 2rem;
    border-bottom: 1px solid var(--border);
    overflow-x: auto;
  }}

  .tab-btn {{
    background: none;
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 0.45rem 1rem;
    border-radius: 99px;
    font-family: inherit;
    font-size: 0.82rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    white-space: nowrap;
  }}

  .tab-btn:hover {{
    border-color: var(--accent);
    color: var(--text);
  }}

  .tab-btn.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: #fff;
  }}

  /* 키워드 필터 */
  .filters {{
    display: flex;
    gap: 0.5rem;
    padding: 1rem 2rem;
    align-items: center;
    flex-wrap: wrap;
  }}

  .filter-label {{
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-right: 0.25rem;
  }}

  .filter-btn {{
    background: none;
    border: 1px solid var(--border);
    color: var(--text-muted);
    padding: 0.3rem 0.75rem;
    border-radius: 99px;
    font-family: inherit;
    font-size: 0.78rem;
    cursor: pointer;
    transition: all 0.2s;
  }}

  .filter-btn.active {{
    background: var(--keyword);
    border-color: var(--keyword);
    color: #0a0a0f;
    font-weight: 600;
  }}

  /* 카드 목록 */
  .posts {{
    padding: 1rem 2rem 3rem;
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
    max-width: 900px;
  }}

  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem;
    transition: all 0.2s;
  }}

  .card:hover {{
    border-color: var(--accent);
    background: var(--surface2);
    transform: translateX(4px);
  }}

  .card.highlight {{
    border-left: 3px solid var(--keyword);
    background: color-mix(in srgb, var(--keyword) 5%, var(--surface));
  }}

  .card-meta {{
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.45rem;
  }}

  .source-tag {{
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--accent);
    background: color-mix(in srgb, var(--accent) 15%, transparent);
    padding: 0.15rem 0.55rem;
    border-radius: 99px;
    letter-spacing: 0.01em;
  }}

  .date {{
    font-size: 0.72rem;
    color: var(--text-muted);
  }}

  .card-title {{
    display: block;
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text);
    text-decoration: none;
    line-height: 1.5;
    letter-spacing: -0.01em;
  }}

  .card-title:hover {{
    color: var(--accent);
  }}

  .badges {{
    display: flex;
    gap: 0.4rem;
    margin-top: 0.5rem;
    flex-wrap: wrap;
  }}

  .badge {{
    font-size: 0.68rem;
    font-weight: 700;
    color: #0a0a0f;
    background: var(--keyword);
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    letter-spacing: 0.02em;
  }}

  /* 빈 상태 */
  .empty {{
    padding: 4rem 2rem;
    text-align: center;
    color: var(--text-muted);
    font-size: 0.9rem;
  }}

  /* 통계 바 */
  .stats {{
    display: flex;
    gap: 1.5rem;
    padding: 1rem 2rem;
    border-bottom: 1px solid var(--border);
  }}

  .stat {{
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }}

  .stat-num {{
    font-size: 1.4rem;
    font-weight: 700;
    letter-spacing: -0.04em;
    color: var(--text);
  }}

  .stat-label {{
    font-size: 0.7rem;
    color: var(--text-muted);
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }}

  @media (max-width: 600px) {{
    header, .tabs, .filters, .posts {{ padding-left: 1rem; padding-right: 1rem; }}
    h1 {{ font-size: 1.1rem; }}
  }}
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-dot"></div>
    <h1>홍익대 공지 모니터</h1>
  </div>
  <span class="updated">마지막 업데이트: {now}</span>
</header>

<div class="stats">
  <div class="stat">
    <span class="stat-num" id="total-count">{len(all_posts)}</span>
    <span class="stat-label">전체 게시물</span>
  </div>
  <div class="stat">
    <span class="stat-num" id="keyword-count" style="color: var(--keyword)">{sum(1 for p in all_posts if match_keywords(p['title'], keywords))}</span>
    <span class="stat-label">키워드 매칭</span>
  </div>
</div>

<div class="tabs">
  <button class="tab-btn active" data-source="all">전체</button>
  {source_tabs}
</div>

<div class="filters">
  <span class="filter-label">키워드</span>
  <button class="filter-btn active" data-keyword="all">전체</button>
  {"".join(f'<button class="filter-btn" data-keyword="{kw}">{kw}</button>' for kw in keywords)}
</div>

<div class="posts" id="posts-container">
  {cards_html if cards_html else '<div class="empty">게시물이 없습니다.</div>'}
</div>

<script>
  const cards = document.querySelectorAll('.card');
  let activeSource = 'all';
  let activeKeyword = 'all';

  function filterCards() {{
    let visible = 0;
    cards.forEach(card => {{
      const matchSource = activeSource === 'all' || card.dataset.source === activeSource;
      const matchKeyword = activeKeyword === 'all' || card.innerHTML.includes(activeKeyword);
      const show = matchSource && matchKeyword;
      card.style.display = show ? '' : 'none';
      if (show) visible++;
    }});
    document.getElementById('total-count').textContent = visible;
  }}

  document.querySelectorAll('.tab-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeSource = btn.dataset.source;
      filterCards();
    }});
  }});

  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeKeyword = btn.dataset.keyword;
      filterCards();
    }});
  }});
</script>

</body>
</html>"""

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[HTML] 대시보드 생성 완료: {OUTPUT_PATH}")


# ── 메인 ─────────────────────────────────────────────────────
def main():
    config = load_config()
    seen = load_seen()
    kakao_token = os.environ.get("KAKAO_TOKEN", "")

    all_posts = []
    new_posts = []
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
        seen[sid] = list(existing)[-200:]  # 최대 200개 유지
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
    else:
        if not kakao_token:
            print("[KAKAO] 토큰 없음 — 알림 생략")
        if not keyword_posts:
            print("[KAKAO] 키워드 매칭 없음")

    # 새 게시물 요약 출력
    print(f"\n신규: {len(new_posts)}개 / 키워드 매칭: {len(keyword_posts)}개")

    # HTML 생성
    generate_html(all_posts, config["keywords"], config["sources"])


if __name__ == "__main__":
    main()
