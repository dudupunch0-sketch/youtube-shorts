# YouTube 게시·운영 레이어 설계

렌더가 끝난 MP4를 실제 YouTube Shorts로 올리고 운영하는 단계의 설계 문서다. 구현 전
합의용이며, 결정되지 않은 항목은 마지막 절에 모아 둔다.

## 1. 범위

포함한다.

- 에피소드 산출물에서 게시 메타데이터(제목·설명·태그·카테고리) 생성
- 미디어 manifest의 승인된 자산에서 출처 표기 블록 자동 생성
- AI 합성 음성 고지의 설명문 삽입과 API 필드 선언
- 게시 전 사람 검토 시트와 승인 게이트
- 업로드, 예약 공개, 게시 후 지표 수집

포함하지 않는다.

- 대본·미디어·TTS·렌더 (기존 파이프라인이 담당한다)
- 썸네일 디자인 자동 생성 (Shorts는 커버 프레임을 쓰므로 후순위, 8절 참고)
- 댓글 자동 응답 (사람 판단 영역으로 남긴다)

## 2. 설계 원칙

기존 파이프라인의 규약을 그대로 승계한다.

- **manifest가 단일 진실**이다. 각 단계는 `output/manifests/`에 JSON을 쓰고, 다음 단계는
  그 JSON만 읽는다.
- **자동 승인은 없다.** `plan_media.py`가 후보를 `needs_review`로 두는 것과 같이,
  `plan_publish.py`도 게시 계획을 `needs_review`로 만든다. 사람이 명시적으로 승인해야
  업로드가 가능하다.
- **draft와 final을 분리한다.** `render_short.py --draft`와 같은 구조로, 업로드는 항상
  `private`으로 먼저 올라가고, 공개 전환은 별도 명령이다.
- **검증기를 따로 둔다.** `validate_*.py` 관례를 따라 `validate_publish.py`가 게시
  직전의 모든 조건을 검사한다.
- **비밀은 Git에 넣지 않는다.** `config/local/elevenlabs-tts.json` 방식을 따른다.

## 3. 파이프라인

```text
output/video/<episode_id>.mp4  (final render, draft 아님)
output/manifests/<episode_id>.render.json
output/manifests/<episode_id>.media.json
output/episodes/<episode_id>.json
  ↓  scripts/plan_publish.py
output/manifests/<episode_id>.publish.json      (review.status = needs_review)
  ↓  scripts/render_publish_review.py
output/manifests/<episode_id>.publish-review.md (사람 검토 시트)
  ↓  사람 검토 → scripts/approve_publish.py
output/manifests/<episode_id>.publish.json      (review.status = approved)
  ↓  scripts/validate_publish.py                (게이트, 네트워크 없음)
  ↓  scripts/upload_youtube.py --confirm        (privacyStatus=private 고정)
output/manifests/<episode_id>.publish.json      (upload.video_id 기록)
  ↓  scripts/promote_youtube.py                 (public 또는 publishAt 예약)
  ↓  scripts/fetch_youtube_stats.py             (운영 단계, 반복 실행)
output/manifests/<episode_id>.stats.json
```

`upload_youtube.py`까지는 되돌릴 수 있고(비공개 업로드), `promote_youtube.py`가 유일한
비가역 단계다. 그래서 승인 게이트를 두 번 통과하게 만든다.

## 4. publish manifest 스키마

`output/manifests/<episode_id>.publish.json`, `manifest_version: 1`.

