const $=id=>document.getElementById(id);let state=null,busy=false,chosen=null;
let editorOptions={tips:{}};
const cardTip=n=>editorOptions.tips[String(n)]||'';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function notice(t,ok=false){$('notice').textContent=t;$('notice').className=ok?'success':'';$('notice').hidden=false;$('notice').scrollIntoView({behavior:'smooth',block:'nearest'});}
async function api(path,data){const r=await fetch(path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({version:state.version,request_id:crypto.randomUUID(),...data})}:{});const v=await r.json();if(!r.ok)throw Error(v.error||'요청을 처리하지 못했어요.');return v;}
async function work(fn){if(busy)return;busy=true;document.querySelectorAll('button').forEach(x=>x.disabled=true);try{await fn();}catch(e){notice(e.message);}finally{busy=false;document.querySelectorAll('button').forEach(x=>x.disabled=false);}}
function render(){const s=state.snapshot;chosen=state.selection?.id||null;$('empty').hidden=!!s;$('source').hidden=!s;$('raw-panel').hidden=!s;
if(s){$('source').innerHTML=`<b>자료 기준 ${esc(s.snapshot_date)}</b> · 반려동물 ${s.rows.length}개<br><a href="${esc(s.source_url)}" target="_blank" rel="noreferrer">공개 목록 원문 ↗</a> · 제3자 스냅샷, 네이버 원본 대조 전<br><span>수집 ${esc(s.observed_at.slice(0,16).replace('T',' '))} · 유입수·검색량·순위 변동 미제공</span>`;$('raw').innerHTML=`<table><thead><tr><th>순위</th><th>검색어</th><th>검색량</th><th>순위 변화</th></tr></thead><tbody>${s.rows.map(r=>`<tr><td>${r.rank}</td><td>${esc(r.keyword)}</td><td>미제공</td><td>미제공</td></tr>`).join('')}</tbody></table>`;}
$('candidates').innerHTML=(state.candidates||[]).map(c=>`<label class="candidate"><div class="candidate-top"><span>공개 목록 ${c.rank}위 · ${esc(c.keyword)}</span><input type="radio" name="topic" value="${c.id}" ${chosen===c.id?'checked':''}></div><h3>${esc(c.suggested_title)}</h3><p>${esc(c.angle)}</p><p class="reason">${esc(c.reason)}</p><p>편집 규칙 기반 제안 · 상승 추세 확인 전</p></label>`).join('');
document.querySelectorAll('[name="topic"]').forEach(el=>el.onchange=()=>{chosen=el.value;$('selection').hidden=false;$('selected').hidden=true;$('angle').value=state.candidates.find(c=>c.id===chosen).angle;});
$('selection').hidden=!chosen;if(chosen)$('angle').value=state.selection.angle;$('selected').hidden=!state.selection;
if(state.selection)$('selected').innerHTML=`<h3>선택한 소재 · ${esc(state.selection.keyword)}</h3><p>${esc(state.selection.angle)}</p><p class="helper">${state.research?'원문 조사와 기획을 아래에서 검토해 주세요.':'원문 조사와 기획을 준비할 차례예요.'} 현재는 원고·이미지 생성 전입니다.</p><a href="/api/brief" target="_blank">저장한 제작 브리프 보기 ↗</a>`;
renderResearch();
renderContent();
const d=state.datalab;$('data-summary').innerHTML=d?`<p><b>${d.rows.length}행 저장됨</b><br>${esc(d.period.start)} ~ ${esc(d.period.end)}<br>${esc(d.note)}</p>`:'';
}
$('collect').onclick=()=>work(async()=>{notice('공개 목록을 읽고 있어요. 실패해도 이전 자료는 유지됩니다.');state=await api('/api/collect',{});render();notice('실제로 읽은 키워드를 저장했어요. 글로 만들 소재를 골라 주세요.',true);});
$('selection').onsubmit=e=>{e.preventDefault();work(async()=>{state=await api('/api/select',{candidate_id:chosen,angle:$('angle').value});render();notice('선택을 저장했어요. 새로고침해도 이어집니다.',true);});};
$('datalab-form').onsubmit=e=>{e.preventDefault();work(async()=>{state=await api('/api/datalab',{csv:$('csv').value});render();notice('자료를 저장했어요. 원본 자동 대조 전의 상대지수 자료로 구분합니다.',true);});};
$('copy-keywords').onclick=()=>work(async()=>{const words=state.selection?[state.selection.keyword]:(state.candidates||[]).map(x=>x.keyword).slice(0,5);if(!words.length)throw Error('공개 목록을 먼저 가져와 주세요.');await navigator.clipboard.writeText(words.join('\n'));notice('비교 후보를 복사했어요. 데이터랩의 주제어 칸에 넣어 주세요.',true);});
Promise.all([api('/api/state'),api('/api/editor-options')]).then(([s,o])=>{state=s;editorOptions=o;render();}).catch(e=>notice(e.message));

