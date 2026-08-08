# YouTube Shorts Automation

짧은 주제 입력을 약 60초짜리 세로형 슬라이드 쇼 영상으로 만드는 프로젝트다. 레퍼런스 쇼츠는 초기 스타일 설정에만 사용하고, 이후 에피소드마다 다시 요구하지 않는다.

## 현재 확정된 방향

- 영상 목표 길이: 55~65초
- 장면 수: 고정하지 않음. 기본 권장 범위는 12~18개
- 장면 길이: 대본과 TTS 길이에 따라 약 2.5~5초
- 장면 단위: 한 장면에는 하나의 핵심 내용만 둔다
- 미디어 우선순위: 합법적으로 사용할 수 있는 웹 자료 → 직접 생성한 이미지 → 추상 배경/타이포그래피
- 게시 전에는 사람이 대본, 사실, 미디어 출처, 자막을 검수한다

## 파이프라인

```text
활성 concept의 스타일 프로필 + 주제
  ↓
scriptwriter 스킬
  ↓
60초 대본 + 장면 JSON
  ↓
장면별 미디어 검색 또는 생성
  ↓
TTS 생성 및 실제 길이 측정
  ↓
자막·미디어·음성 합성
  ↓
검증 후 MP4 출력
```

## 폴더 구조

```text
config/pipeline.json       파이프라인 규칙과 길이 제한
concepts/                   concept 레지스트리와 concept별 정의
references/                 레퍼런스 쇼츠에서 추출한 스타일 프로필
skills/scriptwriter/       노트 확장용 문체 스킬 초안
examples/notes/             입력 노트 예시
examples/episodes/          장면 JSON 예시
scripts/generate_episode.py 주제에서 episode JSON을 생성하는 CLI
scripts/validate_episode.py 에피소드 포맷 검증기
```

## 빠른 검증

WSL에서 실행한다.

```bash
python3 scripts/validate_episode.py examples/episodes/roman-baths.json
```

검증기는 장면 수, 필수 필드, 목표 영상 길이, 장면별 시간 범위를 검사한다. 현재 예시에는 실제 TTS와 미디어 파일이 아직 연결되지 않았으므로, 다음 단계에서 각 어댑터를 붙인다. 레퍼런스 영상은 복제하지 않고, `references/shorts-style-profile.md`에 정리한 형식·리듬·출처 정책만 재사용한다.

## 다음 작업

1. TTS 어댑터와 실제 음성 길이 측정 연결
2. 웹 미디어 검색/출처 저장 어댑터 연결
3. 이미지·음성·자막을 MP4로 합성
4. 사람 검수용 프리뷰 리포트 생성
5. 새 레퍼런스를 받을 때만 스타일 프로필 갱신 기능 추가
6. 유튜브 업로드는 위 과정이 안정화된 뒤 별도 단계로 추가

## 실제 사용 흐름

초기 한 번만 레퍼런스 쇼츠 3~5개를 분석해 스타일 프로필을 만든다. 그 이후에는 다음처럼 주제 입력만 받는다.

```text
주제: 포켓몬에서 가장 오해받는 설정
반드시 포함할 정보: 타입 상성에 관한 공식 설명
피하고 싶은 방향: 지나치게 전문적인 설명
```

스타일을 바꾸고 싶을 때만 새 레퍼런스를 추가로 제공해 프로필을 갱신한다.

## 대본 생성 실행

OpenAI API 키를 환경 변수로 설정한 뒤 실행한다.

```bash
export OPENAI_API_KEY="..."
python3 scripts/generate_episode.py \
  --topic "포켓몬에서 가장 오해받는 설정" \
  --must-include "타입 상성에 관한 공식 설명" \
  --avoid "지나치게 전문적인 설명"
```

짧은 노트 파일을 직접 넣을 수도 있다.

```bash
python3 scripts/generate_episode.py --note examples/notes/roman-baths.md
```

API를 호출하지 않고 concept과 프롬프트 연결만 확인하려면 `--dry-run`을 사용한다. 생성된 episode는 기존 검증기를 통과한 경우에만 `output/episodes/`에 저장된다.

## Concept 시스템

현재 초기 설정은 `fictional-media-lore` concept으로 저장되어 있으며 `concepts/registry.json`에서 활성 상태다. 각 concept은 다음을 독립적으로 가질 수 있다.

- 스타일 프로필
- 대상 도메인
- 말투와 전개 규칙
- 출처·해석 정책
- 장면과 영상 출력 규칙

나중에 다른 분야를 추가할 때는 새 concept 정의와 스타일 프로필을 등록하고, 입력에 `concept`을 지정하면 된다. 생략하면 현재 활성 concept을 사용한다.

## 콘텐츠 원칙

초기 도메인은 창작물의 설정, 캐릭터, 기술, 에피소드, 상품, 번역, 팬덤의 오해를 다루는 정보형 쇼츠다. 공식 자료와 2차 자료를 참고할 수 있으며, 해석을 섞을 수 있다. 다만 공식 설정과 2차 자료와 창작적 해석을 내부적으로 구분해, 해석을 공식 사실처럼 포장하지 않는다.
