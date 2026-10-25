"""Public-source adapters. No authenticated endpoints, cookies or invented metrics."""
import csv
import io
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

PUBLIC_URL="https://countdot.com/keyword/creator-trends"
DATALAB_URL="https://datalab.naver.com/keyword/trendSearch.naver"
KST=timezone(timedelta(hours=9))

class InputError(ValueError):pass

class PublicParser(HTMLParser):
    def __init__(self):
        super().__init__();self.heading=None;self.heading_text=[];self.date=None;self.category=None;self.in_ol=False;self.in_li=False;self.li=[];self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag in ("h2","h3"):self.heading=tag;self.heading_text=[]
        if tag=="ol" and self.category=="반려동물":self.in_ol=True
        if tag=="li" and self.in_ol:self.in_li=True;self.li=[]
    def handle_data(self,data):
        if self.heading:self.heading_text.append(data)
        if self.in_li:self.li.append(data)
    def handle_endtag(self,tag):
        if tag==self.heading:
            text="".join(self.heading_text).strip()
            if tag=="h2" and re.search(r"\d{4}-\d{2}-\d{2}",text):self.date=re.search(r"\d{4}-\d{2}-\d{2}",text)[0]
            if tag=="h3":self.category=text
            self.heading=None
        if tag=="li" and self.in_li:
            text=" ".join(x.strip() for x in self.li if x.strip());m=re.match(r"^(\d+)\s+(.+)$",text)
            if m:self.rows.append({"rank":int(m[1]),"keyword":m[2].strip(),"search_volume":None,"rank_change":None})
            self.in_li=False
        if tag=="ol":self.in_ol=False

def parse_public(raw):
    parser=PublicParser();parser.feed(raw)
    if not parser.date or not parser.rows:raise InputError("공개 페이지에서 반려동물 목록과 기준일을 찾지 못했어요. 이전 자료는 유지합니다.")
    try:datetime.strptime(parser.date,"%Y-%m-%d")
    except ValueError:raise InputError("공개 페이지의 기준일 형식을 확인할 수 없어요.")
    ranks=[r["rank"] for r in parser.rows]
    if len(set(ranks))!=len(ranks) or ranks!=sorted(ranks):raise InputError("공개 목록의 순위가 중복되거나 순서가 달라 확인이 필요해요.")
    return {"source_url":PUBLIC_URL,"source_type":"third_party_public_snapshot","upstream_verified":False,
            "snapshot_date":parser.date,"observed_at":datetime.now(KST).isoformat(),"category":"반려동물","rows":parser.rows,
            "limitations":["제3자 공개 목록 · 네이버 원본과 일치 여부 미검증","절대 검색량·유입수·순위 변화 미제공","현재 페이지에서 읽힌 목록만 표시"]}

def fetch_public():
    request=urllib.request.Request(PUBLIC_URL,headers={"User-Agent":"DogBlogStudio/0.1 (public HTML reader)"})
    try:
        with urllib.request.urlopen(request,timeout=25) as r:
            if "text/html" not in r.headers.get("Content-Type",""):raise InputError("공개 페이지가 HTML로 응답하지 않았어요.")
            raw=r.read(2_000_001)
            if len(raw)>2_000_000:raise InputError("공개 페이지가 너무 커서 수집을 중단했어요.")
    except InputError:raise
    except Exception:raise InputError("공개 목록에 연결하지 못했어요. 잠시 후 다시 시도하거나 저장된 자료를 확인해 주세요.")
    return parse_public(raw.decode("utf-8"))

TOPICS={
 "말티푸":("말티푸를 알아보는 초보 보호자 가이드","품종을 알아볼 때 확인할 특성과 생활 준비","정보형 글과 연결하기 좋은 강아지 키워드"),
 "꼬똥 드 툴레아":("꼬똥 드 툴레아, 함께 살기 전 알아볼 점","품종 특성·돌봄 준비를 근거와 함께 정리","강아지 품종을 알아보는 검색 의도"),
 "광교 펫페어":("펫페어 방문 전 준비할 체크리스트","행사 날짜·장소·동반 규정을 공식 안내에서 확인","행사 소재: 최신 공식 일정 확인 필요"),
 "강아지 감":("강아지와 감에 관해 보호자가 궁금해하는 점","급여 관련 정보는 수의학 자료 확인 후 작성","건강·영양 소재: 근거 검토 우선")}

def candidates(snapshot):
    items=[]
    for row in snapshot.get("rows",[]):
        if row["keyword"] not in TOPICS:continue
        title,angle,reason=TOPICS[row["keyword"]]
        items.append({**row,"id":f"rank-{row['rank']}","suggested_title":title,"angle":angle,"reason":reason,
                      "trend_verified":False,"candidate_method":"검색어별 편집 규칙 초안 · 사용자 선택 필요"})
    return items

def read_datalab_csv(text):
    """Explicit normalized interchange: date,keyword,index. Not a claim to parse every Excel export."""
    reader=csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or not {"date","keyword","index"}.issubset(reader.fieldnames):
        raise InputError("date,keyword,index 열이 필요해요. 검색어만 있는 자료로는 검색 추이를 확인할 수 없습니다.")
    rows=[];seen=set()
    for line in reader:
        try:
            date=datetime.strptime(line["date"].strip(),"%Y-%m-%d").date().isoformat()
            keyword=line["keyword"].strip();value=float(line["index"])
            if not keyword or len(keyword)>100 or not 0<=value<=100:raise ValueError()
            if (date,keyword) in seen:raise InputError("같은 날짜·검색어가 중복됐어요. 원자료를 확인해 주세요.")
            seen.add((date,keyword));rows.append({"date":date,"keyword":keyword,"index":value})
            if len(rows)>5000:raise InputError("한 번에 5000행까지 가져올 수 있어요.")
        except InputError:raise
        except (ValueError,TypeError,KeyError):raise InputError("날짜(YYYY-MM-DD)와 상대지수(0~100)를 확인해 주세요.")
    if not rows:raise InputError("가져올 데이터가 비어 있어요.")
    grouped={}
    for row in rows:grouped.setdefault(row["keyword"],[]).append(row)
    if any(len(v)<2 for v in grouped.values()):raise InputError("변화를 확인하려면 검색어마다 서로 다른 날짜가 두 개 이상 필요해요.")
    return {"source_url":DATALAB_URL,"source_type":"user_imported_datalab_relative_index","independently_verified":False,
            "imported_at":datetime.now(KST).isoformat(),"rows":sorted(rows,key=lambda r:(r["keyword"],r["date"])),
            "period":{"start":min(r["date"] for r in rows),"end":max(r["date"] for r in rows)},
            "note":"사용자가 가져온 상대지수 · 원본 자동 대조 전 · 절대 검색량/내 블로그 유입수 아님"}