function renderResearch(){
if(!$('research'))$('selected').insertAdjacentHTML('afterend','<section id="research" class="research" hidden></section>');
const r=state.research,box=$('research');box.hidden=!r;
document.querySelectorAll('.steps li').forEach((li,i)=>li.classList.toggle('active',i===(r?1:0)));
if(!r)return;
box.innerHTML=`<span class="eyebrow">02 / RESEARCH & PLAN · V${esc(r.revision)}</span><h2>말티푸 입문 가이드, 이렇게 만들까요?</h2><p>${esc(r.angle)}</p><p class="helper">${esc(r.method)}<br>원문 확인 ${esc(r.checked_at)} · 아직 원고·이미지는 제작 전</p><div class="source">${esc(r.trend_note)}</div>
<form id="plan-form"><h3>제목 후보</h3>${r.titles.map((t,i)=>`<label class="title-option"><input type="radio" name="plan-title" value="${i}" ${i===(r.approval?.title_index??r.recommended_title)?'checked':''}> <span>${esc(t)}${i===r.recommended_title?' <small>추천</small>':''}</span></label>`).join('')}
<h3>본문 구성</h3><p class="helper">${esc(r.article_plan)}</p>${r.outline.map(o=>`<article class="outline-item"><h3>${esc(o.heading)}</h3><p>${esc(o.points)}</p><span class="helper">근거 ${o.source_ids.map(esc).join(' · ')}</span></article>`).join('')}
<h3>카드뉴스 7장 구성</h3><ol class="card-plan">${r.cards.map((c,i)=>`<li><b>${esc(c.title)}</b><p>${esc(c.visual)}</p><small class="card-tip">팁 · ${esc(cardTip(i+1))}</small></li>`).join('')}</ol>
<details class="evidence-list"><summary>확인한 원문 ${r.sources.length}개와 적용 범위</summary>${r.sources.map(s=>`<article class="outline-item"><a href="${esc(s.url)}" target="_blank" rel="noreferrer"><b>${esc(s.id)} · ${esc(s.title)} ↗</b></a><p>${esc(s.summary)}</p><p class="helper">${esc(s.kind)} · 확인 ${esc(s.checked_at)}<br>${esc(s.scope)}</p></article>`).join('')}</details>
<details><summary>글에 넣지 않을 표현과 자료의 한계</summary><ul>${[...r.exclusions,...r.limitations].map(t=>`<li>${esc(t)}</li>`).join('')}</ul></details>
<div class="approval"><p>${r.approval?'선택한 제목으로 기획을 승인했어요. 원고 제작을 이어갈 준비가 됐습니다.':'제목과 목차를 확인한 뒤 기획을 승인해 주세요. 승인한 제목과 버전을 저장합니다.'}</p><button class="primary" type="submit">${r.approval?'제목 선택 변경하여 저장':'이 제목과 구성으로 기획 승인'}</button><p class="helper">이 버튼은 기획을 저장합니다. 원고·이미지를 자동 생성하거나 네이버에 발행하지 않습니다.</p></div></form>`;
$('plan-form').onsubmit=e=>{e.preventDefault();work(async()=>{state=await api('/api/approve_plan',{title_index:Number(document.querySelector('[name="plan-title"]:checked').value)});render();notice('기획과 선택한 제목을 저장했어요. 원고·카드 제작을 이어갈 준비가 됐습니다.',true);});};
}

