'use strict';
/* ───────── lista + filtros ───────── */
function flagsOf(r){
  const out=[];
  (r.flags||'').split(';').map(x=>x.trim()).filter(Boolean).forEach(f=>{
    if(f.startsWith('DUPLICADO'))out.push({k:'bad',t:'Posible duplicado. '+f.replace('DUPLICADO:','').trim()});
    else if(f.startsWith('Live Mashup'))out.push({k:'good',t:'Live Mashup: se aplica la regla fija (MOE de 4 u 8 compases + Aca Out).'});
    else if(f.startsWith('barras dudosas'))out.push({k:'warn',t:'Compases dudosos '+f.replace('barras dudosas','').trim()+'. Escucha el corte y confírmalo.'});
    else if(f.startsWith('tipo dudoso'))out.push({k:'warn',t:'Tipo dudoso '+f.replace('tipo dudoso','').trim()+'. Revisa MOE / POE / FME.'});
    else if(f.includes('Aca Out?'))out.push({k:'warn',t:'¿Tiene Aca Out? Comprueba el final de la pista.'});
    else if(f.includes('Aca Starter?'))out.push({k:'warn',t:'¿Empieza en acapella? Escucha el inicio.'});
    else if(f.includes('Short Edit?'))out.push({k:'warn',t:'¿Es un Short Edit? Comprúebalo.'});
    else if(f.includes('In Aca')||f.includes('In Hype'))out.push({k:'warn',t:f});
    else if(f.startsWith('START MIX propuesto'))out.push({k:'info',t:f+'. Ajústalo sobre la onda si no cuadra.'});
    else if(f.includes('sacados del NOMBRE'))out.push({k:'warn',t:'BPM y tono sacados del nombre del archivo, no de Mixed In Key. Pásala por Mixed In Key para fiarte.'});
    else if(f.startsWith('BPM de Mixed In Key'))out.push({k:'warn',t:f});
    else if(f.startsWith('Título con'))out.push({k:'info',t:'Título con "x": se ha puesto (Mashup) automáticamente.'});
    else if(f.startsWith('sin BPM'))out.push({k:'bad',t:'Sin BPM/tono: pasa antes la pista por Mixed In Key.'});
    else if(f.startsWith('trae "Mashup"'))out.push({k:'info',t:'El nombre trae "Mashup": ¿quieres (Mashup)?'});
    else out.push({k:'info',t:f});
  });
  return out;
}
const isDoubt=r=>r.confidence<0.6||flagsOf(r).some(f=>f.k==='warn');
function chipsHTML(r){
  const p=r.p,c=[]; if(p.aca_starter)c.push('<span class="chip c-bars">ACA START</span>'); else if(p.bars)c.push(`<span class="chip c-bars">${p.bars} BARS</span>`);
  if(p.type&&!p.aca_starter)c.push(`<span class="chip c-${p.type}">${p.type}</span>`);
  if(p.mashup)c.push('<span class="chip c-tag">MASHUP</span>'); if(r.original.toLowerCase().includes('live mashup'))c.push('<span class="chip c-info">LIVE</span>');
  if(p.after)c.push(`<span class="chip c-tag">${p.after.toUpperCase()}</span>`); if(p.short_edit)c.push('<span class="chip c-tag">SHORT</span>'); if(p.open_show)c.push('<span class="chip c-tag">OPEN SHOW</span>'); if(p.aca_out)c.push('<span class="chip c-tag">ACA OUT</span>');
  if(r.dup)c.push('<span class="chip c-dup">DUPLICADO</span>'); else if(isDoubt(r)&&!r.reviewed)c.push('<span class="chip c-warn">REVISAR</span>');
  const mk=S.marks[r.original]; if(mk&&mk.start!=null)c.push('<span class="chip c-info">MIX</span>');
  return c.join('');
}
function cardHTML(r,i){
  const kb=keyBadge(r.p.key),conf=r.confidence,col=conf>=.75?'#34d399':conf>=.55?'#fbbf24':'#f87171';
  const artist=r.artist||'<span style="opacity:.5">sin artista</span>';
  return `<div class="card ${i===S.sel?'sel':''} ${r.checked?'':'off'}" data-i="${i}">
    <div class="chk ${r.checked?'on':''}" data-chk="${i}">${r.checked?'✓':''}</div>
    <div class="key" style="background:${kb.bg}">${kb.t}<small>${r.p.bpm?Math.round(r.p.bpm)+' BPM':''}</small></div>
    <div style="min-width:0" title="${esc(r.final||'')}"><div class="ttl">${r.p.key&&r.p.bpm?previewHTML(r):esc(r.final||r.p.base||r.original)}${(r.final&&r.proposed&&r.final!==r.proposed)?' <span class="chip c-tag" style="margin-left:6px">EDITADA</span>':''}</div><div class="sub">${r.artist?esc(r.artist):artist}</div></div>
    <div class="chips">${chipsHTML(r)}</div>
    <div class="ring" style="background:conic-gradient(${col} ${Math.round(conf*360)}deg,rgba(255,255,255,.1) 0)"><span>${Math.round(conf*100)}</span></div>
    ${r.reviewed?'<i class="seen"></i>':''}</div>`;
}
function visible(){
  const q=S.q.trim().toLowerCase();
  return S.rows.map((r,i)=>[r,i]).filter(([r])=>{
    if(q&&!(r.original+' '+r.artist+' '+r.final).toLowerCase().includes(q))return false;
    return S.filter==='all'||(S.filter==='doubt'&&isDoubt(r)&&!r.reviewed)||(S.filter==='dup'&&r.dup)||(S.filter==='seen'&&r.reviewed)||(S.filter==='off'&&!r.checked);
  });
}
function renderFilters(){
  const n=S.rows.length,c={all:n,doubt:S.rows.filter(r=>isDoubt(r)&&!r.reviewed).length,dup:S.rows.filter(r=>r.dup).length,seen:S.rows.filter(r=>r.reviewed).length,off:S.rows.filter(r=>!r.checked).length};
  const L={all:'Todas',doubt:'Por revisar',dup:'Duplicadas',seen:'Vistas',off:'Off'};
  $('#filters').innerHTML=Object.keys(L).map(k=>`<button class="pill ${S.filter===k?'on':''}" data-f="${k}">${L[k]}<b>${c[k]}</b></button>`).join('')+`<input class="search" id="q" placeholder="Buscar…" value="${esc(S.q)}">`;
  const q=$('#q');q.oninput=()=>{S.q=q.value;renderList();};
  const nv=visible().length;
  $('#bulk').innerHTML=`<button class="pill" data-bulk="on" title="Marca con ✓ todas las pistas que ves ahora (usa el filtro Off o Duplicadas)">☑ Marcar visibles<b>${nv}</b></button><button class="pill" data-bulk="off">☐ Desmarcar visibles</button><button class="pill" data-bulk="nodup" title="Marca todas menos las duplicadas">☑ Todas menos duplicadas</button>`;
}
function bulk(m){
  if(m==='nodup')S.rows.forEach(r=>{r.checked=!r.dup;});else visible().forEach(([r])=>{r.checked=(m==='on');});
  renderFilters();renderList();queueSave();
}
function renderList(){
  const v=visible(); const el=$('#list');
  el.innerHTML=v.length?v.map(([r,i])=>cardHTML(r,i)).join(''):`<div class="empty" style="margin:auto"><p>${S.rows.length?'Nada con este filtro.':'Aquí aparecerán tus pistas.'}</p></div>`;
}
function patchCard(i){const old=$(`.card[data-i="${i}"]`);if(old){const t=document.createElement('div');t.innerHTML=cardHTML(S.rows[i],i);old.replaceWith(t.firstElementChild);}renderFilters();}

