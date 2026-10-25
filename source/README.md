# 카드뉴스 앱 + 강아지 블로그 제작실

AI 소식을 카드뉴스로 만드는 앱과, 같은 흐름을 강아지 블로그 정보글 제작으로 넓힌 제작실입니다(2026-10-26 기준). 먼저 프로젝트설명서.pdf를 보고 results/의 실제 결과를 확인하세요. 인증정보·작업 DB·원시 실행 세션은 포함하지 않았습니다.

## 구성
- 프로젝트설명서.pdf: 두 앱의 결과, 요구사항 대응, 실행, 실패 개선과 검증.
- docs/: PRD, DECISIONS, API_SPEC, 검증·최종 승인 기록.
- results/main-cardnews/: 기존 Claude Duet 확정 카드7장과 근거 기록.
- results/dog-blog/: 승인 원고·해시태그·이미지10장·전체 미리보기·근거·폰트 사용 조건.
- evidence/: 입력/선택/결과와 실패 개선의 선별 화면·검증 기록.
- source/: 원래 카드뉴스 앱, extension/은 별도 블로그 제작실. 공개 자료로 만든 승인 데모 포함.

## 실행 - Ubuntu WSL, Python3.12 권장
압축을 푼 source 폴더에서:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cd extension
../.venv/bin/python load_demo.py
../.venv/bin/python app.py
```
http://127.0.0.1:8770/ 와 /editor/ 에서 승인된 말티푸 결과를 볼 수 있습니다. load_demo.py는 새 data/studio.sqlite3만 만들며 기존 DB를 덮어쓰지 않습니다. 초기 상태로 시작하려면 데모 불러오기 단계를 생략합니다. 종료는 Ctrl+C. 다른 포트는 app.py --port 8794.

원래 카드뉴스 앱은 source에서 .venv/bin/python app.py로 시작하고8765를 엽니다. 모의 모드는 로그인 불필요, 실제 조사 모드는 Claude CLI 설치·로그인 필요. 기본 렌더러에 Ubuntu Noto CJK 글꼴이 필요할 수 있습니다. 승인 테마와 확장 편집기용 OFL 글꼴은 source에 포함했습니다.

## 검사
source에서 .venv/bin/python -m unittest -q (26개), extension에서 ../.venv/bin/python -m unittest -q (16개). 실제 Claude 재호출·새 이미지 생성·네이버 발행 검사는 포함하지 않습니다.

## 구현 범위
트렌드 자료 확인→선택→조사·기획→원고·이미지→직접 편집→승인→내보내기를 실제 사례로 실행했습니다. 자료 부족 입력(날짜·지수 없이 검색어만 있는 표)도 실제 브라우저에서 실행해 보완 안내와 기존 자료 보존을 확인했습니다. 후보는 편집 규칙 기반이고 조사·원고·이미지 초안은 AI 도구로 만든 뒤 제작실에 가져왔습니다. 앱 자체 무인 생성 API, 데이터랩 자동 다운로드, 네이버 자동 발행은 미구현입니다. 실제 게시·다른 사람과의 교차 검수는 하지 않았습니다. 협찬·광고 관계가 없음을 직접 확인했습니다.

results/dog-blog/미리보기.html은 로컬에서 열 수 있습니다. 네이버에는 원고.txt를 복사하고 이미지-삽입안내.txt의 순서대로 PNG를 올립니다. 이미지10장·2000자 이상은 이 프로젝트의 편집 목표이며 노출 보장이 아닙니다.
