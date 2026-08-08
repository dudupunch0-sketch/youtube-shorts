# YouTube Shorts Automation

짧은 주제 입력을 약 60초짜리 세로형 슬라이드 쇼 영상으로 만드는 프로젝트다. 레퍼런스 쇼츠는 초기 스타일 설정에만 사용하고, 이후 에피소드마다 다시 요구하지 않는다.

## 현재 확정된 방향

- 영상 목표 길이: 50~70초
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
scripts/generate_tts.py       장면별 TTS와 타이밍 manifest 생성 CLI
```

## 빠른 검증

WSL에서 실행한다.

```bash
python3 scripts/validate_episode.py examples/episodes/roman-baths.json
```

검증기는 장면 수, 필수 필드, 목표 영상 길이, 장면별 시간 범위를 검사한다. 현재 예시에는 실제 TTS와 미디어 파일이 아직 연결되지 않았으므로, 다음 단계에서 각 어댑터를 붙인다. 레퍼런스 영상은 복제하지 않고, `references/shorts-style-profile.md`에 정리한 형식·리듬·출처 정책만 재사용한다.

## 웹 미디어 검색 fallback

웹 검색이나 공식 공개 API를 먼저 사용한다. 특정 URL이 403, WAF 챌린지, 빈 페이지 등으로 막힐 때만 Codex에 설치된 `insane-search` 스킬을 fallback으로 사용한다. 이 스킬은 페이지 접근과 내용 추출을 돕지만 라이선스를 보증하지 않으므로, 최종 미디어 manifest에는 원본 URL·제작자·라이선스·출처를 계속 기록해야 한다.

일반 URL fallback의 진입점은 스킬의 `scripts/run_engine.sh`이며, 결과의 validation과 trace가 실제 콘텐츠를 확인한 경우에만 수집 결과를 채택한다. Openverse·Wikimedia Commons 같은 공개 미디어 검색 결과도 동일하게 원본 라이선스 페이지를 확인한다.

## TTS 연결

TTS는 로컬 실행 가능한 Supertonic 3와 Qwen3-TTS를 사용한다. 듣기 좋은 음질은 Qwen 쪽이었지만, 현재 장비에서는 CPU 생성이 너무 느리고 MX450 GPU 경로도 안정적이지 않다. 따라서 Supertonic 3을 실제 파이프라인의 기본 provider로 유지하고, Qwen은 품질 기준/reference provider로 보존한다. ElevenLabs는 외부 API fallback으로 유지한다.

### 로컬 TTS 설치

별도 가상환경을 만든다. WSL에서 실행한다.

```bash
uv venv .venv-tts
uv pip install --python .venv-tts/bin/python -r requirements-tts-local.txt
```

두 provider 모두 같은 episode를 입력으로 받을 수 있다. 먼저 3개 장면만 생성해 음질과 발음을 비교할 수 있다.

```bash
.venv-tts/bin/python scripts/generate_local_tts.py \
  output/episodes/phantom-clefairy-shadow.json \
  --provider supertonic \
  --voice F1 \
  --limit 3

.venv-tts/bin/python scripts/generate_local_tts.py \
  output/episodes/phantom-clefairy-shadow.json \
  --provider qwen3_tts \
  --speaker Sohee \
  --limit 3
```

전체 장면은 `--limit`을 빼고 실행한다. Qwen을 실행할 때는 생성된 WAV가 무음이 아닌지 직접 확인한다. 현재 MX450에서는 Qwen의 일반 FP16 GPU 샘플링이 실패할 수 있으므로, production 기본값은 Supertonic으로 둔다.

```bash
.venv-tts/bin/python scripts/generate_local_tts.py \
  output/episodes/phantom-clefairy-shadow.json \
  --provider supertonic

.venv-tts/bin/python scripts/generate_local_tts.py \
  output/episodes/phantom-clefairy-shadow.json \
  --provider qwen3_tts --device cpu
```

결과는 provider별 `output/audio/` 폴더와 `output/manifests/`에 저장된다. manifest에는 장면별 실제 음성 길이와 생성 시간이 기록된다.

### ElevenLabs fallback

ChatGPT 구독만으로는 이 저장소가 MP3 파일을 직접 받을 수 없으므로, ElevenLabs를 사용하려면 별도 API 키가 필요하다. 키와 개인 음성 ID는 Git에 저장하지 않는다.

1. `config/local/elevenlabs-tts.json.example`을 `config/local/elevenlabs-tts.json`으로 복사한다.
2. `.env.example`을 `.env`로 복사한다.
3. `.env`에 `ELEVENLABS_API_KEY`를 넣고, `ELEVENLABS_TTS_VOICE_ID` 또는 로컬 프로필의 `voice_name`을 설정한다.
4. 아래 dry-run으로 장면별 생성 계획을 확인한다.

```bash
python3 scripts/generate_tts.py \
  output/episodes/phantom-clefairy-shadow.json \
  --config config/local/elevenlabs-tts.json \
  --profile korean-narrator \
  --dry-run
```

실제 생성은 장면당 MP3 한 개를 만들고, 음성의 실제 길이를 측정해 `output/manifests/*.tts.json`에 기록한다.

```bash
python3 scripts/generate_tts.py \
  output/episodes/phantom-clefairy-shadow.json \
  --config config/local/elevenlabs-tts.json \
  --profile korean-narrator
```

결과 음성은 `output/audio/` 아래에 저장되며 Git에는 올라가지 않는다. 기본 `planned` 타임라인은 대본의 50~70초 목표를 유지하고, 특정 음성이 계획 장면보다 길 경우 해당 장면만 늘린다. 나중에 음성 길이만으로 타임라인을 만들고 싶으면 `--timeline-mode speech`를 사용한다.

음성은 사용자가 직접 복잡하게 찾아야 하는 것은 아니다. 우선 한국어 내레이션에 어울리는 음성 하나를 계정에서 선택하면 되고, 이후에는 같은 프로필로 자동 생성된다. 원하는 분위기(차분한 설명체, 빠른 정보형, 낮은 남성 음성 등)만 정하면 음성 선택 기준은 프로젝트 쪽에서 관리할 수 있다.

## 다음 작업

1. ElevenLabs 키·음성 프로필로 실제 TTS 한 편 생성
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

기본 제공자는 OpenAI API이며, 필요한 경우 Claude Code·Codex CLI·ChatGPT 프롬프트 방식으로 바꿀 수 있다.

### OpenAI API

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

### Claude Code

Claude Code가 PATH에 있거나 `CLAUDE_COMMAND`로 실행 파일을 지정하면 된다.

```bash
export CLAUDE_COMMAND=claude
python3 scripts/generate_episode.py \
  --provider claude_code \
  --topic "포켓몬의 의외의 설정"
```

### Codex CLI

Codex CLI 로그인 상태에서 실행한다. 모델 인증은 Codex CLI가 관리한다.

```bash
export CODEX_COMMAND=codex
python3 scripts/generate_episode.py \
  --provider codex_cli \
  --topic "포켓몬의 의외의 설정"
```

### ChatGPT 수동 프롬프트

현재 대화 중인 ChatGPT 세션을 로컬 프로그램이 직접 호출할 수는 없으므로, ChatGPT에 바로 붙여 넣을 수 있는 프롬프트 파일을 만든다.

```bash
python3 scripts/generate_episode.py \
  --provider chatgpt_prompt \
  --topic "포켓몬의 의외의 설정"
```

이 방식은 `output/prompts/`에 저장된 프롬프트를 ChatGPT에 넣고, 반환된 JSON을 다음 단계의 episode 파일로 사용한다.

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