```json
{
  "manifest_version": 1,
  "episode_id": "phantom-clefairy-shadow",
  "episode_path": "output/episodes/phantom-clefairy-shadow.json",
  "media_manifest": "output/manifests/phantom-clefairy-shadow.media.json",
  "render_report": "output/manifests/phantom-clefairy-shadow.render.json",
  "video_path": "output/video/phantom-clefairy-shadow.mp4",
  "generated_at": "2026-08-13T00:00:00+00:00",
  "publish_profile": "korean-shorts",

  "metadata": {
    "title": "팬텀은 사실 삐삐의 그림자일까?",
    "title_candidates": ["...", "..."],
    "description": "<조립된 최종 설명문>",
    "description_blocks": {
      "hook": "...",
      "body": "...",
      "ai_disclosure": "...",
      "attribution": "...",
      "interpretation_notice": "...",
      "footer": "..."
    },
    "tags": ["포켓몬", "팬텀", "삐삐"],
    "category_id": "24",
    "default_language": "ko",
    "default_audio_language": "ko"
  },

  "status": {
    "privacy_status": "private",
    "publish_at": null,
    "self_declared_made_for_kids": false,
    "contains_synthetic_media": true,
    "license": "youtube",
    "embeddable": true
  },

  "attribution": [
    {
      "segment": 8,
      "candidate_id": "cand-3a4c7f337811",
      "source_url": "...",
      "landing_url": "...",
      "license": "CC BY-NC-SA 2.0 KR",
      "creator": "...",
      "line": "장면 8: <title> — <creator>, <license> (<landing_url>)",
      "commercial_use_allowed": false
    }
  ],

  "claim_summary": {
    "official": 6,
    "secondary_reference": 5,
    "creative_interpretation": 4
  },

  "review": {
    "status": "needs_review",
    "approved_by": null,
    "approved_at": null,
    "notes": []
  },

  "checks": {
    "validated_at": null,
    "passed": null,
    "failures": [],
    "warnings": []
  },

  "upload": {
    "state": "not_uploaded",
    "video_id": null,
    "uploaded_at": null,
    "promoted_at": null,
    "attempts": []
  }
}
```

`upload.state`는 `not_uploaded` → `uploading` → `uploaded` → `promoted`로만 전이한다.
`uploaded` 이후 `upload_youtube.py`를 다시 실행하면 중복 게시를 막기 위해 즉시 실패한다.
재업로드가 필요하면 `--allow-reupload`로 명시하고 이전 `video_id`를 `attempts`에 남긴다.

## 5. 스크립트별 책임

| 스크립트 | 입력 | 출력 | 네트워크 |
|---|---|---|---|
| `scripts/plan_publish.py` | episode, media, render manifest | `*.publish.json` | 없음 |
| `scripts/render_publish_review.py` | `*.publish.json` | `*.publish-review.md` | 없음 |
| `scripts/approve_publish.py` | `*.publish.json` | 같은 파일 갱신 | 없음 |
| `scripts/validate_publish.py` | `*.publish.json` | 종료 코드 + `checks` 갱신 | 없음 |
| `scripts/authorize_youtube.py` | OAuth client secrets | 로컬 토큰 파일 | 있음 |
| `scripts/upload_youtube.py` | `*.publish.json` | `upload.video_id` 기록 | 있음 |
| `scripts/promote_youtube.py` | `*.publish.json` | `upload.promoted_at` 기록 | 있음 |
| `scripts/fetch_youtube_stats.py` | `*.publish.json` | `*.stats.json` | 있음 |

앞의 네 개는 네트워크와 자격 증명이 필요 없어서 `make test`로 전부 검증할 수 있다.
이것이 구현 순서를 정하는 기준이다(10절).

### 5.1 plan_publish.py

- 제목은 `episode.title`을 기본값으로 쓰고, 100자를 넘으면 자르지 않고 실패시킨다.
  대안 후보는 `title_candidates`에 남겨 사람이 고르게 한다.
- 설명문은 블록을 조립한다. 순서는 훅 → 본문 요약 → AI 음성 고지 → 해석 표기 → 출처
  목록 → 고정 푸터다. 사람이 `config/publish/<episode_id>.json`으로 블록을 override할 수
  있게 한다(`config/presentation/` 방식과 동일).
- 출처 목록은 media manifest에서 **각 장면이 실제로 선택한 자산**만 읽는다. 후보 전체를
  긁지 않는다. 선택 자산은 `segments[].asset` / `segments[].visual`을 따른다.
