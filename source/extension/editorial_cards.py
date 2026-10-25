"""Blog-specific typographic layout; independent of the class gradient theme."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageOps

W,H=1080,1350
PAPER="#F5F3ED";INK="#183A31";ACCENT="#DAF08B"
FONTS=["/mnt/c/Windows/Fonts/NotoSansKR-VF.ttf","C:/Windows/Fonts/NotoSansKR-VF.ttf"]

def face(size,weight=800):
    f=ImageFont.truetype(next(p for p in FONTS if Path(p).is_file()),size)
    f.set_variation_by_axes([weight if a["name"]==b"Weight" else a["default"] for a in f.get_variation_axes()])
    return f

def text(d,xy,value,size,fill=INK,weight=800,spacing=1.2):
    font=face(size,weight);x,y=xy;boxes=[]
    for line in value.split("\n"):
        box=d.textbbox((x,y),line,font=font,anchor="lt")
        if box[2]>1008:raise ValueError(f"Line too wide: {line}")
        d.text((x,y),line,font=font,fill=fill,anchor="lt");boxes.append(list(box));y+=round(size*spacing)
    return y,boxes

def photo(path,size,box=None):
    im=Image.open(path).convert("RGB")
    if box:
        iw,ih=im.size;im=im.crop(tuple(round(v*(iw if i%2==0 else ih)) for i,v in enumerate(box)))
    return ImageOps.fit(im,size,method=Image.Resampling.LANCZOS,centering=(.5,.45))

def render_card(card,backgrounds):
    n=card["order"];canvas=Image.new("RGB",(W,H),PAPER);boxes=[]
    if n==1:
        canvas=photo(backgrounds/"08.png",(W,H));overlay=Image.new("RGBA",(W,H));od=ImageDraw.Draw(overlay)
        # Darkening is a layout scrim for white type; the illustration stays full bleed.
        for y in range(H):
            a=round(210*max(0,(y-480)/(H-480))**.75)
            od.line((0,y,W,y),fill=(7,24,19,a))
        canvas=Image.alpha_composite(canvas.convert("RGBA"),overlay).convert("RGB");d=ImageDraw.Draw(canvas)
        text(d,(76,66),"멍글  /  초보 보호자 가이드",30,INK,700)
        text(d,(76,914),"함께 살기 전 알아둘 것",36,"#FFFFFF",600)
        _,boxes=text(d,(72,982),card["title"],106,"#FFFFFF",900,1.15)
        text(d,(76,1272),"저장하고 가족과 함께 확인해요",29,"#FFFFFF",500)
    elif n==7:
        canvas=Image.new("RGB",(W,H),INK);d=ImageDraw.Draw(canvas)
        text(d,(78,72),"06  /  우리 집 준비 체크",32,ACCENT,700)
        _,boxes=text(d,(72,170),card["title"],104,"#FFFFFF",900,1.2)
        for j,line in enumerate(card["checks"]):
            y=510+j*132;d.rounded_rectangle((78,y,139,y+61),radius=16,fill=ACCENT)
            text(d,(94,y+6),str(j+1),38,INK,900)
            text(d,(170,y+3),line,49,"#FFFFFF",700)
        d.line((78,958,1002,958),fill="#557268",width=2)
        text(d,(78,1018),card["body"],48,"#FFFFFF",600,1.55)
        text(d,(78,1245),"체크리스트를 저장해 두세요",30,ACCENT,600)
    else:
        d=ImageDraw.Draw(canvas)
        text(d,(78,70),card["eyebrow"],32,INK,700)
        _,boxes=text(d,(72,154),card["title"],card.get("headline_size",104),INK,900,1.2)
        d.rounded_rectangle((78,438,350,450),radius=6,fill=ACCENT)
        text(d,(78,491),card["body"],46,INK,500,1.5)
        # Crop only within the typography renderer to place the existing art, no new art generated.
        im=photo(backgrounds/f"{n:02d}.png",(924,548),card.get("photo_box",[0,.40,1,1]))
        canvas.paste(im,(78,678));d=ImageDraw.Draw(canvas)
        text(d,(78,1265),"초보 보호자 돌봄 노트",28,INK,500)
    d=ImageDraw.Draw(canvas)
    text(d,(920,1272),f"{n:02d} / 07",26,"#FFFFFF" if n in (1,7) else INK,700)
    return canvas,{"order":n,"headline_size":106 if n==1 else card.get("headline_size",104),"body_size":48 if n==7 else 46,"headline_boxes":boxes,"canvas":[W,H]}
