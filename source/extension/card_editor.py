"""Editable layers over the original ten images; no image generation or destructive edits."""
import copy
import math
import re
import shutil
import uuid
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps
from trends import InputError

def valid_asset_set(name):
    return isinstance(name,str) and (name in ("maltipoo-v1","maltipoo-v2") or bool(re.fullmatch(r"maltipoo-editor-[0-9a-f]{12}",name)))

FONTS={"noto":("NotoSansKR-VF.ttf","NotoSansKR-VF.ttf"),"malgun":("NanumGothic-Regular.ttf","NanumGothic-Bold.ttf"),"headline":("DoHyeon-Regular.ttf","DoHyeon-Regular.ttf"),"postcard":("GowunDodum-Regular.ttf","GowunDodum-Regular.ttf")}
FONTS.update(sans=("NotoSansKR[wght].ttf","NotoSansKR[wght].ttf"),serif=("NotoSerifKR[wght].ttf","NotoSerifKR[wght].ttf"),batang=("GowunBatang-Regular.ttf","GowunBatang-Bold.ttf"),hand=("Gaegu-Regular.ttf","Gaegu-Bold.ttf"))
FONT_STYLES={"serif":{"title":"serif","body":"batang"},"sans":{"title":"headline","body":"sans"},"hand":{"title":"hand","body":"postcard"},"clean":{"title":"noto","body":"noto"},"bold":{"title":"headline","body":"noto"},"warm":{"title":"postcard","body":"noto"},"classic":{"title":"malgun","body":"malgun"}}
FONT_STYLES["default"]={"title":"sans","body":"sans"}

def font_path(family="noto",weight=400):
    if family not in FONTS:raise InputError("지원하는 폰트 스타일을 선택해 주세요.")
    filename=FONTS[family][1 if weight>=700 else 0]
    return next(Path(p)/filename for p in (Path(__file__).resolve().parent/"fonts","/mnt/c/Windows/Fonts","C:/Windows/Fonts") if (Path(p)/filename).is_file())

def face(size,weight,family="noto"):
    f=ImageFont.truetype(str(font_path(family,weight)),size)
    if family in ("noto","sans","serif"):f.set_variation_by_axes([weight if a["name"]==b"Weight" else a["default"] for a in f.get_variation_axes()])
    return f

def lines(text,font,width,draw):
    result=[]
    for paragraph in text.split("\n"):
        current=""
        for ch in paragraph:
            if current and draw.textlength(current+ch,font=font)>width:result.append(current);current=""
            current+=ch
        result.append(current)
    return result

def defaults(content):
    result=[]
    for item in content["images"]:
        n=item["order"];texts=[]
        if n<=7:
            texts=[{"id":"title","label":"제목","text":item.get("title","").strip(),"x":80,"y":116,"width":920,"font_size":94,"weight":800,"color":"#FFFFFF","visible":True},
                   {"id":"body","label":"설명","text":"\n".join(t for t in (item.get("message",""),item.get("body","")) if t),"x":84,"y":425,"width":912,"font_size":44,"weight":500,"color":"#FFFFFF","visible":True},
                   {"id":"number","label":"순번","text":f"{n:02d} / 07","x":895,"y":1275,"width":150,"font_size":26,"weight":700,"color":"#FFFFFF","visible":True}]
        result.append({"order":n,"image":{"x":0,"y":0,"scale":1},"shade":{"mode":"dark" if n<=7 else "none","strength":.9,"end":.72},"texts":texts})
    return result