- `claim_summary`는 episode의 `claim_type` 분포를 집계한다. `creative_interpretation`이
  하나라도 있으면 해석 표기 블록을 필수로 넣는다. 이는 "해석을 공식 사실처럼 포장하지
  않는다"는 콘텐츠 원칙의 게시 단계 구현이다.
- 태그는 자동 생성하지 않고 `config/publish/`의 프로필 태그 + 에피소드 override만 쓴다.
  키워드 추측이 잘못된 태그를 만드는 것보다 비어 있는 편이 낫다.

### 5.2 upload_youtube.py

- 기본은 dry-run이다. 실제 업로드는 `--confirm`이 필요하다.
- `privacyStatus`는 항상 `private`으로 고정한다. CLI로 `public`을 지정할 수 없게 한다.
- `MediaFileUpload`의 resumable 업로드를 쓰고, 재시도는 지수 백오프로 한다. 중간 실패
  시에도 `attempts`에 시각과 오류를 남긴다.
- 업로드 직전 `validate_publish.py`와 같은 검증 함수를 다시 호출한다. 검증과 업로드
  사이에 manifest가 바뀌는 경우를 막는다.

## 6. 설정과 인증

### 6.1 config/pipeline.json에 추가할 블록

```json
"publish": {
  "platform": "youtube",
  "default_profile": "korean-shorts",
  "upload_privacy_status": "private",
  "require_manual_approval": true,
  "require_final_render": true,
  "commercial_use": true,
  "profiles": {
    "korean-shorts": {
      "category_id": "24",
      "default_language": "ko",
      "default_audio_language": "ko",
      "made_for_kids": false,
      "contains_synthetic_media": true,
      "base_tags": [],
      "footer": ""
    }
  },
  "limits": {
    "title_max_chars": 100,
    "description_max_bytes": 5000,
    "tags_max_total_chars": 500,
    "shorts_max_duration_seconds": 180
  },
  "license_policy": {
    "allow": ["CC0", "CC BY", "CC BY-SA", "public_domain", "own_work"],
    "block": ["unknown"],
    "require_review": ["CC BY-NC", "CC BY-NC-SA", "CC BY-ND", "fair_use_claim"]
  },
  "ai_disclosure": {
    "required": true,
    "api_field": "status.containsSyntheticMedia",
    "description_sentence_ko": "이 영상의 내레이션은 AI 음성으로 생성되었습니다."
  },
  "scripts": {
    "planner": "scripts/plan_publish.py",
    "review_report": "scripts/render_publish_review.py",
    "approval": "scripts/approve_publish.py",
    "validator": "scripts/validate_publish.py",
    "uploader": "scripts/upload_youtube.py",
    "promoter": "scripts/promote_youtube.py",
    "stats": "scripts/fetch_youtube_stats.py"
  }
}
```

### 6.2 자격 증명

업로드는 API 키로 안 되고 OAuth 2.0 사용자 동의가 필요하다. 스코프는
`https://www.googleapis.com/auth/youtube.upload`과, 예약 전환·지표 조회를 위한
`https://www.googleapis.com/auth/youtube`이다.

- `config/local/youtube-oauth.json` — Google Cloud 데스크톱 앱 client secrets
- `config/local/youtube-token.json` — refresh token 저장소
- 둘 다 `.gitignore`에 추가한다. `config/local/youtube-oauth.json.example`만 커밋한다.

`.env.example`에 추가할 항목이다.

```text
YOUTUBE_OAUTH_CLIENT_SECRETS=config/local/youtube-oauth.json
YOUTUBE_OAUTH_TOKEN=config/local/youtube-token.json
YOUTUBE_PUBLISH_PROFILE=korean-shorts
YOUTUBE_CHANNEL_ID=
```

### 6.3 WSL에서의 OAuth

프로젝트는 WSL Ubuntu에서 실행하는데, WSL에는 기본 브라우저가 없다. 두 경로를 둔다.

