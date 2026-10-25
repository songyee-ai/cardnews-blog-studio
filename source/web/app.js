const $ = id => document.getElementById(id);
let project = null, busy = false, pollTimer = null, pollFailures = 0;
const running = new Set(['researching','verifying','continuing','planning','revising']);
const boardStates = ['storyboard_ready','storyboard_approved','images_partial','images_ready','final_approved'];
const colorNames = {'#24384A':'딥네이비','#1E1E1E':'검정','#FFFFFF':'흰색'};
const statusNames = {final_approved:'최종 승인됨 · 내려받기 가능',revising:'카드 하나 고치는 중',images_partial:'배경 이미지 일부 준비',images_ready:'배경 이미지 준비됨',planning:'카드별 기획 중',storyboard_ready:'기획 검토 대기',storyboard_approved:'기획 승인됨',ready:'조사 준비',researching:'실제 조사 중',verifying:'원문 확인 중',continuing:'답변 반영 중',selecting:'소식 선택 중',waiting_for_user:'내 답변 대기 중',brief_ready:'편집 방향 저장됨',error:'다시 시도 필요',interrupted:'작업 중단됨',cancelled:'취소됨'};
const escapeHTML = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const requestId = () => crypto.randomUUID();
const sourceLink = url => {try {const u=new URL(url);return u.protocol==='https:' ? `<a href="${escapeHTML(u.href)}" target="_blank" rel="noopener noreferrer">원문 열기 ↗</a>`:'';}catch(_){return '';}};
async function api(path,data) {
  const res = await fetch(path,data===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result = await res.json(); if(!res.ok) throw new Error(result.error || '요청을 완료하지 못했어요. 다시 시도해 주세요.'); return result;
}
function displayError(message){$('error').textContent=message;$('error').hidden=false;}
async function perform(work) {
  if(busy) return; busy=true;$('error').hidden=true;clearTimeout(pollTimer);
  document.querySelectorAll('button,#candidates input').forEach(b=>b.disabled=true);
  try {await work();} catch(e){displayError(e.message);if(project){try{project=await api('/api/projects/'+project.id);render();}catch(_){}}}
  finally{busy=false;document.querySelectorAll('button,#candidates input').forEach(b=>b.disabled=false);refreshButtons();schedulePoll();}
}
async function listProjects(){
  const list=await api('/api/projects');
  $('projects').innerHTML=list.map(p=>`<button class="project ${project?.id===p.id?'active':''}" data-id="${p.id}">${escapeHTML(p.topic)}<small>${escapeHTML(statusNames[p.status] || p.status)}</small></button>`).join('');
  $('projects').querySelectorAll('button').forEach(b=>b.onclick=()=>perform(async()=>{project=await api('/api/projects/'+b.dataset.id);localStorage.setItem('cardnews-project',project.id);$('notice').textContent='저장한 프로젝트를 불러왔어요.';render();await listProjects();}));
}
function modeBanner(mode){const real=mode==='claude';$('mode-title').textContent=real?'실제 조사 모드 · Claude':'모의 데이터 모드';$('mode-description').textContent=real?'Claude가 웹 검색과 원문 확인을 수행합니다. 생성 배경은 카드별로 가져와 문구와 별도로 편집합니다.':'표시되는 소식은 가상 예시입니다. 실제 검색·원문 확인·카드 제작을 수행하지 않습니다.';$('mode-banner').classList.toggle('live',real);}
function pickerMode(){const mode=document.querySelector('input[name=mode]:checked').value;$('start-button').textContent=mode==='claude'?'최근 소식 조사하기 →':'모의 후보 보기 →';if(!project)modeBanner(mode);}
document.querySelectorAll('input[name=mode]').forEach(i=>i.onchange=pickerMode);
function step(active){for(const x of ['topic','select','question','brief','final'])$('step-'+x).classList.toggle('active',x===active);}
function fresh(){clearTimeout(pollTimer);project=null;localStorage.removeItem('cardnews-project');$('start').hidden=false;$('workspace').hidden=true;$('notice').textContent='';$('error').hidden=true;step('topic');pickerMode();document.querySelectorAll('.project').forEach(b=>b.classList.remove('active'));$('topic').focus();}
function refreshButtons(){
 $('next').disabled=busy || !project || !project.selected_ids.length || project.status!=='selecting';
 const radio=document.querySelector('input[name=direction]:checked');$('submit-answer').disabled=busy || !radio || (radio.value==='__custom__' && !$('custom-answer').value.trim());
 $('build-story').disabled=busy || project?.mode!=='claude' || project?.status!=='brief_ready';
 $('approve-story').disabled=busy || project?.status!=='storyboard_ready';
 $('revise-story').disabled=busy || !boardStates.includes(project?.status);
 document.querySelectorAll('.edit-story-save,.layout-save').forEach(b=>b.disabled=busy || !boardStates.includes(project?.status));
 document.querySelectorAll('.import-image-save').forEach(b=>b.disabled=busy || !project?.storyboard || project.storyboard.approved_version!==project.storyboard.version);
 const board=project?.storyboard, approvedBoard=board && board.approved_version===board.version;
 $('fix-submit').disabled=busy || !approvedBoard || !['storyboard_approved','images_partial','images_ready','final_approved'].includes(project?.status);
 $('approve-final').disabled=busy || project?.status!=='images_ready' || !approvedBoard || cardsWithErrors().length>0;
 $('reapprove-story').disabled=busy || project?.status!=='storyboard_ready';$('verify-export').disabled=busy || project?.status!=='final_approved';
}
function schedulePoll(){clearTimeout(pollTimer);if(project && running.has(project.status))pollTimer=setTimeout(poll,2000);}
async function poll(){
 if(busy || !project || !running.has(project.status)){schedulePoll();return;}
 const id=project.id;
 try{const next=await api('/api/projects/'+id);if(busy || project?.id!==id)return;const changed=JSON.stringify(project)!==JSON.stringify(next);project=next;if(changed)render();pollFailures=0;if(!running.has(project.status)){await listProjects();$('notice').textContent=project.status==='error'?'작업을 완료하지 못했습니다. 아래 안내를 확인해 주세요.':'작업 결과를 저장했어요. 다음 선택을 확인해 주세요.';}}
 catch(e){pollFailures++;if(pollFailures>=3)displayError('서버 응답을 확인하지 못했어요. 서버 실행 상태와 연결을 확인한 뒤 새로고침해 주세요.');}
 finally{schedulePoll();}
}
async function change(action,extra={}){project=await api(`/api/projects/${project.id}/${action}`,{version:project.version,request_id:requestId(),...extra});render();await listProjects();}
function render(){
 if(!project)return;
 modeBanner(project.mode);$('start').hidden=true;$('workspace').hidden=false;$('project-topic').textContent=project.topic;$('save-state').textContent='이 PC에 저장됨';
 const real=project.mode==='claude',t=project.period;
 $('period').textContent=`${real?'조사':'예정 조사'} 기간 ${t.start} ~ ${t.end} · ${t.timezone} · 기준 ${t.as_of.slice(0,16).replace('T',' ')}${real?'':' / 현재 실제 검색 없음'}`;
 $('selection-view').hidden=project.status!=='selecting';$('question-view').hidden=project.status!=='waiting_for_user';$('brief-view').hidden=project.status!=='brief_ready';
 $('storyboard-view').hidden=!project.storyboard;
 $('running-view').hidden=!running.has(project.status);$('job-error-view').hidden=!['error','interrupted','cancelled','ready'].includes(project.status);
 $('running-title').textContent=statusNames[project.status] || '';$('latest-event').textContent=(project.events||[]).at(-1)||'';$('job-error-text').textContent=project.error || '아직 조사를 시작하지 않았어요. 아래 버튼으로 시작할 수 있습니다.';
 $('retry-job').textContent=project.status==='ready'?'실제 조사 시작':'저장한 내용으로 다시 시도';
 $('event-panel').hidden=!(project.events||[]).length;
 $('events').innerHTML=(project.events||[]).map(e=>`<li>${escapeHTML(e)}</li>`).join('');
 if(running.has(project.status)){step(project.status==='researching'?'select':project.status==='planning'?'brief':'question');}
 if(project.status==='selecting'){
  step('select');$('selected-count').textContent=`${project.selected_ids.length} / 3개 선택`;
  $('selection-help').textContent=project.selected_ids.length?'선택한 후보는 자동 저장됩니다.':'소식을 선택하면 다음 단계로 갈 수 있어요.';
  $('candidate-note').textContent=real?`실제 조사 후보 ${project.candidates.length}개입니다. 원문을 열어 핵심 날짜와 조건을 직접 대조해 주세요.`:`가상 후보 ${project.candidates.length}개입니다. 실제 최신 소식으로 인용하지 마세요.`;
  $('research-notes').textContent=(project.research_notes||'').replace(/후보\s*\d+\s*개만 반환/, '후보 '+project.candidates.length+'개 반환').replaceAll('source_read=false','원문 읽기 미확인');
  $('research-notes-panel').hidden=!project.research_notes;
  $('expand-period').hidden=!(real && project.candidates.length<7 && (t.days||7)===7);
  $('next').textContent=real?'선택한 소식 심층 확인 →':'방향 정하기 →';
  $('candidates').innerHTML=project.candidates.map(c=>`<article class="candidate"><label><div class="candidate-header"><span>${escapeHTML(c.category)} · ${real?'실제 조사':'가상 예시'}</span><input type="checkbox" value="${c.id}" aria-label="${escapeHTML(c.title)} 선택" ${project.selected_ids.includes(c.id)?'checked':''}></div><h3>${escapeHTML(c.title)}</h3></label><p>${escapeHTML(c.summary)}</p><p><b>선택할 가치</b> · ${escapeHTML(c.value)}</p>${real?`<p>게시일 ${escapeHTML(c.published_at||'미확인')} · 발표·변경일 ${escapeHTML(c.event_at||'미확인')}</p><p class="source">${sourceLink(c.source_url)}<span>${c.source_read?'원문 응답·근거 요약 있음 (검토 필요)':'원문 읽기 미확인'}</span></p><p>${escapeHTML(c.evidence)}</p>`:''}<p class="uncertainty">${escapeHTML(c.uncertainty||'추가 조건은 심층 조사에서 확인합니다.')}</p></article>`).join('');
  $('candidates').querySelectorAll('input').forEach(input=>input.onchange=()=>perform(async()=>{const ids=Array.from($('candidates').querySelectorAll('input:checked')).map(i=>i.value);if(ids.length>3){input.checked=false;throw new Error('소식은 최대 3개까지 선택할 수 있어요.');}$('save-state').textContent='저장 중…';project=await api(`/api/projects/${project.id}/selection`,{candidate_ids:ids,version:project.version,request_id:requestId()});render();}));
 }else if(project.status==='waiting_for_user'){
  step('question');const q=project.question;$('question-text').textContent=q.text;
  $('options').innerHTML=q.options.map(o=>`<label class="option"><input type="radio" name="direction" value="${escapeHTML(o.value)}"><span><b>${escapeHTML(o.value)}</b>${o.recommended?'<em class="recommended">추천</em>':''}<small>${escapeHTML(o.detail)}</small></span></label>`).join('');
  document.querySelector('input[value="__custom__"]').checked=false;$('custom-answer').value='';$('custom-answer').disabled=true;$('recommendation').textContent=q.recommendation||'';
  document.querySelectorAll('input[name=direction]').forEach(i=>i.onchange=()=>{const custom=document.querySelector('input[name=direction]:checked')?.value==='__custom__';$('custom-answer').disabled=!custom;if(custom)$('custom-answer').focus();refreshButtons();});
 }else if(project.status==='brief_ready'){
  step('brief');const titles=project.candidates.filter(c=>project.selected_ids.includes(c.id)).map(c=>c.title).join(' / ');
  $('brief-note').textContent=real?'실제 원문 조사와 사용자 선택을 반영한 편집 방향입니다. 아직 카드 제작은 시작하지 않았습니다.':'여기까지는 모의 화면과 저장 흐름을 확인하는 단계입니다.';
  $('brief').innerHTML=[['대상 독자',project.audience],[real?'선택한 소식':'선택한 가상 소식',titles],['전달 목적',project.editorial_goal||project.answer?.text||'조사 결과에 따라 AI가 추천'],['비교할 형식',project.formats.join(' · ')]].map(([k,v])=>`<dt>${escapeHTML(k)}</dt><dd>${escapeHTML(v)}</dd>`).join('');
  const b=project.editorial_brief;
  $('editorial').innerHTML=b?`<h3>${escapeHTML(b.recommended_format)} 추천</h3><p>${escapeHTML(b.reason)}</p><p class="muted">${escapeHTML(b.format_comparison)}</p><h3>표지 문장 후보</h3><ol>${b.hooks.map(h=>`<li>${escapeHTML(h)}</li>`).join('')}</ol><h3>핵심 사실과 사용 조건</h3>${b.facts.map(f=>`<div class="fact"><span class="tag">${{fact:'확인한 사실',company_claim:'발표 주체의 주장',unknown:'미확인'}[f.kind]||'검토 필요'}</span><p>${escapeHTML(f.text)}</p>${sourceLink(f.source_url)}</div>`).join('')}<h3>한계·추가 확인</h3><p>${escapeHTML(b.limitations)}</p>`:'';
  $('story-start-form').hidden=!real;$('story-size').value=project.card_size||'1080x1350';
  $('next-step-title').textContent=real?'다음 단계: 카드별 기획 검토':'다음 단계: 실제 조사 엔진 연결';
  $('next-step-note').textContent=real?'아래에서 카드 크기를 정하고 기획을 만들어 보세요. 기획을 확인하고 승인하기 전에는 이미지를 만들지 않습니다.':'실제 원문 조사와 카드 기획을 연결해야 합니다. 아직 실제 조사·스토리보드·이미지·다운로드는 실행되지 않았습니다.';
 }
 if(project.storyboard)renderStoryboard();
 renderFinal();
 refreshButtons();
}
function cardsWithErrors(){return (project?.storyboard?.cards||[]).filter(c=>(project.renders?.[c.id]?.checks||[]).some(x=>x.level==='error'));}
function renderFinal(){
 const board=project.storyboard,renders=project.renders||{};
 $('final-view').hidden=!board || !Object.keys(renders).length;
 if($('final-view').hidden)return;
 if(!running.has(project.status))step('final');
 const cards=board.cards,ready=cards.filter(c=>renders[c.id]),final=project.status==='final_approved';
 $('final-count').textContent=`카드 PNG ${ready.length}/${cards.length}장`;
 const needs=cards.filter(c=>project.image_results?.[c.id]?.status==='needs_image').map(c=>c.order);
 $('final-status').textContent=final?`최종 승인됨 (${project.final_approval.approved_at.slice(0,16).replace('T',' ')}). 아래에서 내려받을 수 있어요.`:board.approved_version!==board.version?'카드 문구가 바뀌어 기획 승인이 풀렸어요. 바뀐 카드를 확인한 뒤 ‘고친 기획 승인’을 눌러 주세요.':ready.length<cards.length?`배경이 준비된 카드만 PNG로 만들었어요. 남은 카드: ${cards.filter(c=>!renders[c.id]).map(c=>c.order+'번').join(', ')}${needs.length?` (다시 만들 그림: ${needs.join(', ')}번)`:''}.`:'모든 카드 PNG가 준비됐어요. 넘겨 보며 확인한 뒤 최종 승인해 주세요.';
 $('phone-cards').innerHTML=cards.map(c=>renders[c.id]?`<figure><img src="/api/projects/${project.id}/renders/${c.id}?v=${renders[c.id].sha256}" alt="${c.order}번 카드 ${escapeHTML(c.title)}"><figcaption>${c.order}/${cards.length} · ${escapeHTML(c.title)}</figcaption></figure>`:`<figure class="missing"><div>${c.order}번 카드<br>배경 준비 전</div><figcaption>${c.order}/${cards.length} · ${escapeHTML(c.title)}</figcaption></figure>`).join('');
 $('render-checks').innerHTML=ready.map(c=>`<li><b>${c.order}번</b>${renders[c.id].checks.map(x=>`<span class="check ${x.level}">${escapeHTML(x.text)}</span>`).join('')}</li>`).join('');
 const selected=$('fix-card').value;$('fix-card').innerHTML=cards.map(c=>`<option value="${c.id}">${c.order}번 · ${escapeHTML(c.title)}</option>`).join('');if(cards.some(c=>c.id===selected))$('fix-card').value=selected;
 const fix=project.card_fix;$('fix-result').textContent=!fix?'':project.status==='revising'?`${fix.order}번 카드를 고치는 중이에요.`:fix.error?`${fix.order}번 카드 고치기 실패: ${fix.error} 다른 카드와 승인한 내용은 그대로예요.`:fix.result?`${fix.order}번 카드 ${fix.result.change==='text'?'글을 고쳤어요':'그림을 다시 만들도록 표시했어요'}: ${fix.result.reason}`:fix.scope==='image'?(project.image_results?.[fix.card_id]?.status==='ready'?`${fix.order}번 카드에 새 배경을 적용했어요. 다른 카드는 그대로예요.`:`${fix.order}번 카드 그림을 다시 만들도록 표시했어요. 위쪽 ${fix.order}번 카드에 새 배경을 가져와 주세요.`):'';
 $('reapprove-story').hidden=project.status!=='storyboard_ready';
 const errors=cardsWithErrors();
 $('final-help').textContent=final?'카드를 고치면 최종 승인이 풀리고 다시 승인해야 내려받을 수 있어요.':errors.length?`${errors.map(c=>c.order+'번').join(', ')} 카드의 글자가 잘려 최종 승인할 수 없어요.`:'최종 승인 전에는 내려받기가 열리지 않아요.';
 $('downloads').hidden=!final;
 if(final){$('download-zip').href=`/api/projects/${project.id}/export.zip`;$('download-pngs').innerHTML='카드별 PNG · '+cards.map(c=>`<a href="/api/projects/${project.id}/renders/${c.id}?download=1">${c.order}번</a>`).join(' ');}
 const check=project.export_check;$('export-check').hidden=!check;
 if(check){const names={pass:'통과',fail:'실패',unverified:'확인 못 함 · 직접 확인'};const count=k=>check.items.filter(i=>i.result===k).length;$('export-check').innerHTML=`<caption>내보낸 ZIP 검사 ${check.checked_at.slice(0,16).replace('T',' ')} · 통과 ${count('pass')} · 실패 ${count('fail')} · 확인 못 함 ${count('unverified')}</caption>`+check.items.map(i=>`<tr class="${i.result}"><th>${escapeHTML(i.name)}</th><td>${names[i.result]}</td><td>${escapeHTML(i.detail)}</td></tr>`).join('');}
}
function renderStoryboard(){
 if(!running.has(project.status))step('brief');
 const board=project.storyboard, editable=boardStates.includes(project.status);
 const approved=board.approved_version===board.version && ['storyboard_approved','images_partial','images_ready','final_approved'].includes(project.status);
 const imageCount=board.cards.filter(c=>project.image_results?.[c.id]?.status==='ready').length;
 $('story-version').textContent=`${board.cards.length}장 · 기획 v${board.version} · ${(board.card_size||project.card_size||'미정').replace('x','×')}`;
 $('story-design').textContent=`${board.format} · ${board.design_direction}`;
 $('story-status').textContent=approved?`기획 승인됨 · 배경 이미지 ${imageCount}/${board.cards.length}장 준비됨. 배경이 있는 카드는 PNG로 만들었어요.`:(editable?'아직 승인하지 않은 기획입니다. 문구와 출처를 확인해 주세요.':'이전 기획을 보관하고 있습니다. 현재 작업이 끝난 뒤 다시 검토할 수 있어요.');
 $('story-review-notes').textContent=/(indexed_facts|fact_refs|kind=)/.test(board.review_notes)?'발표일과 조사 기준일, 프리뷰·지역·요금제 조건, 제목의 과장 여부, 모바일에서의 줄바꿈을 확인해 주세요.':board.review_notes;
 $('storyboard-actions').hidden=!editable;
 $('story-cards').innerHTML=board.cards.map(c=>{const image=project.image_results?.[c.id],rendered=project.renders?.[c.id],layout=rendered?.layout||project.layouts?.[c.id];return `<article class="story-card"><div class="story-label">${String(c.order).padStart(2,'0')} / ${escapeHTML(c.role)}</div>${rendered?`<img class="story-render" src="/api/projects/${project.id}/renders/${c.id}?v=${rendered.sha256}" alt="${c.order}번 완성 카드 미리보기">`:''}<div ${rendered?'hidden ':''}class="story-canvas ${(board.card_size||project.card_size)==='1080x1080'?'square':''} ${image?.status==='ready'?'has-image':''}">${image?.status==='ready'?`<img class="story-background" src="/api/projects/${project.id}/images/${c.id}?v=${image.sha256}" alt="${escapeHTML(c.role)} 설명용 생성 이미지">`: ''}<span class="story-preview-badge">${image?.status==='ready'?'생성 배경 적용 · 문구 미리보기':'기획 미리보기 · 그림 생성 전'}</span><h3>${escapeHTML(c.title)}</h3><strong>${escapeHTML(c.message)}</strong><p>${escapeHTML(c.body)}</p><small>조사 기준 ${escapeHTML(project.period.as_of.slice(0,10))} · ${c.order}/${board.cards.length}</small></div><div class="story-card-meta"><p><b>그림 계획</b><br>${escapeHTML(c.image_brief)}</p><p><b>근거</b> · ${c.source_urls.map(u=>sourceLink(u)).join(' · ')}</p>${c.edited_by_user?'<p class="edited-note">직접 수정한 문구입니다. 원문과 다시 대조해 주세요.</p>':''}<details><summary>이 카드 문구 직접 수정</summary><form class="edit-story-form" data-card-id="${c.id}"><label>제목 (45자 이내)<input name="title" value="${escapeHTML(c.title)}" maxlength="45" required ${editable?'':'disabled'}></label><label>핵심 문장 (75자 이내)<textarea name="message" maxlength="75" required ${editable?'':'disabled'}>${escapeHTML(c.message)}</textarea></label><label>본문 (180자 이내)<textarea name="body" maxlength="180" rows="4" required ${editable?'':'disabled'}>${escapeHTML(c.body)}</textarea></label><button class="secondary edit-story-save" type="submit">이 카드 문구 저장</button></form></details>${rendered?`<details><summary>글자 배치 조정</summary><form class="layout-form" data-card-id="${c.id}" data-theme="${layout.theme||''}">${layout.theme=== 'ivory-gradient'?`<input type="hidden" name="theme" value="ivory-gradient"><p>고딕 제목 · 그라데이션 배경 · 순번 자동 색상</p><label>그림 세로 위치 (px)<input type="number" name="image_offset_y" min="-200" max="300" value="${layout.image_offset_y}"></label>`:''}<label>글자 위치<select name="position"><option value="top" ${layout.position==='top'?'selected':''}>위쪽 여백</option><option value="bottom" ${layout.position==='bottom'?'selected':''}>아래쪽 여백</option><option value="full" ${layout.position==='full'?'selected':''}>넓게 (그림이 작은 카드)</option></select></label><label>제목 크기 (44~80px)<input type="number" name="title_size" min="44" max="80" value="${layout.title_size}"></label><label>본문 크기 (26~44px)<input type="number" name="body_size" min="26" max="44" value="${layout.body_size}"></label><label>글자색<select name="text_color">${Object.entries(colorNames).map(([v,n])=>`<option value="${v}" ${layout.text_color===v?'selected':''}>${n}</option>`).join('')}</select></label><label>글자 뒤 상자 진하기 (0~0.95)<input type="number" name="panel" min="0" max="0.95" step="0.05" value="${layout.panel}"></label><button class="secondary layout-save" type="submit">이 카드 배치 저장</button></form></details>`:''}<details class="import-details"><summary>${image?.status==='ready'?'이 카드 생성 이미지 교체':'이 카드 생성 이미지 가져오기'}</summary>${image?.status==='needs_image'?`<p class="edited-note">그림 다시 만들기 요청: ${escapeHTML(image.reason)}</p><pre class="image-prompt">이전 프롬프트\n${escapeHTML(image.previous_prompt)}</pre>`:''}<form class="import-image-form" data-card-id="${c.id}"><label>생성한 배경 파일 (16MB 이하)<input type="file" name="image" accept="image/png,image/jpeg,image/webp" required ${approved?'':'disabled'}></label><label>생성 도구<input name="generator" maxlength="200" placeholder="예: OpenAI image_gen (ChatGPT)" required ${approved?'':'disabled'}></label><label>생성 프롬프트·사용 조건<textarea name="prompt" rows="3" maxlength="10000" placeholder="실제 사용한 생성 요청과 출처 기록" ${approved?'':'disabled'}></textarea></label><button class="secondary import-image-save" type="submit" ${approved?'':'disabled'}>이 카드에 이미지 적용</button></form>${approved?'':'<p>이미지를 가져오려면 현재 기획을 먼저 승인해 주세요.</p>'}</details>${image?.status==='ready'?`<details><summary>이미지 생성 기록</summary><p>${escapeHTML(image.generator)} · ${image.width}×${image.height} · ${escapeHTML(image.created_at.slice(0,10))}</p><p>${escapeHTML(image.explanation)}</p><pre class="image-prompt">${escapeHTML(image.prompt)}</pre></details>`:''}</div></article>`;}).join('');
 document.querySelectorAll('.import-image-form').forEach(form=>form.onsubmit=e=>{e.preventDefault();perform(async()=>{
  const file=form.querySelector('input[type=file]').files[0];if(!file)throw new Error('생성한 이미지 파일을 골라 주세요.');if(file.size>16*1024*1024)throw new Error('이미지는 16MB 이하여야 합니다.');
  const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('이미지 파일을 읽지 못했습니다.'));reader.readAsDataURL(file);});
  const fields=new FormData(form);await change('import-image',{card_id:form.dataset.cardId,image_base64:encoded,generator:fields.get('generator'),prompt:fields.get('prompt')||''});$('notice').textContent='실제 이미지 파일 검사를 통과했어요. 글자는 별도로 수정할 수 있습니다.';
 });});
 document.querySelectorAll('.layout-form').forEach(form=>form.onsubmit=e=>{e.preventDefault();perform(async()=>{const d=new FormData(form);await change('layout-card',{card_id:form.dataset.cardId,position:d.get('position'),title_size:Number(d.get('title_size')),body_size:Number(d.get('body_size')),text_color:d.get('text_color'),panel:Number(d.get('panel')),theme:d.get('theme')||undefined,image_offset_y:d.get('theme')?Number(d.get('image_offset_y')):undefined});$('notice').textContent='이 카드의 글자 배치만 바꿨어요. 배경 그림과 다른 카드는 그대로입니다.';});});
 document.querySelectorAll('.edit-story-form').forEach(form=>form.onsubmit=e=>{e.preventDefault();perform(async()=>{const data=new FormData(form);await change('edit-card',{card_id:form.dataset.cardId,storyboard_version:project.storyboard.version,title:data.get('title'),message:data.get('message'),body:data.get('body')});$('notice').textContent='이 카드의 문구를 저장했어요. 다른 카드는 유지했고 기존 기획 승인은 해제했습니다.';});});
}
$('story-start-form').onsubmit=e=>{e.preventDefault();perform(()=>change('storyboard',{card_size:$('story-size').value}));};
$('story-revision-form').onsubmit=e=>{e.preventDefault();perform(()=>change('storyboard',{card_size:project.storyboard.card_size||project.card_size,feedback:$('story-feedback').value.trim()}));};
$('approve-story').onclick=$('reapprove-story').onclick=()=>perform(()=>change('approve',{stage:'storyboard',storyboard_version:project.storyboard.version}));
$('approve-final').onclick=()=>perform(async()=>{await change('approve',{stage:'final',render_signature:project.render_signature});$('notice').textContent='최종 승인했어요. 카드 PNG와 ZIP을 내려받을 수 있습니다.';});
$('verify-export').onclick=()=>perform(async()=>{await change('verify-export');$('notice').textContent='내보낸 ZIP 파일을 직접 열어 검사했어요. 확인 못 한 항목은 직접 확인해 주세요.';});
$('fix-form').onsubmit=e=>{e.preventDefault();perform(async()=>{await change('fix-card',{card_id:$('fix-card').value,storyboard_version:project.storyboard.version,request:$('fix-request').value.trim(),scope:document.querySelector('input[name=fix-scope]:checked').value});$('fix-request').value='';$('notice').textContent=project.status==='revising'?'고칠 카드 하나의 요청을 Claude에 전달했어요.':'이 카드의 그림만 다시 만들도록 표시했어요. 다른 카드는 그대로입니다.';});};
$('new-project').onclick=()=>{if(!busy)fresh();};$('another').onclick=fresh;
$('topic-form').onsubmit=e=>{e.preventDefault();perform(async()=>{project=await api('/api/projects',{topic:$('topic').value,mode:document.querySelector('input[name=mode]:checked').value});localStorage.setItem('cardnews-project',project.id);if(project.mode==='claude')await change('research');else{render();await listProjects();}$('notice').textContent=project.mode==='claude'?'실제 웹 조사를 시작했어요. 진행 내역을 확인할 수 있습니다.':'가상 후보를 준비했어요. 실제 최신 소식으로 인용하지 마세요.';});};
$('next').onclick=()=>perform(()=>change('next'));
$('expand-period').onclick=()=>perform(()=>change('expand'));
$('cancel-job').onclick=()=>perform(()=>change('cancel'));
$('retry-job').onclick=()=>perform(()=>change(project.status==='ready'?'research':'retry'));
$('custom-answer').oninput=refreshButtons;
$('answer-form').onsubmit=e=>{e.preventDefault();perform(async()=>{const radio=document.querySelector('input[name=direction]:checked');if(!radio)return;const answer=radio.value==='__custom__'?$('custom-answer').value.trim():radio.value;await change('answers',{question_id:project.question.id,question_version:project.question.version,answer});$('notice').textContent=project.mode==='claude'?'저장한 답변을 같은 Claude 세션에 전달했어요.':'답변을 저장했어요. 새로고침해도 같은 프로젝트가 이어집니다.';});};
perform(async()=>{const saved=localStorage.getItem('cardnews-project');if(saved){try{project=await api('/api/projects/'+saved);render();}catch(e){localStorage.removeItem('cardnews-project');$('notice').textContent='저장한 프로젝트를 찾지 못했어요. 새로 시작해 주세요.';}}else{step('topic');pickerMode();}await listProjects();const health=await api('/api/health');if(!health.claude_available)$('engine-info').textContent='현재 서버에서 Claude 명령을 찾지 못했어요. 실제 조사는 실패 안내가 나오며 모의 모드로 화면 작업을 계속할 수 있습니다.';});
