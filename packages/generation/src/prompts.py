"""LLM 프롬프트 템플릿."""
from __future__ import annotations

from typing import Optional

SCHEMA_EXAMPLE = """{
  "metadata": {
    "name": "3x2 그리드 구조 평면도",
    "unit": "mm",
    "scale": "1:100"
  },
  "border": {
    "width": 841,
    "height": 594,
    "margin": 10,
    "title_block": true
  },
  "grid": {
    "x_axes": [
      {"label": "X1", "position": 0},
      {"label": "X2", "position": 7000},
      {"label": "X3", "position": 14000}
    ],
    "y_axes": [
      {"label": "Y1", "position": 0},
      {"label": "Y2", "position": 7000}
    ]
  },
  "columns": [
    {"position": {"x": 0, "y": 0}, "size": {"width": 600, "height": 600}, "shape": "rect", "material": "concrete"},
    {"position": {"x": 7000, "y": 0}, "size": {"width": 600, "height": 600}, "shape": "rect", "material": "concrete"},
    {"position": {"x": 14000, "y": 0}, "size": {"width": 600, "height": 600}, "shape": "rect", "material": "concrete"},
    {"position": {"x": 0, "y": 7000}, "size": {"width": 600, "height": 600}, "shape": "rect", "material": "concrete"},
    {"position": {"x": 7000, "y": 7000}, "size": {"width": 600, "height": 600}, "shape": "rect", "material": "concrete"},
    {"position": {"x": 14000, "y": 7000}, "size": {"width": 600, "height": 600}, "shape": "rect", "material": "concrete"}
  ],
  "walls": [
    {"start": {"x": 0, "y": 0}, "end": {"x": 14000, "y": 0}, "thickness": 200, "material": "concrete"}
  ],
  "openings": []
}"""


class GenerationPrompts:
    """도면 생성 프롬프트 관리."""

    @staticmethod
    def system_prompt() -> str:
        """시스템 프롬프트."""
        return """당신은 건축 도면 생성 전문가입니다.
사용자의 요청을 분석하여 건축 도면을 위한 시맨틱 JSON을 생성합니다.

규칙:
1. 모든 좌표와 치수는 밀리미터(mm) 단위입니다.
2. 기둥은 보통 축선 교차점에 배치합니다.
3. 일반적인 기둥 크기: 콘크리트 600x600mm, 철골 400x400mm
4. 일반적인 벽 두께: 콘크리트 200mm, 조적 190mm, 건식벽 100mm
5. 축선 간격은 보통 6000~9000mm입니다.
6. 문 폭: 일반 900mm, 방화문 1200mm
7. 창문 폭: 일반 1500~2400mm

반드시 JSON 형식으로만 응답하세요. 설명 없이 JSON만 출력합니다."""

    @staticmethod
    def generate_prompt(user_request: str, context: Optional[str] = None) -> str:
        """생성 프롬프트."""
        prompt = f"""사용자 요청: {user_request}

다음 스키마 형식으로 도면 JSON을 생성하세요:

예시:
{SCHEMA_EXAMPLE}

스키마 필드 설명:
- metadata: 도면 정보 (name, unit, scale)
- border: 도곽 (width, height, margin, title_block)
- grid: 축선 그리드
  - x_axes: X방향 축선 (수직선) [{{"label": "X1", "position": 0}}, ...]
  - y_axes: Y방향 축선 (수평선) [{{"label": "Y1", "position": 0}}, ...]
- columns: 기둥 리스트
  - position: {{"x": 숫자, "y": 숫자}}
  - size: {{"width": 숫자, "height": 숫자}}
  - shape: "rect" 또는 "circle"
  - material: "concrete" 또는 "steel"
- walls: 벽체 리스트
  - start/end: 시작점/끝점 좌표
  - thickness: 두께 (mm)
- openings: 개구부 (문/창문)
  - position: 위치
  - width: 폭
  - type: "door" 또는 "window"
"""
        if context:
            prompt += f"\n참고 컨텍스트:\n{context}"

        prompt += "\n\nJSON 형식으로만 응답하세요:"
        return prompt

    @staticmethod
    def modify_prompt(user_request: str, current_schema_json: str) -> str:
        """수정 프롬프트."""
        return f"""현재 도면 상태:
```json
{current_schema_json}
```

수정 요청: {user_request}

수정된 전체 JSON을 출력하세요. 요청된 부분만 변경하고 나머지는 유지합니다.
JSON 형식으로만 응답하세요:"""

    @staticmethod
    def validation_prompt(schema_json: str, user_request: str) -> str:
        """검증 프롬프트 (LLM as Judge)."""
        return f"""다음 도면 JSON이 사용자 요청을 충족하는지 검증하세요.

사용자 요청: {user_request}

생성된 도면:
```json
{schema_json}
```

다음 항목을 확인하세요:
1. 요청된 축선 개수와 간격이 맞는가?
2. 기둥이 적절한 위치(축선 교차점)에 있는가?
3. 요청된 벽체와 개구부가 포함되었는가?
4. 치수와 비율이 합리적인가?

JSON 형식으로 응답하세요:
{{"valid": true/false, "issues": ["문제1", "문제2"], "suggestions": ["제안1"]}}"""