1. 기본값: `127.0.0.1:8765`에 임시 loopback 서버를 띄우고 동의 URL을 표준출력에 찍는다.
   Windows 브라우저에 붙여 넣으면 WSL2의 localhost 포워딩으로 콜백이 돌아온다.
2. `--manual`: 콜백 없이 동의 후 표시되는 코드를 붙여 넣는다. 포워딩이 막힌 환경용이다.

`authorize_youtube.py`는 최초 1회만 실행하고, 이후에는 refresh token으로 갱신한다.

### 6.4 쿼터

`videos.insert`는 전용 쿼터 버킷을 쓰며 기본 하루 100회다. 공용 10,000 유닛 풀과
분리되어 있으므로 이 채널 규모에서 쿼터는 제약이 아니다. `videos.list`는 1 유닛,
`videos.update`와 `thumbnails.set`은 각 50 유닛이다. 지표 수집을 매일 돌려도 여유가 있다.

## 7. 검증 규칙

`validate_publish.py`가 검사한다. 하나라도 실패하면 업로드가 불가능하다.

**렌더 상태**

1. `render.json`이 존재하고 `draft`가 false다.
2. `duration_sec`이 50~70 범위이고, Shorts 한계인 180초 미만이다.
3. 해상도가 1080x1920이다.
4. `video_path`의 MP4가 존재하고 오디오 트랙이 유효하다.

**미디어 권리**

5. 모든 장면의 선택 자산이 `review_status: approved`다.
6. 선택 자산마다 `source_url`, `license`, `creator`가 채워져 있다.
   `pipeline.json`의 `required_attribution_fields`를 그대로 쓴다.
7. 라이선스가 `license_policy.block`에 있으면 실패한다. `unknown`은 차단 대상이다.
8. `require_review` 라이선스는 `attribution[].commercial_use_allowed`가 명시적으로
   기록되어 있어야 한다. `commercial_use: true`인데 NC 자료가 있으면 실패한다(9절).

**메타데이터**

9. 제목이 비어 있지 않고 100자 이하다.
10. 설명문이 5000 **바이트** 이하다. 문자 수가 아니라 UTF-8 바이트다. 한국어는 글자당
    3바이트이므로 실제 상한은 약 1,660자다. 이 구분을 놓치면 조용히 잘린다.
11. 태그 전체 길이가 쉼표·공백 포함 500자 이하다.
12. `category_id`가 유효한 값이다.
13. `default_language`와 `default_audio_language`가 채워져 있다.

**고지**

14. `status.contains_synthetic_media`가 true다. 내레이션이 Supertonic·Qwen·ElevenLabs
    중 무엇이든 합성 음성이므로 항상 true다.
15. 설명문에 AI 음성 고지 문장이 실제로 포함되어 있다. 필드 선언과 문장을 둘 다 검사한다.
16. `creative_interpretation` 장면이 있으면 해석 표기 블록이 설명문에 있다.

**게이트**

17. `review.status`가 `approved`이고 `approved_at`이 채워져 있다.
18. `upload.state`가 `uploaded`나 `promoted`가 아니다.
19. `publish_at`을 쓰는 경우 `privacy_status`가 `private`이고, 시각이 미래이며,
    타임존이 포함된 ISO 8601이다.

## 8. API로 못 하는 것

설계상 자동화 범위를 잘못 잡지 않기 위해 명시한다. 아래는 `*.publish-review.md`의 수동
체크리스트 항목으로 남긴다.

- **썸네일**: `thumbnails.set`은 전화 인증된 채널만 가능하고, Shorts는 대개 커버 프레임을
  쓴다. 1단계 구현에서는 제외한다.
- **재생목록 추가**: `playlistItems.insert`로 가능하지만 별도 스코프와 재생목록 ID가
  필요하다. 프로필에 `playlist_id`를 두고 후속 단계로 미룬다.
