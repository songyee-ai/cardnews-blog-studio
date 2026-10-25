"""Validated, human-reviewed research import; not autonomous web research."""
import copy
from urllib.parse import urlparse
from trends import InputError

def validate_research(value, selection):
    if not selection:
        raise InputError("소재를 먼저 선택해 주세요.")
    if not isinstance(value,dict) or value.get("keyword")!=selection["keyword"]:
        raise InputError("조사 자료와 선택한 소재가 다릅니다.")
    sources=value.get("sources",[])
    if not sources or len({s.get("id") for s in sources})!=len(sources):
        raise InputError("중복 없는 근거 목록이 필요해요.")
    ids={s.get("id") for s in sources}
    for s in sources:
        u=urlparse(s.get("url",""))
        if u.scheme!="https" or not u.hostname or u.username or u.password or not s.get("summary") or not s.get("checked_at"):
            raise InputError("원문 주소·확인일·요약을 확인해 주세요.")
    for section in value.get("outline",[]):
        if not section.get("source_ids") or not set(section["source_ids"]).issubset(ids):
            raise InputError("목차마다 확인한 근거를 연결해 주세요.")
    if not value.get("outline") or len(value.get("titles",[]))<2 or not value.get("cards"):
        raise InputError("제목 후보·목차·카드 구성이 필요해요.")
    result=copy.deepcopy(value)
    result.update(method="채팅에서 원문 확인 후 가져온 편집 기획 · 앱 자동 조사 아님",approval=None)
    return result
