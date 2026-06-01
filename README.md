# 홍익대 공지 모니터

매일 자동으로 홍익대 공지사항을 크롤링하고, 키워드 매칭 시 카카오톡으로 알림을 보냅니다.

---

## 파일 구조

```
hongik-monitor/
├── config.json                  ← URL, 키워드 설정
├── crawler.py                   ← 크롤러 메인 스크립트
├── seen_posts.json              ← 이미 본 게시물 기록 (자동 생성)
├── requirements.txt
├── docs/
│   └── index.html               ← 대시보드 (GitHub Pages)
└── .github/workflows/
    └── monitor.yml              ← 자동 실행 스케줄
```

---

## 세팅 방법

### 1. GitHub 레포지토리 생성

1. GitHub에서 새 레포지토리 생성 (이름 예: `hongik-monitor`)
2. 이 파일들 모두 업로드

### 2. 카카오 API 토큰 발급

1. [카카오 개발자 콘솔](https://developers.kakao.com) 접속
2. 내 애플리케이션 → 앱 만들기
3. 앱 이름 입력 후 생성
4. **앱 키 → REST API 키** 복사
5. [카카오 로그인 테스트](https://kauth.kakao.com/oauth/authorize?client_id=REST_API_키&redirect_uri=https://example.com/oauth&response_type=code) 로 code 발급
6. 아래 명령으로 access_token 발급:

```bash
curl -X POST https://kauth.kakao.com/oauth/token \
  -d "grant_type=authorization_code" \
  -d "client_id=REST_API_키" \
  -d "redirect_uri=https://example.com/oauth" \
  -d "code=발급받은_code"
```

> 반환된 JSON에서 `access_token` 값 복사

### 3. GitHub Secrets 설정

1. 레포지토리 → Settings → Secrets and variables → Actions
2. **New repository secret** 클릭
3. Name: `KAKAO_TOKEN`, Value: 발급받은 액세스 토큰

### 4. GitHub Pages 활성화

1. 레포지토리 → Settings → Pages
2. Source: `Deploy from a branch`
3. Branch: `main`, Folder: `/docs`
4. Save

→ `https://[깃허브아이디].github.io/hongik-monitor` 에서 대시보드 확인

---

## URL 추가 방법

`config.json` 의 `sources` 배열에 추가:

```json
{
  "id": "scholarship",
  "name": "장학 공지",
  "url": "https://www.hongik.ac.kr/...",
  "enabled": true
}
```

## 키워드 추가/삭제

`config.json` 의 `keywords` 배열 수정:

```json
"keywords": ["창업", "지원금", "장학금", "공모전"]
```

## 수동 실행

GitHub → Actions 탭 → `홍익대 공지 모니터링` → **Run workflow**