- **끝 화면·카드·리믹스 설정**: Data API에 없다. Studio에서 처리한다.
- **댓글 정책 기본값**: API로 설정할 수 없다. 채널 단위로 Studio에서 한 번 정한다.
- **음악·효과음 저작권 클레임**: 업로드 후 Studio에서만 확인된다. 게시 후 확인 항목이다.

## 9. 라이선스 리스크 — 결정이 필요한 부분

설계 중 확인한 실질적 문제다. 게시 단계 코드보다 먼저 정리되어야 한다.

`config/pipeline.json`의 나무위키 캡처 설정은 `license_assumption: "CC BY-NC-SA 2.0 KR"`,
`noncommercial_only: true`다. 그리고 현재 팬텀 에피소드는 나무위키 캡처 5개를 쓴다.

- **NC(비영리)**: 수익 창출을 켠 채널의 업로드는 상업적 이용으로 해석될 여지가 크다.
  수익화 계획이 있으면 나무위키 캡처는 그대로 쓸 수 없고, 원 출처(공식 자료, 위키백과 등)를
  다시 찾아 대체하거나 직접 만든 텍스트 카드로 바꿔야 한다.
- **SA(동일조건변경허락)**: 2차적 저작물에 같은 라이선스를 요구한다. 영상 전체에 적용될
  범위가 불분명하다.
- 또한 현재 manifest의 후보 상당수가 `license: "unknown"`이고, 프랜차이즈 공식 아트워크는
  검토 노트에 "권리와 플랫폼 정책 확인 전 사용 금지"로 남아 있다.

그래서 `commercial_use`를 `pipeline.json`에 명시적 플래그로 둔다. 기본값은 안전한 쪽인
`true`(수익화 가정)로 두고, 이 경우 검증기가 NC 자료를 차단한다. 취미 목적 비수익
채널이면 `false`로 바꾸고 NC 자료를 검토 후 허용한다. 이 값이 정해지기 전에는
팬텀 에피소드의 최종 렌더 자체가 확정될 수 없다.

## 10. 구현 순서

각 단계가 독립적으로 검증 가능하도록 쪼갠다.

1. **1단계 — 오프라인 계획과 게이트.** `plan_publish.py`, `render_publish_review.py`,
   `approve_publish.py`, `validate_publish.py`. 네트워크와 OAuth가 필요 없고
   `tests/test_pipeline.py`에 단위 테스트를 붙일 수 있다. 설명문 바이트 상한, 라이선스
   차단, 승인 게이트, 고지 문장 검사를 여기서 전부 확정한다.
2. **2단계 — 인증과 비공개 업로드.** `authorize_youtube.py`, `upload_youtube.py`.
   `private` 고정이라 실수의 비용이 낮다. 실제 채널에 테스트 영상 하나로 확인한다.
3. **3단계 — 공개 전환.** `promote_youtube.py`. 예약 공개와 즉시 공개를 지원한다.
4. **4단계 — 운영 지표.** `fetch_youtube_stats.py`로 `videos.list` 조회 결과를 누적한다.
   재생목록 추가와 썸네일은 이 시점에 필요하면 붙인다.

1단계는 기존 저장소만으로 완결되므로 지금 바로 구현할 수 있다. 2단계부터는 Google Cloud
프로젝트와 OAuth 클라이언트가 필요하다.

## 11. 미해결 결정 사항

1. **수익화 여부.** 9절의 `commercial_use` 값. 나머지 라이선스 정책이 여기에 달려 있다.
2. **`category_id`.** 24(Entertainment), 27(Education), 22(People & Blogs) 중 선택.
3. **업로드 후 기본 동작.** 비공개 유지 후 수동 공개인지, 예약 공개 시각을 프로필에
   고정할지.
4. **아동용 대상 여부.** `selfDeclaredMadeForKids`. 포켓몬 소재라 판단이 필요하다.
   true로 선언하면 댓글이 비활성화된다.
5. **채널 고정 푸터.** 설명문 마지막에 넣을 고정 문구(채널 소개, 정정 요청 안내 등).
