# API_SPEC - 실제 서버 기준

입출력은 JSON입니다. 변경 요청에는 프로젝트 version과 request_id가 필요합니다. 같은 ID·같은 입력은 저장된 결과를 반환하고 같은 ID·다른 입력은 409입니다. 잘못된 버전·상태의 변경을 거부합니다.

| 요청 | 주요 내용 |
|---|---|
| GET /api/health | 서버 상태 |
| GET/POST /api/projects | 목록 / topic·mode로 생성 |
| GET /api/projects/{id} | 현재 후보·질문·기획·이미지·렌더·검사 상태 |
| POST /api/projects/{id}/research | 실제 조사 시작 |
| POST /api/projects/{id}/selection | 후보 ID 선택 |
| POST /api/projects/{id}/preferences | 목적·카드 크기 저장 |
| POST /api/projects/{id}/next | 다음 질문 또는 편집 흐름 |
| POST /api/projects/{id}/answers | question_id·질문 버전·답변 저장 및 같은 세션 재개 |
| POST /api/projects/{id}/expand | 조사 기간 확대 |
| POST /api/projects/{id}/retry 또는 cancel | 재시도 / 취소 |
| POST /api/projects/{id}/storyboard | 카드 기획 생성·재기획 |
| POST /api/projects/{id}/edit-card | 카드 ID·현재 기획 버전·문구 변경 |
| POST /api/projects/{id}/layout-card | 글자 배치·크기, 선택적 theme·image_offset_y |
| POST /api/projects/{id}/fix-card | 한 카드에 대한 수정 요청·범위 |
| POST /api/projects/{id}/import-image | card_id·image_base64·generator·prompt |
| POST /api/projects/{id}/approve | storyboard 또는 final 단계 승인 |
| POST /api/projects/{id}/verify-export | 내보낸 ZIP 직접 검사 |
| GET /api/projects/{id}/images/{card_id} | 원본 생성 배경 |
| GET /api/projects/{id}/renders/{card_id} | 현재 카드 PNG. download=1은 승인 후 다운로드 |
| GET /api/projects/{id}/export.zip | 최종 승인된 ZIP |

layout-card의 기본 필드는 position(top/bottom/full), title_size(44~80), body_size(26~44), text_color, panel(0~0.95)입니다. 새 테마는 theme="ivory-gradient", image_offset_y 정수(-200~300)를 추가합니다. 고딕·그라데이션 테마는 현재 1080x1350용입니다. 순번 색상 자동 선택, 별도 출처 띠 없음. 실제 데이터 키와 동작의 최종 기준은 source/app.py입니다.
