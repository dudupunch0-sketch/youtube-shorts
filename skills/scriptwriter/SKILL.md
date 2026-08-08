# Shorts Scriptwriter Skill

## 목적

초기 설정 단계에서 제공된 레퍼런스 쇼츠로 만든 스타일 프로필을 사용해, 사용자의 짧은 주제 정보만으로 약 60초짜리 쇼츠용 대본과 장면 목록을 작성한다. 결과물은 이후 미디어 검색, TTS, 자막, 영상 합성 단계가 바로 사용할 수 있는 구조화된 JSON이어야 한다.

## 입력

```text
주제: ...
반드시 포함할 정보: ...
피하고 싶은 방향: ...

레퍼런스 쇼츠는 매번 입력하지 않는다. `references/shorts-style-profile.md`가 기본 스타일 프로필이며, 사용자가 새 레퍼런스를 주면서 업데이트를 요청할 때만 다시 분석한다.
```

## 출력 규칙

1. 저장된 스타일 프로필의 형식과 리듬만 사용하고, 레퍼런스의 문장·장면·이미지를 복제하지 않는다.
2. 전체 내레이션 예상 길이는 55~65초를 목표로 한다.
3. 장면 수는 내용에 따라 결정한다. 기본 권장 범위는 12~18개다.
4. 각 장면은 하나의 핵심 내용만 전달한다.
5. 첫 장면은 시청자가 계속 볼 이유를 만드는 훅이어야 한다.
6. 중간 장면은 사실, 사례, 비교, 반전 중 하나를 사용한다.
7. 마지막 장면은 핵심 메시지를 기억하게 하는 결론이어야 한다.
8. 문장은 TTS가 자연스럽게 읽을 수 있도록 짧게 쓴다.
9. 각 장면에 `visual_query`, `visual_type`, `caption`을 함께 생성한다.
10. 창작물 정보는 `official`, `secondary_reference`, `creative_interpretation` 중 하나로 내부 분류한다.
11. `creative_interpretation`은 허용하지만 공식 설정처럼 단정하지 않는다.
12. 특정 작가나 크리에이터의 문체를 그대로 모방하지 않는다.

## JSON 계약

```json
{
  "title": "영상 제목",
  "topic": "주제",
  "language": "ko-KR",
  "target_duration_sec": 60,
  "estimated_duration_sec": 60,
  "reference_style": "references/shorts-style-profile.md",
  "content_domain": "fictional_media_lore",
  "segments": [
    {
      "index": 1,
      "narration": "TTS가 읽을 문장",
      "visual_query": "검색 또는 이미지 생성용 설명",
      "visual_type": "photo|video|illustration|map|typography",
      "caption": "화면에 표시할 짧은 자막",
      "duration_sec": 4,
      "claim_type": "official|secondary_reference|creative_interpretation",
      "source": {
        "status": "pending",
        "source_url": null,
        "license": null,
        "creator": null
      }
    }
  ]
}
```

## 스타일 TODO

- [ ] 사용자가 제공하는 레퍼런스에서 문장 길이와 리듬 추출
- [ ] 훅의 유형과 금지되는 도입부 정의
- [ ] 존댓말/반말/해설체 등 기본 말투 결정
- [ ] 정보 전달 속도와 문장당 음절 수 측정
- [ ] 반복 표현과 상투적인 AI 문장 제거 규칙 추가
- [ ] 결말과 CTA의 사용 여부 결정
- [ ] 사실 검증이 필요한 주제의 출처 표기 규칙 추가
- [ ] 썸네일 제목과 영상 제목 생성 규칙 추가
- [ ] 레퍼런스 3~5개에서 공통 규칙과 예외를 분리하는 자동 분석 추가
- [ ] 작품별 공식 출처와 2차 출처의 우선순위 정의

## 장면 분할 TODO

- [ ] 실제 TTS 길이를 기준으로 장면을 재분할
- [ ] 55초 미만이면 부족한 설명을 확장
- [ ] 65초 초과면 중요도가 낮은 장면을 축약/삭제
- [ ] 첫 3초의 훅을 별도 검수