function renderContent(){
if(!$('content-review'))document.querySelector('.grid').insertAdjacentHTML('beforebegin','<section id="content-review" class="content-review" hidden></section>');
const box=$('content-review'),c=state.content;box.hidden=!c;
if(!c)return;
const a=c.audit;const assetSet=c.asset_set||"maltipoo-v1";
$('research').hidden=true;
$('selection').hidden=true;
const scopeNote=document.querySelector('.panel.light p:last-child');
if(scopeNote)scopeNote.textContent='공개 검색어에서 고른 소재로 원고와 AI 이미지 초안을 준비했어요. 발행 전 내용과 실제 광고·협찬 관계를 직접 확인해 주세요.';
document.querySelectorAll('.steps li').forEach((li,i)=>li.classList.toggle('active',i===3));
$('selected').querySelector('.helper').textContent='원고와 이미지 초안이 준비됐어요. 위의 검수 화면에서 확인해 주세요.';
box.innerHTML=`<div class="section-head"><div><span class="eyebrow">04 / REVIEW · V${c.revision}</span><h2>말티푸 블로그, 발행 전 검수</h2></div><span class="review-badge">${c.approval?'검수 승인 · 미발행':'검수 대기 · 미발행'}</span></div><h2 class="draft-title">${esc(c.title)}</h2>
<div class="audit-grid"><div><b>${a.body_chars_no_space.toLocaleString()}자</b><span>본문 공백 제외</span></div><div><b>${a.image_count}장</b><span>카드 7 · 보조 3</span></div><div><b>${a.findings.length}건</b><span>등록 표현 점검 결과</span></div><div><b>${c.hashtags.length}개</b><span>관련 해시태그</span></div></div>
<p class="helper">본문 목표 ${a.body_target.join('~')}자 · ${a.body_in_target?'목표 범위 안':'편집 목표 재확인'} · 본문 내 중심 검색어 ${a.keyword_body_count}회 (반복 횟수 목표 아님)<br>${esc(a.count_scope)}<br>글자 수·이미지 수는 이번 글의 편집 설정이며 네이버 공식 노출 조건이 아닙니다.</p>
<div class="review-actions"><a class="button" href="/editor/">카드 배치 직접 편집 ↗</a><button id="copy-title" class="primary">제목 복사</button><button id="copy-body" class="secondary">본문 복사</button><button id="copy-tags" class="secondary">태그 복사</button><a class="button" href="/api/article-preview" target="_blank">이미지 배치 미리보기 ↗</a><a class="button" href="/api/export">원고·이미지 ZIP 받기</a></div>
<details><summary>작성 기준·표현 점검 확인</summary><p>정확한 제목, 관련 정보, 근거와 읽기 쉬운 구성을 적용했습니다. 네이버 공식 안내에서 이미지 10~15장·특정 최소 글자 수·일괄 금칙어 목록은 확인하지 못했어요.</p><p><a href="https://searchadvisor.naver.com/guide/content-basic" target="_blank" rel="noreferrer">네이버 공식 콘텐츠 안내 ↗</a></p><p>${esc(a.note)} 등록된 ${a.checked_term_count}개 표현을 제목·본문·태그·캡션·카드 문구에서 확인했습니다.</p>${a.findings.length?'<ul>'+a.findings.map(f=>`<li>${esc(f.term)} · ${f.count}회 · ${esc(f.kind)}</li>`).join('')+'</ul>':'<p>등록된 점검 표현은 발견되지 않았어요. 문맥과 내용의 정확성은 직접 검토해 주세요.</p>'}<p>${c.approval?.commercial_relationship==='none'?'협찬·광고 관계 없음 · 사용자 확인 완료.':'협찬·광고 여부는 아직 확인하지 않았습니다. 실제 관계가 있다면 발행 전에 필요한 표시를 추가해 주세요.'}</p></details>
<h3>이미지 10장 · 삽입 위치와 설명</h3><p class="helper">각 이미지를 누르면 원본 PNG를 볼 수 있어요. AI로 제작한 설명 이미지이며 실제 촬영 사진이 아닙니다.</p><div class="image-gallery">${c.images.map(i=>`<figure><a href="/assets/${assetSet}/${String(i.order).padStart(2,'0')}.png" target="_blank"><img src="/assets/${assetSet}/${String(i.order).padStart(2,'0')}.png" alt="${esc(i.alt)}" loading="lazy"></a><figcaption><b>${String(i.order).padStart(2,'0')} · ${esc(i.placement)}</b><br>${esc(i.caption)}<small class="card-tip">팁 · ${esc(cardTip(i.order))}</small></figcaption></figure>`).join('')}</div>
<details class="article-editor"><summary>원고 읽고 수정하기</summary><form id="draft-form"><label>제목<input id="draft-title" type="text" maxlength="120" value="${esc(c.title)}" required></label><label>도입<textarea id="draft-intro" rows="6">${esc(c.intro.join('\n\n'))}</textarea></label>${c.sections.map((s,i)=>`<h3>${esc(s.heading)}</h3><textarea data-section="${i}" rows="9">${esc(s.paragraphs.join('\n\n'))}</textarea>`).join('')}<label>체크리스트 (줄마다 한 항목)<textarea id="draft-checklist" rows="5">${esc(c.checklist.join('\n'))}</textarea></label><label>맺음말<textarea id="draft-closing" rows="4">${esc(c.closing)}</textarea></label><label>해시태그 (공백으로 구분)<textarea id="draft-tags" rows="2">${esc(c.hashtags.join(' '))}</textarea></label><label>추가 회피어 (줄마다 한 항목)<textarea id="draft-avoid" rows="3" placeholder="내 블로그에서 피할 표현이 있으면 입력">${esc(c.writing_settings.custom_avoid_terms.join('\n'))}</textarea></label><button type="submit" class="primary">수정 저장하고 다시 점검</button><p class="helper">수정하면 검수 승인이 해제돼요. 카드의 문구 변경은 이미지도 함께 수정해야 하므로 별도 검토가 필요합니다.</p></form></details>
<p class="helper">${esc(c.disclosure)}</p><details><summary>제작 방법과 원문 확인</summary><p>${esc(c.provenance)}</p><ul>${state.research.sources.map(s=>`<li><a href="${esc(s.url)}" target="_blank" rel="noreferrer">${esc(s.id)} · ${esc(s.title)}</a></li>`).join('')}</ul></details>
<div class="approval"><p>${c.approval?'현재 버전의 검수를 승인했어요. 네이버 등록은 직접 진행합니다.':'원고와 이미지, 삽입 위치를 확인한 뒤 최종 검수를 승인해 주세요.'}</p><button id="approve-draft" class="primary">${c.approval?'현재 버전 검수 승인됨':'이 원고와 이미지 검수 승인'}</button><p class="helper">검수 승인은 제작실에만 저장합니다. 네이버에 발행하지 않습니다.</p></div>`;
const plain=()=>[...c.intro,...c.sections.flatMap(s=>[s.heading,...s.paragraphs]),'우리 집 돌봄 체크리스트',...c.checklist,c.closing].join('\n\n');
for(const [id,text] of [['copy-title',c.title],['copy-body',plain()+'\n\n'+c.disclosure+'\n\n참고한 자료\n'+state.research.sources.map(s=>s.title+'\n'+s.url).join('\n\n')],['copy-tags',c.hashtags.map(t=>'#'+t).join(' ')]])$(id).onclick=()=>work(async()=>{await navigator.clipboard.writeText(text);notice('복사했어요. 네이버 편집기에 붙여 넣어 주세요.',true);});
$('draft-form').onsubmit=e=>{e.preventDefault();work(async()=>{const paragraphs=t=>t.split(/\n\s*\n/).map(x=>x.trim()).filter(Boolean);const sections=c.sections.map((s,i)=>({...s,paragraphs:paragraphs(document.querySelector(`[data-section="${i}"]`).value)}));state=await api('/api/edit_content',{title:$('draft-title').value,intro:paragraphs($('draft-intro').value),sections,checklist:$('draft-checklist').value.split('\n').map(x=>x.trim()).filter(Boolean),closing:$('draft-closing').value,hashtags:$('draft-tags').value.split(/\s+/).map(t=>t.replace(/^#/, '')).filter(Boolean),avoid_terms:$('draft-avoid').value.split('\n').map(x=>x.trim()).filter(Boolean)});render();notice('수정본을 저장하고 글자 수와 등록 표현을 다시 점검했어요.',true);});};
$('approve-draft').disabled=!!c.approval;
$('approve-draft').onclick=()=>work(async()=>{state=await api('/api/approve_content',{});render();notice('최종 검수 승인을 저장했어요. 네이버에는 아직 발행되지 않았습니다.',true);});
}