def checked_layout(value,order):
    try:
        if not isinstance(value,dict) or value.get("order")!=order:raise ValueError()
        im=value["image"];shade=value["shade"]
        def number(v,lo,hi):
            if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError()
            return v
        image={"x":number(im["x"],-1080,1080),"y":number(im["y"],-1350,1350),"scale":number(im["scale"],.5,3)}
        if "visible" in im:
            if type(im["visible"])!=bool:raise ValueError()
            image["visible"]=im["visible"]
        if im.get("clip") is not None:
            clip=im["clip"];cx=number(clip["x"],0,1079);cy=number(clip["y"],0,1349)
            image["clip"]={"x":cx,"y":cy,"width":number(clip["width"],1,1080-cx),"height":number(clip["height"],1,1350-cy)}
        background=value.get("background","#F7F3E8")
        if not isinstance(background,str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",background):raise ValueError()
        card_type=value.get("card_type","custom")
        if card_type not in ("custom","photo","split","text"):raise ValueError()
        if shade["mode"] not in ("dark","light","none"):raise ValueError()
        shading={"mode":shade["mode"],"strength":number(shade["strength"],0,1),"end":number(shade["end"],.2,1)}
        if not isinstance(value["texts"],list) or len(value["texts"])>8:raise ValueError()
        result=[];ids=set();draw=ImageDraw.Draw(Image.new("RGB",(1,1)))
        for t in value["texts"]:
            if not re.fullmatch(r"[a-z0-9_-]{1,32}",t["id"]) or t["id"] in ids:raise ValueError()
            ids.add(t["id"])
            if not isinstance(t["text"],str) or len(t["text"])>600 or not isinstance(t["label"],str):raise ValueError()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}",t["color"]) or type(t["visible"])!=bool:raise ValueError()
            x=number(t["x"],0,1070);y=number(t["y"],0,1330);width=number(t["width"],60,1080-x)
            size=number(t["font_size"],20,180);weight=number(t["weight"],400,900)
            if type(size)!=int or type(weight)!=int:raise ValueError()
            family=t.get("font_family","noto")
            if family not in FONTS:raise ValueError()
            font=face(size,weight,family);wrapped=lines(t["text"],font,width,draw)
            if t["visible"] and t["text"] and y+(len(wrapped)-1)*round(size*1.3)+size>1350:raise InputError("글이 카드 아래를 넘어가요. 글자 크기나 위치를 조정해 주세요.")
            if t["visible"] and any(draw.textlength(line,font=font)>width+.5 for line in wrapped):raise InputError("글자보다 글 상자가 좁아요. 상자 너비나 글자 크기를 조정해 주세요.")
            result.append({"id":t["id"],"label":t["label"][:40],"text":t["text"],"x":x,"y":y,"width":width,"font_size":size,"weight":weight,"color":t["color"],"visible":t["visible"]})
            if "font_family" in t:result[-1]["font_family"]=family
        checked={"order":order,"image":image,"shade":shading,"texts":result}
        if "background" in value:checked["background"]=background
        if "card_type" in value:checked["card_type"]=card_type
        return checked
    except InputError:raise
    except (KeyError,TypeError,ValueError):raise InputError("사진 위치·배율과 글자 설정을 확인해 주세요. 글은 카드 안에 배치해야 합니다.")

def draw_text_line(draw,position,text,font,color,size):
    """Keep the user's check emoji legible when the text font has no emoji glyph."""
    if "✅" not in text:
        draw.text(position,text,font=font,fill=color,anchor="lt");return
    x,y=position;prefix=""
    parts=text.split("✅")
    for n,part in enumerate(parts):
        if n:part=part.removeprefix("\ufe0f")
        if part:draw.text((round(x+draw.textlength(prefix,font=font)),y),part,font=font,fill=color,anchor="lt")
        prefix+=part
        if n<len(parts)-1:
            left=x+draw.textlength(prefix,font=font);top=y+size*.08;side=size*.8
            draw.rounded_rectangle((round(left),round(top),round(left+side),round(top+side)),radius=max(2,round(size*.08)),fill="#659A52")
            draw.line([(round(left+side*.19),round(top+side*.51)),(round(left+side*.42),round(top+side*.75)),(round(left+side*.82),round(top+side*.25))],fill="#FFFFFF",width=max(2,round(size*.065)),joint="curve")
            prefix+="✅"

