"""Editorial checks and portable blog exports. These checks do not predict ranking."""
import copy
import html
import io
import json
import re
import zipfile
from pathlib import Path
from trends import InputError
from card_editor import valid_asset_set

REVIEW_TERMS=["상위노출 보장","상위 노출 보장","무조건","100%","완치","부작용 없음","알레르기 없는","무알레르기","최저가","분양문의","분양 문의","구매 문의","즉시 구매","최고의"]

def body_text(c):
    parts=list(c["intro"])
    for s in c["sections"]:parts.extend([s["heading"],*s["paragraphs"]])
    parts.extend(["우리 집 돌봄 체크리스트",*c["checklist"],c["closing"]])
    return "\n\n".join(parts)

def char_count(text):return len(re.sub(r"\s","",text))

def audit(c):
    body=body_text(c);captions="\n".join(i["caption"] for i in c["images"])
    image_text="\n".join("\n".join(i.get(k,"") for k in ("title","message","body")) for i in c["images"])
    public="\n".join([c["title"],body," ".join(c["hashtags"]),captions,image_text,c["disclosure"]])
    settings=c["writing_settings"];terms=REVIEW_TERMS+settings.get("custom_avoid_terms",[])
    findings=[{"term":t,"count":public.count(t),"kind":"사용자 회피어" if t in settings.get("custom_avoid_terms",[]) else "과장·보장·거래 유도 표현"} for t in dict.fromkeys(terms) if t and t in public]
    n=char_count(body)
    return {"body_chars_no_space":n,"body_chars_with_space":len(body),"title_chars":len(c["title"]),
        "public_text_chars_no_space":char_count(public),"keyword_body_count":body.count(c["keyword"]),
        "keyword_title_count":c["title"].count(c["keyword"]),"image_count":len(c["images"]),
        "image_target":settings["image_target"],"body_target":[settings["body_min"],settings["body_max"]],
        "body_in_target":settings["body_min"]<=n<=settings["body_max"],"findings":findings,
        "checked_term_count":len(set(terms)),"note":"편집용으로 등록한 표현만 점검합니다. 네이버 공식 금칙어 목록이나 노출 보장 검사가 아닙니다.",
        "count_scope":"본문＝도입·소제목·본문·체크리스트·맺음말. 모든 공백·줄바꿈·탭 제외. 제목·태그·이미지 문구·출처·제작 안내 제외."}

def validate_content(value,research):
    if not research:raise InputError("조사 자료를 먼저 저장해 주세요.")
    if not isinstance(value,dict) or value.get("keyword")!=research["keyword"]:raise InputError("원고와 선택한 소재가 다릅니다.")
    try:
        if not valid_asset_set(value.get("asset_set","maltipoo-v1")):raise ValueError()
        if not 1<=len(value["title"].strip())<=120:raise ValueError()
        if len(value["sections"])!=6 or not value["intro"] or not value["checklist"]:raise ValueError()
        ids={s["id"] for s in research["sources"]}
        for s in value["sections"]:
            if not s["heading"].strip() or not s["paragraphs"] or not all(isinstance(p,str) and p.strip() for p in s["paragraphs"]):raise ValueError()
            if not s["source_ids"] or not set(s["source_ids"]).issubset(ids):raise ValueError()
        if len(value["images"])!=10 or {i["order"] for i in value["images"]}!=set(range(1,11)):raise ValueError()
        for i in value["images"]:
            if not i["alt"] or not i["caption"] or not set(i["source_ids"]).issubset(ids):raise ValueError()
        if not all(isinstance(t,str) and re.fullmatch(r"[가-힣A-Za-z0-9_]{1,30}",t) for t in value["hashtags"]):raise ValueError()
        a=audit(value)
        if a["body_chars_no_space"]>15000:raise ValueError()
    except (KeyError,ValueError,TypeError,AttributeError):raise InputError("제목·본문·태그·이미지 근거의 형식을 확인해 주세요.")
    result=copy.deepcopy(value);result["audit"]=a;result["approval"]=None
    return result

def asset_name(i):return f"{i:02d}.png"

