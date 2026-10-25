import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw
from app import ROOT,Store
from card_editor import defaults,checked_layout,apply_editor,valid_asset_set,face,FONT_STYLES,render,draw_text_line
from editor_options import options
from trends import InputError

class EditorTests(unittest.TestCase):
    def test_check_emoji_export_and_plain_text_unchanged(self):
        font=face(55,400,'sans')
        image=Image.new('RGB',(700,100),'#173e32')
        draw_text_line(ImageDraw.Draw(image),(10,10),'✅ 매일 돌봄',font,'#ffffff',55)
        self.assertGreater(sum(pixel==(101,154,82) for pixel in image.getdata()),100)
        a=Image.new('RGB',(700,100),'white');b=a.copy()
        draw_text_line(ImageDraw.Draw(a),(10,10),'매일 돌봄',font,'#173e32',55)
        ImageDraw.Draw(b).text((10,10),'매일 돌봄',font=font,fill='#173e32',anchor='lt')
        self.assertEqual(a.tobytes(),b.tobytes())

    def setUp(self):
        self.c=json.loads((ROOT/"maltipoo-content.json").read_text(encoding="utf-8"))
    def test_layout_rejects_nonfinite_invalid_colors_overflow_and_order(self):
        base=defaults(self.c)[0]
        self.assertEqual(checked_layout(base,1),base)
        for mutate in (lambda x:x["image"].update(scale=float('nan')),lambda x:x["image"].update(scale=20),lambda x:x["texts"][0].update(color="url(x)"),lambda x:x["texts"][0].update(y=1300),lambda x:x.update(order=2)):
            bad=copy.deepcopy(base);mutate(bad)
            with self.assertRaises(InputError):checked_layout(bad,1)
        self.assertFalse(valid_asset_set("../../outside"));self.assertTrue(valid_asset_set("maltipoo-editor-1234abcdef12"))
    def test_font_styles_presets_and_hidden_photo_render(self):
        base=defaults(self.c)[6]
        for style in FONT_STYLES.values():
            candidate=copy.deepcopy(base)
            for t in candidate["texts"]:t["font_family"]=style["title"] if t["id"]=="title" else style["body"]
            self.assertTrue(checked_layout(candidate,7))
            self.assertGreater(face(60,800,style["title"]).getlength("말티푸"),0)
        for kind,preset in options()["types"].items():
            candidate=copy.deepcopy(base)
            candidate.update(card_type=kind,background=preset["background"],image=preset["image"],shade=preset["shade"])
            for t in candidate["texts"]:
                t.update(preset["roles"][t["id"]]);t["color"]=preset["color"]
            self.assertTrue(checked_layout(candidate,7))
        candidate["image"]["visible"]=False
        for t in candidate["texts"]:t["visible"]=False
        image=render(candidate,Path("not-an-image.png"))
        self.assertEqual(image.getpixel((500,900)),(23,62,50))
        bad=copy.deepcopy(base);bad["texts"][0]["font_family"]="unregistered"
        with self.assertRaises(InputError):checked_layout(bad,7)
        bad=copy.deepcopy(base);bad["image"]["clip"]={"x":0,"y":640,"width":1080,"height":1000}
        with self.assertRaises(InputError):checked_layout(bad,7)
    def test_save_preserves_original_and_previous_png_and_restores_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);raw=root/"output/maltipoo-v1/backgrounds";raw.mkdir(parents=True)
            for n in range(1,11):Image.new("RGB",(80,100),(30+n*9,90,70)).save(raw/f"{n:02d}.png")
            before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.glob("*.png")}
            first=apply_editor(self.c,root);old=root/"output"/first["asset_set"]/"01.png";oldbytes=old.read_bytes()
            layout=copy.deepcopy(first["card_editor"]["layouts"][0]);layout["image"].update(x=-50,y=20,scale=1.2);layout["texts"][0]["font_size"]=80
            nextc=apply_editor(first,root,1,layout)
            self.assertNotEqual(first["asset_set"],nextc["asset_set"])
            self.assertEqual(old.read_bytes(),oldbytes)
            self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in raw.glob("*.png")})
            self.assertEqual(nextc["layout_history"][0]["layout"],first["card_editor"]["layouts"][0])
            store=Store(root/"test.sqlite3")
            with store.db() as db:
                state=store.get();state.update(content=nextc,research=json.loads((ROOT/"maltipoo-research.json").read_text(encoding="utf-8")))
                db.execute("UPDATE state SET body=? WHERE id=1",(json.dumps(state,ensure_ascii=False),))
            self.assertEqual(Store(store.path).get()["content"]["card_editor"]["layouts"][0]["image"]["scale"],1.2)
            request={"version":state["version"],"request_id":"editor-save","order":1,"layout":layout}
            with patch("app.ROOT",root):
                saved=store.mutate("save_layout",request)
                self.assertEqual(store.mutate("save_layout",request),saved)
                bad=copy.deepcopy(layout);bad["image"]["scale"]=99
                with self.assertRaises(InputError):store.mutate("save_layout",{"version":saved["version"],"request_id":"bad","order":1,"layout":bad})
                self.assertEqual(store.get(),saved)
                batch=copy.deepcopy(saved["content"]["card_editor"]["layouts"])
                coordinates=[[(t["x"],t["y"],t["font_size"]) for t in l["texts"]] for l in batch]
                for l in batch:
                    for t in l["texts"]:t["font_family"]="headline" if t["id"]=="title" else "noto"
                allsaved=store.mutate("save_layouts",{"version":saved["version"],"request_id":"all-fonts","layouts":batch,"font_style":"bold","font_bases":batch})
                self.assertEqual(allsaved["content"]["card_editor"]["font_style"],"bold")
                self.assertEqual(allsaved["content"]["card_editor"]["font_bases"],batch)
                self.assertEqual(coordinates,[[ (t["x"],t["y"],t["font_size"]) for t in l["texts"]] for l in allsaved["content"]["card_editor"]["layouts"]])
                badbatch=copy.deepcopy(batch);badbatch[8]["image"]["scale"]=99
                files_before=set((root/"output").iterdir())
                with self.assertRaisesRegex(InputError,"09번"):
                    store.mutate("save_layouts",{"version":allsaved["version"],"request_id":"bad-all","layouts":badbatch,"font_style":"bold"})
                self.assertEqual(store.get(),allsaved);self.assertEqual(files_before,set((root/"output").iterdir()))
                with self.assertRaises(InputError):
                    store.mutate("save_layouts",{"version":allsaved["version"],"request_id":"bad-bases","layouts":batch,"font_bases":batch[:9]})
                self.assertEqual(store.get(),allsaved);self.assertEqual(files_before,set((root/"output").iterdir()))
                single=store.mutate("save_layout",{"version":allsaved["version"],"request_id":"single-after-font","order":1,"layout":batch[0]})
                self.assertEqual(single["content"]["card_editor"]["font_bases"],batch)

if __name__=="__main__":unittest.main()