def render(layout,original):
    canvas=Image.new("RGB",(1080,1350),layout.get("background","#F7F3E8"));im=layout["image"]
    if im.get("visible",True):
        photo=ImageOps.fit(Image.open(original).convert("RGB"),(1080,1350),method=Image.Resampling.LANCZOS)
        photo=photo.resize((round(1080*im["scale"]),round(1350*im["scale"])),Image.Resampling.LANCZOS)
        if im.get("clip"):
            layer=canvas.copy();layer.paste(photo,(round(im["x"]),round(im["y"])));clip=im["clip"]
            box=(round(clip["x"]),round(clip["y"]),round(clip["x"]+clip["width"]),round(clip["y"]+clip["height"]))
            canvas.paste(layer.crop(box),box[:2])
        else:canvas.paste(photo,(round(im["x"]),round(im["y"])))
    shade=layout["shade"]
    if shade["mode"]!="none":
        overlay=Image.new("RGBA",canvas.size);d=ImageDraw.Draw(overlay)
        color=(17,42,34) if shade["mode"]=="dark" else (247,243,232)
        for y in range(1350):
            t=y/(1350*shade["end"]);alpha=shade["strength"]*(1-min(1,max(0,(t-.45)/.55)))
            d.line((0,y,1080,y),fill=color+(round(alpha*255),))
        canvas=Image.alpha_composite(canvas.convert("RGBA"),overlay).convert("RGB")
    draw=ImageDraw.Draw(canvas)
    for t in layout["texts"]:
        if not t["visible"]:continue
        f=face(t["font_size"],t["weight"],t.get("font_family","noto"))
        for n,line in enumerate(lines(t["text"],f,t["width"],draw)):
            draw_text_line(draw,(round(t["x"]),round(t["y"])+n*round(t["font_size"]*1.3)),line,f,t["color"],t["font_size"])
    return canvas

def apply_editor(content,root,order=None,layout=None,batch=None,font_style=None,font_bases=None):
    c=copy.deepcopy(content);previous=c.get("card_editor");layouts=copy.deepcopy(previous["layouts"] if previous else defaults(c))
    if batch is not None:
        if not isinstance(batch,list) or len(batch)!=10:raise InputError("전체10장의 배치가 필요해요.")
        layouts=[]
        for n,l in enumerate(batch,1):
            try:layouts.append(checked_layout(l,n))
            except InputError as e:raise InputError(f"{n:02d}번 카드: {e}")
        if font_style is not None and font_style not in FONT_STYLES:raise InputError("폰트 스타일을 확인해 주세요.")
        entries=[{"revision":c["revision"],"order":n,"layout":copy.deepcopy(previous["layouts"][n-1])} for n in range(1,11)] if previous else []
        c["layout_history"]=(c.get("layout_history",[])+entries)[-30:]
    elif order is not None:
        if type(order)!=int or not 1<=order<=10:raise InputError("편집할 카드를 선택해 주세요.")
        checked=checked_layout(layout,order)
        before=copy.deepcopy(layouts[order-1]);layouts[order-1]=checked
        c["layout_history"]=(c.get("layout_history",[])+[{"revision":c["revision"],"order":order,"layout":before}])[-30:]
    layouts=[checked_layout(l,n) for n,l in enumerate(layouts,1)]
    if font_bases is not None:
        if not isinstance(font_bases,list) or len(font_bases)!=10:raise InputError("폰트 기준 배치10개가 필요해요.")
        font_bases=[checked_layout(l,n) for n,l in enumerate(font_bases,1)]
    asset_set="maltipoo-editor-"+uuid.uuid4().hex[:12];out=root/"output"/asset_set;out.mkdir(parents=True)
    for n,l in enumerate(layouts,1):
        path=out/f"{n:02d}.png"
        if previous and batch is None and order is not None and n!=order:
            shutil.copy2(root/"output"/c["asset_set"]/path.name,path)
        else:render(l,root/"output/maltipoo-v1/backgrounds"/path.name).save(path)
        item=c["images"][n-1]
        item["title"]="\n".join(t["text"] for t in l["texts"] if t["visible"] and t["id"]=="title")
        item["message"]="";item["body"]="\n".join(t["text"] for t in l["texts"] if t["visible"] and t["id"]!="title")
    c.update(card_editor={"schema_version":1,"source":"original-ten-v1","layouts":layouts},asset_set=asset_set,revision=c["revision"]+1,design_note="처음 만든 원본10장 유지 · 요소별 편집",approval=None)
    if batch is not None and font_style:c["card_editor"]["font_style"]=font_style
    elif previous and previous.get("font_style"):c["card_editor"]["font_style"]=previous["font_style"]
    if font_bases is not None:c["card_editor"]["font_bases"]=font_bases
    elif previous and previous.get("font_bases"):c["card_editor"]["font_bases"]=previous["font_bases"]
    return c