def article_html(c,sources,assets_prefix="images/"):
    e=html.escape
    def paragraphs(lines):return "".join(f"<p>{e(p)}</p>" for p in lines)
    def images(orders):
        result=[]
        for order in orders:
            i=next(x for x in c["images"] if x["order"]==order)
            result.append(f'<figure><img src="{assets_prefix}{asset_name(order)}" alt="{e(i["alt"],quote=True)}"><figcaption>{e(i["caption"])} · AI 제작 이미지</figcaption></figure>')
        return "".join(result)
    out=f'<h1>{e(c["title"])}</h1>'+paragraphs(c["intro"])+images([1])
    for s in c["sections"]:out+=f'<h2>{e(s["heading"])}</h2>'+paragraphs(s["paragraphs"])+images(s["after_images"])
    out+='<h2>우리 집 돌봄 체크리스트</h2><ul>'+"".join(f'<li>{e(t)}</li>' for t in c["checklist"])+"</ul>"+paragraphs([c["closing"],c["disclosure"]])
    out+='<h2>참고한 자료</h2><ul>'+"".join(f'<li><a href="{e(s["url"],quote=True)}">{e(s["title"])}</a></li>' for s in sources)+"</ul>"
    out+=f'<p>{e(" ".join("#"+t for t in c["hashtags"]))}</p>'
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+e(c["title"])+'</title><style>body{max-width:740px;margin:40px auto;padding:0 24px;background:#fffef9;color:#293c36;font:17px/1.95 "Malgun Gothic",sans-serif}h1{font-size:30px;line-height:1.5}h2{font-size:23px;margin-top:48px}p{white-space:pre-wrap}figure{margin:30px 0}img{width:100%;height:auto;border-radius:8px}figcaption{font-size:13px;color:#687c6b}a{color:#285a4a}</style>'+out+'</html>'

def export_zip(state,root):
    c=state.get("content")
    if not c:raise InputError("원고가 아직 없어요.")
    sources=state["research"]["sources"];buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("원고.txt",c["title"]+"\n\n"+body_text(c)+"\n\n"+c["disclosure"])
        z.writestr("해시태그.txt"," ".join("#"+t for t in c["hashtags"]))
        z.writestr("미리보기.html",article_html(c,sources))
        z.writestr("출처와-검수.json",json.dumps({"sources":sources,"audit":audit(c),"approval":c.get("approval"),"provenance":c["provenance"]},ensure_ascii=False,indent=2))
        z.writestr("이미지-삽입안내.txt","\n".join(f'{i["order"]:02d}.png · {i["placement"]} · {i["caption"]}\n대체텍스트: {i["alt"]}' for i in c["images"]))
        if c.get("card_editor"):
            z.writestr("카드-편집배치.json",json.dumps(c["card_editor"],ensure_ascii=False,indent=2))
            packs={"noto":"notosanskr","sans":"notosanskr","serif":"notoserifkr","batang":"gowunbatang","hand":"gaegu","headline":"dohyeon","postcard":"gowundodum","malgun":"nanumgothic"}
            used={packs[t.get("font_family","noto")] for l in c["card_editor"]["layouts"] for t in l["texts"] if t["visible"]}
            for pack in sorted(used):
                license=root/"fonts"/f"{pack}-OFL.txt"
                if license.is_file():z.write(license,f"font-licenses/{pack}-OFL.txt")
            z.writestr("폰트-사용안내.txt","제공한 세리프·산세리프·손글씨 조합은 SIL OFL 1.1 글꼴을 사용합니다. 카드 이미지의 상업적 사용이 가능하며, 폰트 파일 자체를 묶어 배포할 때는 해당 저작권·라이선스 조건을 유지해야 합니다. 원문: https://openfontlicense.org/ofl-faq/ . 이 ZIP에는 사용 글꼴의 OFL 원문을 동봉하며 글꼴 바이너리는 포함하지 않습니다.")
        z.writestr("발행전-확인.txt","네이버에 자동 발행되지 않습니다. 미리보기.html은 배치 참고용이며 네이버 HTML 가져오기 기능이 아닙니다. 원고.txt를 복사하고 images의 PNG를 순서대로 업로드하세요. 이미지10장은 공식 최소 요건이 아닙니다. 본문과 AI 이미지, 실제 협찬·광고 관계를 확인한 뒤 직접 발행하세요. 실제 경험이 있으면 확인 가능한 경험만 추가해 주세요. 최종 검수 승인 여부는 출처와-검수.json에 기록됩니다.")
        z.write(root/"WRITING_RULES.md","작성기준.md")
        for i in c["images"]:
            path=root/"output"/c.get("asset_set","maltipoo-v1")/asset_name(i["order"])
            if not path.is_file():raise InputError("아직 제작 중인 이미지가 있어요. 완료 후 내려받아 주세요.")
            z.write(path,"images/"+path.name)
    return buffer.getvalue()
