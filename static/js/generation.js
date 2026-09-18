(() => {
  const modal = document.getElementById('generation-wizard');
  if (!modal) return;
  const content = document.getElementById('generation-content');
  const next = document.getElementById('generation-next');
  const back = document.getElementById('generation-back');
  const status = document.getElementById('generation-status');
  const errorBox = document.getElementById('generation-error');
  const trigger = document.getElementById('btn-auto-generate');
  let context, conditions, nightCounts, scope, month, mode, floor, step, draft, saveDefaults, busy = false;
  const esc = value => String(value ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const staff = () => context.staff.filter(s => !s.exclude_from_staffing && (!scope || (s.departments || [s.department]).includes(scope)));
  function fail(message) { errorBox.textContent = message; errorBox.classList.remove('hidden'); errorBox.scrollIntoView({block:'nearest'}); }
  function loading(value, message = '') { content.querySelectorAll('input,select').forEach(input=>input.disabled=value); busy=value; next.disabled=value; back.disabled=value; modal.querySelectorAll('[data-generation-close]').forEach(b=>b.disabled=value); status.textContent=message; }
  async function api(path, data) {
    const response = await fetch('/api/shifts/generation/' + path, data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {});
    const result = await response.json().catch(()=>({}));
    if (!response.ok) throw new Error(typeof result.detail==='string' ? result.detail : '処理できませんでした。入力内容を確認してください。');
    return result;
  }
  function field(label, input, hint='') { return `<label class="form-field"><span class="form-label">${label}</span>${input}${hint?`<span class="field-hint">${hint}</span>`:''}</label>`; }
  function number(key,label,min,max) { return field(label,`<input type="number" data-condition="${key}" min="${min}" max="${max}" ${key==='off_days_per_period'?'placeholder="自動（土日数）"':'required'} value="${conditions[key]??''}">`, key==='off_days_per_period'?'明け・有休は公休と別に数えます。':''); }
  function requirements() {
    if(context.settings.staffing_requirement_mode==='time_slot') {
      return `<h4>時間帯ごとの必要人数</h4><div class="generation-table-wrap"><table class="data-table"><thead><tr><th>フロア・時間帯</th><th>必要人数</th></tr></thead><tbody>${conditions.time_slot_staffing_rules.map((r,i)=>`<tr ${scope&&r.floor&&r.floor!==scope?'hidden':''}><td>${esc(r.floor||'施設全体')} ${esc(r.label)}<br>${esc(r.start_time)}〜${r.end_time<r.start_time?'翌':''}${esc(r.end_time)}</td><td><input type="number" data-slot="${i}" min="0" max="99" required value="${r.min_staff}" aria-label="${esc(r.label)}の必要人数"></td></tr>`).join('')}</tbody></table></div>`;
    }
    const shown=scope?[scope]:context.floors;
    if(!shown.includes(floor))floor=shown[0];
    return `<div class="generation-row"><h4>1日に必要な人数</h4><label>フロア <select id="generation-floor">${shown.map(f=>`<option ${floor===f?'selected':''}>${esc(f)}</option>`).join('')}</select></label></div><div class="generation-counts">${context.work_types.map(w=>field(esc(w.label),`<input type="number" required min="0" max="99" data-count="${esc(w.key)}" value="${conditions.min_staff_by_floor[floor]?.[w.key]??0}">`)).join('')}</div>`;
  }
  function nightRows() { return staff().map(s=>`<tr><td>${esc(s.name)}</td><td>${s.can_work_night?'可':'不可'}</td><td>${s.can_work_night?`<input type="number" min="0" max="31" data-night="${s.id}" value="${nightCounts[s.id]??(s.fix_night_shift_count?s.night_shift_count??'':'')}" placeholder="勤務割合に従う" aria-label="${esc(s.name)}の今回の夜勤回数">`:'0回'}</td></tr>`).join(''); }
  function pairs() {
    const byId=new Map(context.staff.map(s=>[s.id,s])); const seen=new Set(), labels=[];
    for(const s of context.staff) for(const id of [...(s.night_incompatible_ids||[]),...(s.day_incompatible_ids||[])]) {
      if(!byId.has(id))continue;
      const pair=[s.id,id].sort((a,b)=>a-b).join(':');
      if(seen.has(pair))continue;seen.add(pair);
      if(staff().some(x=>x.id===id||x.id===s.id))labels.push(`${esc(s.name)} × ${esc(byId.get(id).name)}`);
    }
    return labels.join('<br>')||'登録なし';
  }
  function render() {
    errorBox.classList.add('hidden');
    modal.querySelectorAll('.generation-steps li').forEach((item,i)=>{if(i+1===step)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');});
    back.textContent=step===1?'閉じる':'戻る';
    next.textContent=step===1?'次へ：今回の条件':step===2?'この条件で案を作成':'この案を反映';
    next.disabled=false;status.textContent='';
    if(step===1) {
      content.innerHTML=`<h4>どのシフトを作りますか？</h4><div class="settings-form-grid">${field('対象月',`<input type="month" id="generation-month" min="2000-01" max="2100-12" required value="${month}">`)}${field('対象フロア',`<select id="generation-scope"><option value="">すべてのフロア</option>${context.floors.map(f=>`<option ${scope===f?'selected':''}>${esc(f)}</option>`).join('')}</select>`)}</div><p class="field-hint">施設の開始日（毎月${context.settings.calendar_start_day}日）から1期間が対象です。複数フロアに登録した職員は勤務全体が対象になります。</p>${field('作り直す範囲',`<select id="generation-mode"><option value="auto" ${mode==='auto'?'selected':''}>空欄と、自動生成した勤務</option><option value="blank" ${mode==='blank'?'selected':''}>空欄だけ</option></select>`)}<p class="generation-note">手動入力・希望休はそのまま残します。</p><p>対象職員：${staff().length}人</p>`;
    } else if(step===2) {
      content.innerHTML=`<h4>今回の条件を確認</h4><p class="generation-note">日中・通常夜勤は1人1フロア。${context.settings.require_leader_on_night?'夜勤はフロア担当に加え、兼務リーダーを別に1人確保します。':'夜勤リーダーの別枠確保はオフです（各種設定で変更）。'}</p><p class="field-hint">標準設定を読み込んでいます。変更は今回の生成だけに使います。</p><div class="settings-form-grid">${number('off_days_per_period','1人あたりの公休（日）',0,31)}${number('max_consecutive_days','連続勤務の上限（日）',1,14)}</div>${requirements()}<details class="settings-advanced"><summary>職員ごとの夜勤回数を確認・変更</summary><p class="field-hint">空欄は勤務割合に従います。数字を入れると今回の固定回数になります。対象外の職員は変更しません。</p><div class="generation-table-wrap"><table class="data-table"><thead><tr><th>職員</th><th>夜勤</th><th>今回の回数</th></tr></thead><tbody>${nightRows()}</tbody></table></div></details><details class="settings-advanced"><summary>夜勤の上限・相性を確認</summary>${number('max_night_per_week','1週間の夜勤上限（回）',0,7)}<p>同じ夜勤を避ける組み合わせ</p><p>${pairs()}</p><p class="field-hint">夜勤不可・相性NG、夜勤→明け→休みは常に適用します。</p></details><details class="settings-advanced"><summary>この条件を今後も使いたい場合</summary><label class="check-row"><input type="checkbox" id="generation-save-defaults" ${saveDefaults?'checked':''}>反映時に、施設共通の条件を標準設定にも保存する</label><p class="field-hint">職員ごとの夜勤回数は今回のみの変更です。</p></details>`;
    } else {
      const cells=new Map(draft.assignments.map(a=>[`${a[0]}:${a[1]}`,a]));
      const placements=new Map((draft.placements||[]).map(p=>[`${p.staff_id}:${p.date}`,p]));
      content.innerHTML=`<h4>反映する前に確認</h4><p>${esc(draft.start)}〜${esc(draft.end)} / ${esc(draft.scope)} / ${draft.summary.length}人</p><p class="generation-note">手動入力 ${draft.stats.manual_locked}件・希望休 ${draft.stats.leave_locked}件を保持します。案の有効期限は1時間です。</p><p class="field-hint">勤務の下に配置先を表示します。L＝夜勤リーダー（担当フロア兼務・フロア必要人数には含めません）。</p>${draft.warnings.length?`<details class="generation-warnings" open><summary>確認事項 ${draft.warnings.length}件</summary><ul>${draft.warnings.map(w=>`<li>${esc(w.message)}</li>`).join('')}</ul></details>`:'<p>公休・夜勤回数・配置についての警告はありません。</p>'}<div class="generation-table-wrap" tabindex="0" role="region" aria-label="生成案のカレンダー。横方向にスクロールできます"><table class="data-table generation-calendar"><thead><tr><th>職員</th>${draft.dates.map(d=>`<th>${Number(d.slice(5,7))}/${Number(d.slice(8))}</th>`).join('')}</tr></thead><tbody>${draft.summary.map(s=>`<tr><th>${esc(s.name)}</th>${draft.dates.map(d=>{const a=cells.get(`${s.id}:${d}`),p=placements.get(`${s.id}:${d}`);const badge=p?.role==='night_leader'?'L':p?.floor||'';return `<td class="${esc(window.SYMBOL_CLASS_MAP?.[a?.[2]]||'')}" title="${a?.[3]==='manual'?'手動入力を保持':a?.[3]==='leave'?'希望休を保持':'自動生成'}">${esc(a?.[2]||'')}${badge?`<small class="placement-badge" aria-label="${p.role==='night_leader'?'夜勤リーダー（担当フロア兼務）':esc(badge)}">${esc(badge)}</small>`:''}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div><details class="settings-advanced" open><summary>公休・夜勤回数の集計</summary><div class="generation-table-wrap"><table class="data-table"><thead><tr><th>職員</th><th>公休／目標</th><th>夜勤／設定</th></tr></thead><tbody>${draft.summary.map(s=>`<tr><td>${esc(s.name)}</td><td>${s.off}日／${s.off_target}日</td><td>${s.nights}回／${s.night_target===null?'勤務割合':s.night_target+'回'}</td></tr>`).join('')}</tbody></table></div></details>`;
      if(draft.warnings.some(w=>w.level==='error')) {next.disabled=true;status.textContent='条件を見直して案を作り直してください。';}
    }
  }
  function close() { if(busy)return;modal.classList.add('hidden');modal.setAttribute('aria-hidden','true');trigger.focus(); }
  trigger?.addEventListener('click',async()=>{
    context=null;step=1;draft=null;modal.classList.remove('hidden');modal.setAttribute('aria-hidden','false');content.textContent='条件を読み込み中…';errorBox.classList.add('hidden');loading(true);
    try {
      context=await api('context');conditions={off_days_per_period:context.settings.off_days_per_period,max_consecutive_days:context.settings.max_consecutive_days,max_night_per_week:context.settings.max_night_per_week,min_staff_by_floor:structuredClone(context.settings.min_staff_by_floor),time_slot_staffing_rules:structuredClone(context.settings.time_slot_staffing_rules)};
      nightCounts={};scope='';month=`${window.CALENDAR_YEAR}-${String(window.CALENDAR_MONTH).padStart(2,'0')}`;mode='auto';floor=context.floors[0];step=1;draft=null;saveDefaults=false;render();
    }catch(e){fail(e.message);next.disabled=true;}finally{busy=false;content.querySelectorAll('input,select').forEach(input=>input.disabled=false);back.disabled=false;modal.querySelectorAll('[data-generation-close]').forEach(b=>b.disabled=false);back.focus();}
  });
  content.addEventListener('change',e=>{
    const t=e.target;
    if(t.dataset.condition){conditions[t.dataset.condition]=t.value===''?null:Number(t.value);}
    if(t.hasAttribute('data-count')){conditions.min_staff_by_floor[floor]??={};conditions.min_staff_by_floor[floor][t.dataset.count]=Number(t.value);}
    if(t.hasAttribute('data-slot'))conditions.time_slot_staffing_rules[Number(t.dataset.slot)].min_staff=Number(t.value);
    if(t.hasAttribute('data-night')){if(t.value==='')delete nightCounts[t.dataset.night];else nightCounts[t.dataset.night]=Number(t.value);}
    if(t.id==='generation-floor'){floor=t.value;render();}
    if(t.id==='generation-scope'){scope=t.value;render();}
    if(t.id==='generation-month')month=t.value;
    if(t.id==='generation-mode')mode=t.value;
    if(t.id==='generation-save-defaults')saveDefaults=t.checked;
  });
  next.addEventListener('click',async()=>{
    if(busy)return;
    const invalid=[...content.querySelectorAll('input,select')].find(x=>!x.checkValidity());
    if(invalid){for(let p=invalid.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;invalid.reportValidity();return;}
    if(step===1){if(!staff().length){fail('対象職員がいません。職員管理の担当フロアを確認してください。');return;}step=2;render();return;}
    loading(true,step===2?'案を作成しています…':'確認した案を反映しています…');errorBox.classList.add('hidden');
    try {
      if(step===2){const [year,m]=month.split('-').map(Number);const ids=new Set(staff().map(s=>String(s.id)));draft=await api('preview',{year,month:m,floor:scope||null,mode,conditions,night_counts:Object.fromEntries(Object.entries(nightCounts).filter(([id])=>ids.has(id))),save_defaults:saveDefaults});step=3;render();}
      else {await api('apply',{token:draft.token});status.textContent='反映しました。カレンダーを更新します。';window.location.reload();return;}
    } catch(e){fail(e.message);} finally{busy=false;content.querySelectorAll('input,select').forEach(input=>input.disabled=false);back.disabled=false;modal.querySelectorAll('[data-generation-close]').forEach(b=>b.disabled=false);next.disabled=step===3&&draft?.warnings.some(w=>w.level==='error');if(!next.disabled)status.textContent='';}
  });
  back.addEventListener('click',()=>{if(busy)return;if(!context||step===1){close();return;}step--;draft=null;render();});
  modal.querySelectorAll('[data-generation-close]').forEach(b=>b.addEventListener('click',close));
  modal.addEventListener('keydown',e=>{
    if(e.key==='Escape'){e.preventDefault();close();}
    if(e.key==='Tab') {const fields=[...modal.querySelectorAll('button,input,select,summary,[tabindex="0"]')].filter(x=>!x.disabled&&x.getClientRects().length);const first=fields[0],last=fields.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
  });
})();
