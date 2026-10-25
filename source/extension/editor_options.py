from card_editor import FONT_STYLES

TIPS={1:"표지는 사진과 짧은 큰 제목으로 글의 주제를 바로 알려주세요.",2:"특징 설명은 사진과 핵심 두 줄을 함께 배치하면 이해하기 쉬워요.",3:"오해를 바로잡는 주의점은 텍스트 중심 유형도 잘 맞아요.",4:"빗질하는 손과 도구가 가려지지 않게 글과 사진을 나눠보세요.",5:"구강 관리 장면을 살리고 설명은 행동 한 가지로 줄여보세요.",6:"산책 자세와 여유 공간을 살려 편안한 경험을 보여주세요.",7:"체크리스트는 사진을 숨기고 항목을 분명하게 정리해도 좋아요.",8:"보조 사진은 설명을 더하기보다 표정과 털의 특징을 보여주세요.",9:"도구 사진은 물건이 가려지지 않도록 캡션을 짧게 붙여주세요.",10:"마무리 보조 사진은 쉼과 생활 분위기를 전달하도록 여백을 남겨주세요."}

def options():
    roles={"title":{"x":80,"y":116,"width":920,"font_size":94},"body":{"x":84,"y":425,"width":912,"font_size":44},"number":{"x":895,"y":1275,"width":150,"font_size":26}}
    return {"tips":TIPS,"font_styles":[
        {"id":"default","label":"기본","description":"제목 Noto Sans KR 800 · 본문 Noto Sans KR 400","title_weight":800,"body_weight":400,"title_scale":1,"body_scale":1,"gap":72,"intent":"처음 제공했던 Noto Sans KR 제목·본문 조합입니다.",**FONT_STYLES["default"]},
        {"id":"serif","label":"세리프 · 차분한 매거진","description":"제목 Noto Serif KR 700 · 본문 고운바탕 400","title_weight":700,"body_weight":400,"title_scale":1.06,"body_scale":1.08,"gap":80,"intent":"명조 제목의 힘과 본문용 바탕의 차분한 읽기 리듬을 조합합니다.",**FONT_STYLES["serif"]},
        {"id":"sans","label":"산세리프 · 명확한 정보형","description":"제목 도현체 · 본문 Noto Sans KR 400","title_weight":400,"body_weight":400,"title_scale":1.12,"body_scale":1.14,"gap":76,"intent":"단단한 제목용 고딕과 중립적인 본문 고딕의 역할을 나눕니다.",**FONT_STYLES["sans"]},
        {"id":"hand","label":"손글씨 · 친근한 돌봄 노트","description":"제목 개구 700 · 본문 고운돋움 400","title_weight":700,"body_weight":400,"title_scale":1.25,"body_scale":1.14,"gap":88,"intent":"손글씨 제목에 손의 움직임이 느껴지는 고운돋움을 붙여 부드럽게 읽히게 합니다.",**FONT_STYLES["hand"]}],
      "font_reference_note":"Google Design의 제목·본문 역할과 대비 원칙, 각 글꼴 제작자의 설명을 참고해 선정한 조합입니다. 이 세 조합 자체를 공식 추천 조합으로 인용한 것은 아닙니다.",
      "font_license_note":"제공하는 세 조합은 모두 SIL OFL 1.1 글꼴로 상업적 디자인에 무료로 사용할 수 있습니다. 공식 글꼴 파일과 저작권·라이선스 원문을 함께 보관합니다.",
      "types":{
       "photo":{"label":"사진 중심","description":"사진을 넓게 쓰고 위에 큰 제목을 배치합니다.","background":"#F7F3E8","image":{"x":0,"y":0,"scale":1,"visible":True},"shade":{"mode":"dark","strength":.9,"end":.72},"roles":roles,"color":"#FFFFFF"},
       "split":{"label":"글·사진 분리","description":"윗부분은 글, 아래는 사진으로 나눕니다. 사진 안의 위치도 계속 조정할 수 있어요.","background":"#F7F3E8","image":{"x":0,"y":0,"scale":1,"visible":True,"clip":{"x":0,"y":640,"width":1080,"height":710}},"shade":{"mode":"none","strength":0,"end":.72},"roles":{**roles,"title":{"x":80,"y":100,"width":920,"font_size":90},"body":{"x":84,"y":385,"width":912,"font_size":44}},"color":"#24384A"},
       "text":{"label":"텍스트 중심","description":"사진을 숨기고 단색 배경에 핵심 메시지나 체크리스트를 배치합니다.","background":"#173E32","image":{"x":0,"y":0,"scale":1,"visible":False},"shade":{"mode":"none","strength":0,"end":.72},"roles":{**roles,"body":{"x":84,"y":430,"width":912,"font_size":48}},"color":"#FFFFFF"}}
    }
