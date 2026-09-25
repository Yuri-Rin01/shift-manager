(() => {
  const $ = id => document.getElementById(id);
  const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let sheet, active, loading = false, saving = false;
  const editor = $('daily-editor'), roleEditor = $('daily-role-editor');
  async function api(path, data) {
    const response = await fetch('/api/daily-duties' + path, data ? {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '入力内容を確認してください。');
    return result;
  }
  function roles() { $('daily-role-list').innerHTML = sheet.roles.map(r=>`<option value="${esc(r)}"></option>`).join(''); }
  function render() {
    const unfilled = sheet.rows.reduce((n,r)=>n+r.cells.filter(c=>(c.am_enabled&&!c.am)||(c.pm_enabled&&!c.pm)).length,0);
    $('daily-title').textContent = `${sheet.facility_name} デイリー役割表`;
    $('daily-range').textContent = `${sheet.dates[0]} 〜 ${sheet.dates.at(-1)}${$('daily-floor').value ? ' ／ 担当可能フロア：'+$('daily-floor').value : ''}`;
    $('daily-status').textContent = `${sheet.rows.length}人 ／ 未入力の勤務 ${unfilled}件 ／ 勤務変更による要確認 ${sheet.review_count}件${sheet.review_count ? '。該当枠を開き、担当を確認・保存または解除してから印刷してください。' : ''}`;
    $('daily-print').disabled = sheet.review_count > 0 || !sheet.rows.length;
    $('daily-table').classList.toggle('daily-one-day', sheet.dates.length===1);
    $('daily-table').innerHTML = `<colgroup><col class="daily-name-col">${sheet.dates.map(()=>'<col class="daily-symbol-col"><col><col>').join('')}</colgroup><thead><tr><th rowspan="2" scope="col">職員名</th>${sheet.dates.map(d=>`<th colspan="3" scope="colgroup">${esc(d.slice(5).replace('-','/'))}（${'日月火水木金土'[new Date(d+'T12:00:00').getDay()]}）</th>`).join('')}</tr><tr>${sheet.dates.map(()=>'<th scope="col">勤務</th><th scope="col">AM</th><th scope="col">PM</th>').join('')}</tr></thead><tbody>${sheet.rows.map(r=>`<tr><th scope="row">${esc(r.name)}</th>${r.cells.map(c=>{
      const location = c.night_leader ? '兼務L' : c.floor || (c.symbol&&(c.am_enabled||c.pm_enabled||c.night)?'未配置':'');
      const night = c.night ? (c.night_leader ? '夜勤リーダー（兼務）' : c.floor || '配置未確定') : '';
      const td = period => {
        const text = c[period] || (period==='pm' ? night : '');
        return `<td class="${c.stale?'daily-stale':''} ${!c[period+'_enabled']?'daily-inactive':''}">${c[period+'_enabled']||c.stale ? `<button type="button" data-duty-staff="${r.id}" data-duty-date="${c.date}" data-period="${period}" aria-label="${esc(r.name)} ${c.date} ${period.toUpperCase()}担当：${esc(text||'未入力')}"><span>${esc(text)||'<span class="daily-empty">＋ 担当</span>'}</span>${c.stale?'<small>要確認</small>':''}</button>` : esc(text)}</td>`;
      };
      return `<td class="daily-symbol ${!c.am_enabled&&!c.pm_enabled&&!c.night?'daily-inactive':''}">${esc(c.symbol)||'—'}<small>${esc(location)}</small></td>${td('am')}${td('pm')}`;
    }).join('')}</tr>`).join('')}</tbody>`;
    if (!sheet.rows.length) $('daily-status').textContent = '対象の職員がいません。フロア条件または職員登録を確認してください。';
    roles();
  }
  async function load() {
    if (loading) return;
    if (!$('daily-start').reportValidity()) return;
    loading = true; $('daily-error').hidden = true; $('daily-status').textContent = '読み込み中…';
    $('daily-controls').querySelectorAll('button,input,select').forEach(x=>x.disabled=true);
    try {
      sheet = await api('?'+new URLSearchParams({start:$('daily-start').value,days:$('daily-days').value,floor:$('daily-floor').value}));
      const floor = $('daily-floor').value;
      $('daily-floor').innerHTML = '<option value="">すべて</option>'+sheet.floors.map(f=>`<option value="${esc(f)}">${esc(f)}</option>`).join('');
      $('daily-floor').value = floor; render();
    } catch(e) { $('daily-error').textContent=e.message; $('daily-error').hidden=false; $('daily-status').textContent='読み込めませんでした。「表示・再読み込み」で再試行してください。'; }
    finally { loading=false;$('daily-controls').querySelectorAll('button,input,select').forEach(x=>x.disabled=false);$('daily-print').disabled=!sheet||sheet.review_count>0||!sheet.rows.length; }
  }
  $('daily-controls').addEventListener('submit',e=>{e.preventDefault();load();});
  for(const id of ['daily-start','daily-days','daily-floor']) $(id).addEventListener('change',load);
  for(const [id,delta] of [['daily-prev',-1],['daily-next',1]]) $(id).addEventListener('click',()=>{
    const d=new Date($('daily-start').value+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+delta*Number($('daily-days').value));$('daily-start').value=d.toISOString().slice(0,10);load();
  });
  $('daily-table').addEventListener('click',e=>{
    const button=e.target.closest('[data-duty-staff]');if(!button||loading)return;
    const row=sheet.rows.find(r=>r.id===Number(button.dataset.dutyStaff));active=row.cells.find(c=>c.date===button.dataset.dutyDate);
    $('daily-editor-title').textContent = `${row.name} ／ ${active.date}`;
    $('daily-editor-note').textContent = `勤務：${active.symbol||'未入力'} ${active.floor}${active.stale?' ／ 元の勤務が変わっています。担当を見直してください。':''}`;
    for(const p of ['am','pm']) { $('daily-'+p).value=active[p];$('daily-'+p).disabled=!active[p+'_enabled']; }
    $('daily-cell-error').textContent='';editor.showModal();
    if(active[button.dataset.period+'_enabled']) $('daily-'+button.dataset.period).focus();
  });
  async function saveCell(clear=false) {
    if(saving)return;saving=true;
    editor.querySelectorAll('button').forEach(b=>b.disabled=true);
    try {
      const result=await api('/cell',{staff_id:active.staff_id,date:active.date,am:clear?'':$('daily-am').value.trim(),pm:clear?'':$('daily-pm').value.trim(),signature:active.signature,revision:active.revision});
      Object.assign(active,result);sheet.review_count=sheet.rows.reduce((n,r)=>n+r.cells.filter(c=>c.stale).length,0);render();editor.close();$('daily-status').textContent+=' ／ 保存しました';
    } catch(e){$('daily-cell-error').textContent=e.message;}
    finally{saving=false;editor.querySelectorAll('button').forEach(b=>b.disabled=false);}
  }
  $('daily-cell-form').addEventListener('submit',e=>{e.preventDefault();saveCell();});
  $('daily-clear').addEventListener('click',()=>saveCell(true));
  $('daily-options').addEventListener('click',()=>{if(!sheet)return;$('daily-role-text').value=sheet.roles.join('\n');$('daily-role-error').textContent='';roleEditor.showModal();});
  $('daily-role-form').addEventListener('submit',async e=>{
    e.preventDefault();if(saving)return;saving=true;roleEditor.querySelectorAll('button').forEach(b=>b.disabled=true);
    try { const result=await api('/roles',{labels:$('daily-role-text').value.split('\n'),revision:sheet.roles_revision});Object.assign(sheet,result);roles();roleEditor.close(); }
    catch(e){$('daily-role-error').textContent=e.message;}
    finally{saving=false;roleEditor.querySelectorAll('button').forEach(b=>b.disabled=false);}
  });
  document.querySelectorAll('[data-close-duty]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
  [editor,roleEditor].forEach(d=>d.addEventListener('cancel',e=>{if(saving)e.preventDefault();}));
  $('daily-print').addEventListener('click',async()=>{
    await load();if($('daily-error').hidden===false||$('daily-print').disabled)return;
    let style=$('daily-print-style');if(!style){style=document.createElement('style');style.id='daily-print-style';document.head.appendChild(style);}
    style.textContent=`@page {size:${$('daily-paper').value} landscape; margin:8mm;} ${$('daily-paper').value==='A3'?'@media print {#daily-table {font-size:10px} #daily-table small {font-size:9px}}':''}`;
    window.print();
  });
  load();
})();
