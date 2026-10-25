# 확장 첫 단계 API

- GET /api/health: 실행 상태.
- GET /api/state: 현재 snapshot, candidates, datalab, selection, version. 실제 수집 상태는 choose_topic, 선택 뒤 topic_selected.
- POST /api/collect: 고정된 공개 URL의 HTML 수집·파싱. 이전 스냅샷 최대10개 보존. 새 수집 후 소재는 다시 선택.
- POST /api/select: candidate_id, angle(선택). 관측 키워드에 연결된 현재 소재만 저장.
- POST /api/datalab: csv 문자열. date,keyword,index(0~100) 형태의 정규화 표. 중복 날짜·키워드나 1개 날짜뿐인 입력은 거부. 사용자 가져오기이며 원본 자동 대조 전으로 표시.
- GET /api/brief: 선택한 소재와 관점·트렌드 자료. 선택 전409. 원고 생성 전 브리프.

POST에는 version과 request_id가 필요. 동일 요청·동일 입력은 기존 결과 반환, 다른 입력은 거부. 600KB보다 큰 요청과 교차 출처 Origin은 거부. 임의 외부 URL을 서버에서 읽지 않으며 네이버 인증·쿠키를 저장하지 않는다.

## 조사·기획 검토
- POST /api/research: 선택 소재와 일치하는 research 구조를 검증 후 저장. 외부 검색을 실행하는 API가 아니며, 확인된 편집 자료 가져오기. 실제 가져오기는 로컬 `import_reviewed_research.py` 사용.
- POST /api/approve_plan: title_index로 기획 버전·선택 제목 승인 저장. 기획이 없거나 유효한 정수 인덱스가 아니면 거부. 원고 생성·외부 발행 없음.
- state의 research에는 출처·적용 범위·제목·목차·카드 기획·approval 포함. 상태 plan_review → plan_approved. 소재 변경/재수집 시 기존 기획 해제.
- /api/brief에도 research 포함. article_generated는 현재 false.


최신 원고·검수·내보내기 API와 article_generated 변경 사항: CONTENT_STATUS.md 참고.

## 카드 편집 API
POST /api/init_editor: 원본10장 기반 배치 초기화. POST /api/save_layout: order와layout 검증 후 새 자산버전과배치 저장, 승인 해제, 최근30개 이력. /editor/ 정적 편집기, /editor-original/01.png~10.png 읽기전용원본, /editor/font.ttf 로컬한글글꼴. 기존version/request_id 충돌방지 동일. 카드-편집배치.json을 ZIP에 포함. CARD_EDITOR.md 참고.

## 전체 폰트·카드 유형
GET /api/editor-options: 한 줄 팁·세 조합·유형 제안. POST /api/save_layouts: layouts10개와font_style 검증 후 전체 저장, 이전 배치 이력 유지. 사진 visible/clip, background, card_type, text.font_family를 지원하며 이전 배치와 호환. /font-study/에서 예시·참고 자료·OFL 조건 확인. FONT_PAIRINGS.md 참고.

2026-10-26: save_layout / save_layouts에 선택 필드 font_bases(10개 기준 배치)를 지원한다. 크기 배율 중복 적용 방지를 위한 기준이며 구조와 범위를 검증한 후 저장한다. 생략 시 기존 기준을 보존한다.

최종 승인: POST /api/approve_content의 commercial_relationship은 선택 필드이며 none/present/unknown만 허용. 사용자 확인 결과를 현재 revision의 approval에 보관한다. 잘못된 값은 저장 상태를 바꾸지 않는다.
