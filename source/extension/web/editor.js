const $=id=>document.getElementById(id),clone=v=>JSON.parse(JSON.stringify(v));
let state,current=0,selected='title',layouts=[],saved=[],dirty=new Set(),undos={},images={},drag=null,busy=false,ready=false;
let editorOptions,previewLayout=null,fontSnapshot=null,pendingFontStyle=null;
let typographyBases=[],typographyLast=[];
const fontLoads=new Map();
const fontNames={noto:'EditorNoto',malgun:'EditorMalgun',headline:'EditorHeadline',postcard:'EditorPostcard',sans:'EditorSans',serif:'EditorSerif',batang:'EditorBatang',hand:'EditorHand'};
const canvas=$('canvas'),ctx=canvas.getContext('2d'),boxes={};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const layout=()=>layouts[current],target=()=>selected==='image'?layout().image:layout().texts.find(t=>t.id===selected);
function notice(t,error=false){$('notice').textContent=t;$('notice').className=error?'error':'';}
function push(){(undos[current]??=[]).push(clone(layout()));if(undos[current].length>50)undos[current].shift();}
function changed(){if(JSON.stringify(layout())===JSON.stringify(saved[current]))dirty.delete(current);else dirty.add(current);draw();nav();}
function wrapped(text,width){const lines=[];for(const p of text.split('\n')){let line='';for(const ch of p){if(line&&ctx.measureText(line+ch).width>width){lines.push(line);line='';}line+=ch;}lines.push(line);}return lines;}
function draw(showSelection=true){
if(!ready||!layout()||!images[current])return;
const l=previewLayout||layout();ctx.clearRect(0,0,1080,1350);ctx.fillStyle=l.background||'#f7f3e8';ctx.fillRect(0,0,1080,1350);
const im=images[current],p=l.image,iw=im.naturalWidth,ih=im.naturalHeight,ratio=Math.max(1080/iw,1350/ih),sw=1080/ratio,sh=1350/ratio;
if(p.visible!==false){ctx.save();if(p.clip){ctx.beginPath();ctx.rect(p.clip.x,p.clip.y,p.clip.width,p.clip.height);ctx.clip();}ctx.drawImage(im,(iw-sw)/2,(ih-sh)/2,sw,sh,p.x,p.y,1080*p.scale,1350*p.scale);ctx.restore();}
const s=l.shade;if(s.mode!=='none'){const g=ctx.createLinearGradient(0,0,0,1350*s.end),rgb=s.mode==='dark'?'17,42,34':'247,243,232';g.addColorStop(0,`rgba(${rgb},${s.strength})`);g.addColorStop(.45,`rgba(${rgb},${s.strength})`);g.addColorStop(1,`rgba(${rgb},0)`);ctx.fillStyle=g;ctx.fillRect(0,0,1080,1350);}
for(const key of Object.keys(boxes))delete boxes[key];
for(const t of l.texts){ctx.font=`${t.weight} ${t.font_size}px ${fontNames[t.font_family||'noto']}`;const lines=wrapped(t.text,t.width),height=Math.max(t.font_size,(lines.length-1)*Math.round(t.font_size*1.3)+t.font_size);boxes[t.id]={x:t.x,y:t.y,w:t.width,h:height};if(!t.visible)continue;ctx.fillStyle=t.color;ctx.textBaseline='alphabetic';for(let n=0;n<lines.length;n++){const line=lines[n],ascent=ctx.measureText(line).actualBoundingBoxAscent||t.font_size*.8;ctx.fillText(line,t.x,t.y+n*Math.round(t.font_size*1.3)+ascent);}}
if(showSelection&&!previewLayout){const b=selected==='image'?(p.visible===false?null:{x:p.x,y:p.y,w:1080*p.scale,h:1350*p.scale}):boxes[selected];if(b){ctx.save();ctx.strokeStyle='#78bdff';ctx.lineWidth=3;ctx.setLineDash([12,6]);ctx.strokeRect(b.x,b.y,b.w,b.h);ctx.setLineDash([]);if(selected!=='image'){ctx.fillStyle='#78bdff';ctx.fillRect(b.x+b.w-10,b.y+b.h-10,20,20);}ctx.restore();}}
const overflow=l.texts.filter(t=>t.visible&&t.text&&boxes[t.id].y+boxes[t.id].h>1350);
$('overflow').textContent=overflow.length?'카드 아래를 넘는 글이 있어요: '+overflow.map(t=>t.label).join(', '):'';
}
function nav(){ $('cards').innerHTML=layouts.map((l,i)=>`<button class="${i===current?'active':''}" data-card="${i}">${String(i+1).padStart(2,'0')}${dirty.has(i)?' ·':''}</button>`).join('');document.querySelectorAll('[data-card]').forEach(b=>b.onclick=()=>openCard(Number(b.dataset.card)));$('card-title').textContent=`${String(current+1).padStart(2,'0')} / 10 · ${current<7?'카드뉴스':'보조 이미지'}`;$('dirty').textContent=dirty.has(current)?'저장 전 변경 있음':'저장된 배치';$('undo').disabled=!(undos[current]?.length);}
function controls(){const l=layout();if(selected!=='image'&&!l.texts.some(t=>t.id===selected))selected=l.texts[0]?.id||'image';$('element').innerHTML='<option value="image">사진</option>'+l.texts.map(t=>`<option value="${t.id}">${esc(t.label)}${t.visible?'':' (숨김)'}</option>`).join('');$('element').value=selected;const image=selected==='image',t=target();$('photo-options').hidden=!image;$('text-options').hidden=image;$('remove').disabled=image;$('property-title').textContent=image?'사진 위치와 크기':'텍스트 설정';for(const k of ['x','y']){$(k).value=Math.round(t[k]);$(k).min=image?(k==='x'?-1080:-1350):0;$(k).max=k==='x'?1080:1350;}$('scale').value=l.image.scale;$('scale-label').textContent=Math.round(l.image.scale*100)+'%';if(!image){if(document.activeElement!==$('text'))$('text').value=t.text;$('width').value=Math.round(t.width);$('font-size').value=t.font_size;$('font-label').textContent=t.font_size+'px';$('weight').value=t.weight;$('color').value=t.color;$('visible').checked=t.visible;}$('shade-mode').value=l.shade.mode;$('shade-strength').value=l.shade.strength;$('shade-label').textContent=Math.round(l.shade.strength*100)+'%';$('shade-end').value=l.shade.end;$('end-label').textContent=Math.round(l.shade.end*100)+'%';const history=(state.content.layout_history||[]).filter(h=>h.order===current+1).reverse();$('history').innerHTML=history.length?history.map((h,i)=>`<option value="${i}">원고 v${h.revision} 저장 전 배치</option>`).join(''):'<option value="">이전 저장 없음</option>';$('restore').disabled=!history.length;$('png').href=`/assets/${state.content.asset_set}/${String(current+1).padStart(2,'0')}.png`;}
async function openCard(i){previewLayout=null;previewUI(false);current=i;selected=layouts[i].texts[0]?.id||'image';if(!images[i]){const im=new Image();im.src=`/editor-original/${String(i+1).padStart(2,'0')}.png`;await im.decode();images[i]=im;}nav();controls();draw();}
async function api(path,data){const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:state.version,request_id:crypto.randomUUID(),...data})}:{}),v=await r.json();if(!r.ok)throw Error(v.error||'저장하지 못했어요.');return v;}
function edit(fn){if(busy||previewLayout)return;push();fn();changed();controls();}
$('element').onchange=()=>{selected=$('element').value;controls();draw();};
$('quick-save').onclick=()=>$(pendingFontStyle?'save-all':'save').click();
$('preview-size').onclick=()=>{document.body.classList.toggle('large-preview');$('preview-size').textContent=document.body.classList.contains('large-preview')?'화면에 맞춤':'보기 확대';};
for(const k of ['x','y'])$(k).onchange=()=>edit(()=>{let v=Number($(k).value);if(!Number.isFinite(v))return;const t=target(),image=selected==='image';t[k]=Math.max(image?(k==='x'?-1080:-1350):0,Math.min(k==='x'?1080:1330,v));if(!image&&k==='x'){t.x=Math.min(t.x,1020);t.width=Math.min(t.width,1080-t.x);}});
$('scale').oninput=()=>edit(()=>{const p=layout().image,n=Number($('scale').value);p.x+=(1080*p.scale-1080*n)/2;p.y+=(1350*p.scale-1350*n)/2;p.scale=n;});
$('center').onclick=()=>edit(()=>layout().image={x:0,y:0,scale:1});
for(const [id,key,parse] of [['text','text',String],['width','width',Number],['font-size','font_size',Number],['weight','weight',Number],['color','color',String]])$(id).oninput=()=>edit(()=>{target()[key]=parse($(id).value);});
$('visible').onchange=()=>edit(()=>target().visible=$('visible').checked);
for(const [id,key] of [['shade-mode','mode'],['shade-strength','strength'],['shade-end','end']])$(id).oninput=()=>edit(()=>layout().shade[key]=key==='mode'?$(id).value:Number($(id).value));
$('add').onclick=()=>{if(layout().texts.length>=8)return notice('카드당 텍스트는 8개까지 추가할 수 있어요.',true);edit(()=>{const id='text_'+Date.now();layout().texts.push({id,label:'추가 텍스트',text:'새 텍스트',x:80,y:800,width:700,font_size:48,weight:700,color:'#FFFFFF',visible:true});selected=id;});};
$('remove').onclick=()=>{if(selected==='image')return;edit(()=>{layout().texts=layout().texts.filter(t=>t.id!==selected);selected=layout().texts[0]?.id||'image';});};
$('undo').onclick=()=>{if(!undos[current]?.length)return;layouts[current]=undos[current].pop();changed();controls();};
$('reset').onclick=()=>edit(()=>{layouts[current]=clone(saved[current]);});
$('reset').textContent='저장된 배치로';
$('restore').onclick=()=>{const history=(state.content.layout_history||[]).filter(h=>h.order===current+1).reverse(),h=history[Number($('history').value)];if(h)edit(()=>layouts[current]=clone(h.layout));};
$('save').onclick=async()=>{if(busy)return;if(previewLayout)return notice('유형 미리보기를 적용하거나 취소해 주세요.',true);if(pendingFontStyle)return notice('전체 폰트 변경은 전체 카드 저장으로 반영해 주세요.',true);const savedIndex=current,savedLayout=clone(layout());busy=true;$('save').disabled=true;notice('배치를 저장하고 PNG를 만들고 있어요.');try{state=await api('/api/save_layout',{order:savedIndex+1,layout:savedLayout,font_bases:typographyBases});saved=clone(state.content.card_editor.layouts);dirty.delete(savedIndex);for(let i=0;i<10;i++)if(!dirty.has(i))layouts[i]=clone(saved[i]);nav();controls();draw();notice('저장했어요. 검수 화면·PNG·ZIP에 이 배치가 반영됐습니다.');}catch(e){notice(e.message+' 편집 중인 배치는 화면에 유지했습니다.',true);}finally{busy=false;$('save').disabled=false;}};
for(const id of ['png','zip'])$(id).onclick=e=>{if((id==='png'&&dirty.has(current))||(id==='zip'&&dirty.size)){e.preventDefault();notice('저장 전 편집이 있어요. 현재 카드를 저장한 뒤 내려받아 주세요.',true);}};
const point=e=>{const r=canvas.getBoundingClientRect();return{x:(e.clientX-r.left)*1080/r.width,y:(e.clientY-r.top)*1350/r.height};};
canvas.onpointerdown=e=>{if(busy||previewLayout||!ready)return;e.preventDefault();const p=point(e),b=boxes[selected];if(selected!=='image'&&b&&Math.abs(p.x-b.x-b.w)<32&&Math.abs(p.y-b.y-b.h)<32){push();drag={type:'width',start:p,old:clone(target())};}else{selected=[...layout().texts].reverse().find(t=>{const b=boxes[t.id];return t.visible&&b&&p.x>=b.x&&p.x<=b.x+b.w&&p.y>=b.y&&p.y<=b.y+b.h;})?.id||'image';push();drag={type:'move',start:p,old:clone(target())};}canvas.setPointerCapture(e.pointerId);canvas.focus({preventScroll:true});controls();draw();};
canvas.onpointermove=e=>{if(!drag)return;const p=point(e),t=target(),dx=p.x-drag.start.x,dy=p.y-drag.start.y;if(drag.type==='width')t.width=Math.round(Math.max(60,Math.min(1080-t.x,drag.old.width+dx)));else{const image=selected==='image';t.x=Math.round(Math.max(image?-1080:0,Math.min(image?1080:1080-t.width,drag.old.x+dx)));t.y=Math.round(Math.max(image?-1350:0,Math.min(image?1350:Math.max(0,1350-(boxes[selected]?.h||100)),drag.old.y+dy)));}changed();$('x').value=t.x;$('y').value=t.y;if(selected!=='image')$('width').value=t.width;};
canvas.onpointerup=canvas.onpointercancel=()=>{drag=null;controls();};
canvas.onkeydown=e=>{if(busy||previewLayout)return;const moves={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};if(moves[e.key]){e.preventDefault();edit(()=>{const d=e.shiftKey?10:1,[dx,dy]=moves[e.key],t=target(),im=selected==='image';t.x=Math.max(im?-1080:0,Math.min(im?1080:1080-t.width,t.x+dx*d));t.y=Math.max(im?-1350:0,Math.min(im?1350:Math.max(0,1350-(boxes[selected]?.h||100)),t.y+dy*d));});}};
window.addEventListener('beforeunload',e=>{if(dirty.size){e.preventDefault();e.returnValue='';}});
async function loadFonts(families=['noto']){await Promise.all([...new Set(families)].map(family=>{if(!fontLoads.has(family)){const promise=Promise.all([400,700].map(weight=>document.fonts.load(`${weight} 48px ${fontNames[family]}`,'말티푸 가나다'))).then(results=>{if(results.some(r=>!r.length))throw Error('missing font');}).catch(()=>{fontLoads.delete(family);throw Error(`${family} 글꼴을 브라우저에서 읽지 못했어요.`);});fontLoads.set(family,promise);}return fontLoads.get(family);}));}
function fontSample(preset){const title=$('font-sample-title'),body=$('font-sample-body');if(!preset)return;title.style.fontFamily=fontNames[preset.title];title.style.fontWeight=preset.title_weight;body.style.fontFamily=fontNames[preset.body];body.style.fontWeight=preset.body_weight;}
function cardFontHint(){if(!ready)return;$('font-card-hint').textContent=layout().texts.some(t=>t.visible&&t.text)?'전체 카드의 글꼴을 바꿉니다. 저장은 별도입니다.':'이 카드는 글이 없는 사진 카드예요. 위 샘플이나 1~7번 카드에서 서체 변화를 확인하세요.';}
function lockInputs(on){for(const el of document.querySelectorAll('#layer-settings input,#layer-settings select,#layer-settings textarea,#layer-settings button,#background-settings input,#background-settings select,#series-style button,#series-style select,#card-type-settings select'))el.disabled=on;}
function previewUI(on){$('type-preview-banner').hidden=!on;lockInputs(on);}
const originalControls=controls;controls=function(){originalControls();const l=layout();$('composition-tip').textContent='팁 · '+(editorOptions.tips[String(current+1)]||'핵심 정보와 사진이 서로 가리지 않게 배치해 주세요.');$('card-type').value=l.card_type||'custom';$('type-description').textContent=editorOptions.types[l.card_type]?.description||'현재 요소를 직접 편집합니다.';cardFontHint();$('photo-visible').checked=l.image.visible!==false;$('background-color').value=l.background||'#f7f3e8';const t=target();if(selected!=='image')$('weight').disabled=['headline','postcard'].includes(t.font_family);$('font-cancel').disabled=!fontSnapshot;$('font-note').textContent=pendingFontStyle?'폰트 변경됨 · 전체 카드 저장 필요':'현재 저장된 폰트와 배치를 유지하고 있어요.';};
function presetLayout(id){const p=editorOptions.types[id];if(!p)throw Error('카드 유형을 골라 주세요.');const l=clone(layout());Object.assign(l,{card_type:id,background:p.background,image:clone(p.image),shade:clone(p.shade)});for(const t of l.texts){const role=t.id==='title'?'title':t.id==='number'?'number':'body';if(p.roles[t.id])Object.assign(t,p.roles[role]);t.color=p.color;if(id==='text'&&l.order===7&&t.id==='body')t.text=t.text.replaceAll(' · ','\n');}return l;}
function textHeight(t){ctx.font=`${t.weight} ${t.font_size}px ${fontNames[t.font_family||'noto']}`;return Math.max(t.font_size,(wrapped(t.text,t.width).length-1)*Math.round(t.font_size*1.3)+t.font_size);}
function tuneTypography(base,preset){
const result=clone(base);
for(const t of result.texts){const title=t.id==='title',number=t.id==='number';t.font_family=title?preset.title:preset.body;t.weight=title?preset.title_weight:preset.body_weight;if(!number)t.font_size=Math.max(20,Math.min(180,Math.round(t.font_size*((title?preset.title_scale:preset.body_scale)||1))));}
const beforeTitle=base.texts.find(t=>t.id==='title'&&t.visible),beforeBody=base.texts.find(t=>t.id==='body'&&t.visible),title=result.texts.find(t=>t.id==='title'&&t.visible),body=result.texts.find(t=>t.id==='body'&&t.visible);
if(title&&body&&beforeTitle&&beforeBody&&beforeBody.y>beforeTitle.y){
const gap=Math.max(preset.gap||72,Math.min(120,beforeBody.y-beforeTitle.y-textHeight(beforeTitle)));
const bottom=result.card_type==='split'?Math.min(1235,(result.image.clip?.y||1280)-32):1235;
for(let n=0;n<340;n++){body.y=Math.round(title.y+textHeight(title)+gap);if(body.y+textHeight(body)<=bottom)break;const canTitle=title.font_size>Math.min(28,beforeTitle.font_size),canBody=body.font_size>Math.min(28,beforeBody.font_size);if(!canTitle&&!canBody)break;if(canTitle&&(!canBody||textHeight(title)>=textHeight(body)))title.font_size--;else body.font_size--;}
}
for(const t of result.texts){if(!t.visible||t.id==='number')continue;const original=base.texts.find(b=>b.id===t.id);const minSize=Math.min(28,original.font_size);const bottom=result.card_type==='split'&&t.id!=='title'?Math.min(1235,(result.image.clip?.y||1280)-32):1235;while(t.font_size>minSize&&t.y+textHeight(t)>bottom)t.font_size--;}
return result;
}
$('card-type').onchange=()=>{
if(busy)return;const id=$('card-type').value;
try{if(id==='custom')edit(()=>layout().card_type='custom');else{const base=presetLayout(id);let next=clone(base);const active=editorOptions.font_styles.find(p=>p.id===(pendingFontStyle||state.content.card_editor.font_style));if(active)next=tuneTypography(next,active);edit(()=>layouts[current]=next);typographyBases[current]=clone(base);typographyLast[current]=clone(next);if(fontSnapshot){fontSnapshot.base[current]=clone(base);fontSnapshot.last[current]=clone(next);fontSnapshot.initial[current]=clone(next);}}
$('type-description').textContent=editorOptions.types[id]?.description||'현재 요소를 직접 편집합니다.';
notice('선택한 유형을 현재 카드에 반영했어요. 되돌리기로 복원할 수 있으며 저장 전에는 저장본이 바뀌지 않습니다.');
}catch(e){notice(e.message,true);}
};
$('type-preview').onclick=()=>{if(busy)return;try{previewLayout=presetLayout($('card-type').value);previewUI(true);draw();notice('유형 미리보기입니다. 적용 전에는 현재 배치가 바뀌지 않아요.');}catch(e){notice(e.message,true);}};
$('type-cancel').onclick=()=>{previewLayout=null;previewUI(false);controls();draw();notice('미리보기를 취소하고 현재 배치를 유지했어요.');};
$('type-apply').onclick=()=>{if(!previewLayout)return;const next=clone(previewLayout);previewLayout=null;previewUI(false);edit(()=>layouts[current]=next);notice('현재 카드에만 적용했어요. 저장하면 검수본에 반영됩니다.');};
$('photo-visible').onchange=()=>edit(()=>{layout().image.visible=$('photo-visible').checked;layout().card_type='custom';});
$('background-color').oninput=()=>edit(()=>layout().background=$('background-color').value);
async function applyFontStyle(){
if(busy||previewLayout)return notice('다른 미리보기나 저장을 마친 뒤 폰트를 선택해 주세요.',true);
const preset=editorOptions.font_styles.find(p=>p.id===$('font-style').value);
if(!preset)return notice('전체 폰트 스타일을 골라 주세요.',true);
busy=true;lockInputs(true);$('font-load-status').textContent='선택한 글꼴을 준비하고 있어요…';notice('선택한 글꼴을 읽고 있어요. 현재 편집은 유지합니다.');
try{
await loadFonts([preset.title,preset.body]);
if(!fontSnapshot)fontSnapshot={style:pendingFontStyle,base:clone(typographyBases),last:clone(typographyLast),initial:clone(layouts),families:layouts.map(l=>Object.fromEntries(l.texts.map(t=>[t.id,{present:Object.hasOwn(t,'font_family'),value:t.font_family,weight:t.weight}])))};
pendingFontStyle=preset.id;
for(let i=0;i<layouts.length;i++){
const base=clone(layouts[i]);for(const t of base.texts){const original=fontSnapshot.base[i].texts.find(x=>x.id===t.id),last=fontSnapshot.last[i].texts.find(x=>x.id===t.id),initial=fontSnapshot.initial[i].texts.find(x=>x.id===t.id);if(original&&last)for(const key of ['font_size','x','y','width']){if(t[key]===last[key])t[key]=original[key];else{original[key]=t[key];if(initial)initial[key]=t[key];}}}
layouts[i]=tuneTypography(base,preset);fontSnapshot.last[i]=clone(layouts[i]);
if(JSON.stringify(layouts[i])===JSON.stringify(saved[i]))dirty.delete(i);else dirty.add(i);
}
fontSample(preset);controls();nav();draw();$('font-load-status').textContent='적용됨 · '+preset.description;notice(layout().texts.some(t=>t.visible&&t.text)?'선택한 폰트를 전체 카드에 반영했어요. 줄바꿈을 확인한 뒤 전체 카드 저장을 눌러 주세요.':'전체 카드에 폰트를 반영했어요. 현재 카드는 사진 전용이므로 서체 샘플이나 1~7번에서 확인하세요.');
}catch(e){$('font-load-status').textContent='글꼴 준비 실패 · 다시 선택해 주세요.';notice(e.message+' 기존 편집은 유지됩니다.',true);}
finally{busy=false;lockInputs(false);controls();}
};
$('font-style').onchange=()=>{const p=editorOptions.font_styles.find(x=>x.id===$('font-style').value);$('font-style-detail').textContent=p?p.description+' · '+p.intent:'기존 개별 설정을 유지합니다.';if(p)applyFontStyle();else if(fontSnapshot)$('font-cancel').click();};
$('font-cancel').onclick=()=>{if(!fontSnapshot)return;for(let i=0;i<layouts.length;i++){for(const t of layouts[i].texts){const old=fontSnapshot.families[i][t.id];if(old?.present)t.font_family=old.value;else delete t.font_family;if(old?.weight)t.weight=old.weight;const initial=fontSnapshot.initial?.[i].texts.find(x=>x.id===t.id),last=fontSnapshot.last?.[i].texts.find(x=>x.id===t.id);if(initial&&last)for(const key of ['font_size','x','y','width'])if(t[key]===last[key])t[key]=initial[key];}if(JSON.stringify(layouts[i])===JSON.stringify(saved[i]))dirty.delete(i);else dirty.add(i);}pendingFontStyle=fontSnapshot.style;fontSnapshot=null;$('font-style').value=editorOptions.font_styles.some(p=>p.id===state.content.card_editor.font_style)?state.content.card_editor.font_style:'';const p=editorOptions.font_styles.find(p=>p.id===$('font-style').value);$('font-style-detail').textContent=p?p.description+' · '+p.intent:'기존 개별 설정을 유지합니다.';fontSample(p);$('font-load-status').textContent='저장된 글꼴로 복원했어요.';controls();nav();draw();notice('폰트 변경을 취소했어요. 글 내용과 위치 편집은 유지합니다.');};
$('save-all').onclick=async()=>{if(busy)return;if(previewLayout)return notice('유형 미리보기를 먼저 적용하거나 취소해 주세요.',true);busy=true;$('save-all').disabled=true;notice('10장의 배치와 글 넘침을 확인하고 전체 PNG를 만들고 있어요.');try{state=await api('/api/save_layouts',{layouts:clone(layouts),font_style:pendingFontStyle||state.content.card_editor.font_style||null,font_bases:fontSnapshot?fontSnapshot.base:typographyBases});saved=clone(state.content.card_editor.layouts);layouts=clone(saved);typographyBases=clone(state.content.card_editor.font_bases||saved);typographyLast=clone(saved);dirty.clear();fontSnapshot=null;pendingFontStyle=null;nav();controls();draw();notice('전체 카드를 저장했어요. 원고와 원본 사진은 유지됐습니다.');}catch(e){notice(e.message+' 현재 화면의 편집은 유지됩니다.',true);}finally{busy=false;$('save-all').disabled=false;}};
(async()=>{try{[state,editorOptions]=await Promise.all([api('/api/state'),api('/api/editor-options')]);if(!state.content)throw Error('먼저 제작실에서 카드뉴스를 준비해 주세요.');if(!state.content.card_editor)state=await api('/api/init_editor',{});layouts=clone(state.content.card_editor.layouts);saved=clone(layouts);typographyBases=clone(state.content.card_editor.font_bases||layouts);typographyLast=clone(saved);$('font-style').innerHTML='<option value="" disabled>개별 설정</option>'+editorOptions.font_styles.map(p=>`<option value="${p.id}">${esc(({default:'기본',serif:'세리프',sans:'산세리프',hand:'손글씨'})[p.id]||p.label)}</option>`).join('');$('card-type').innerHTML='<option value="custom">직접 편집</option>'+Object.entries(editorOptions.types).map(([id,p])=>`<option value="${id}">${esc(p.label)}</option>`).join('');const active=editorOptions.font_styles.find(p=>p.id===state.content.card_editor.font_style);if(active){$('font-style').value=active.id;$('font-style-detail').textContent=active.description+' · '+active.intent;}await loadFonts(layouts.flatMap(l=>l.texts.map(t=>t.font_family||'noto')));ready=true;fontSample(active||editorOptions.font_styles.find(p=>p.id==='default'));await openCard(0);Promise.all(editorOptions.font_styles.map(p=>loadFonts([p.title,p.body]).catch(()=>null)));notice('옵션을 선택하면 화면에 바로 반영됩니다. 저장 전에는 저장본이 바뀌지 않아요.');}catch(e){notice(e.message,true);}})();








