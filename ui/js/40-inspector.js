'use strict';
/* ───────── inspector ───────── */
const CATS=[['Pink','FF007F'],['Review','FF0000'],['Build Up','FFA500'],['Warm Up','FFFF00'],['Peak Time','00FF00'],['Chill Out','25FDE9'],['Samples','0000FF'],['Closing','660099']];
function renderInsp(){
  const el=$('#insp');
  if(!S.rows.length&&S.done.apply){
    el.innerHTML=`<div class="empty"><div style="font-size:54px;margin-bottom:12px">✅</div><h2>Tanda terminada</h2><p>${S.done.cues?'Nombres, tags y cues listos. Ahora impórtalos en Rekordbox con djflow_cues.xml (visor «rekordbox xml» › djflow) y arrástralos a tu colección.':'Nombres y tags aplicados.'}<br><br>Si algo no te convence, puedes deshacer la tanda con ↶ (arriba).</p><button class="btn pri" id="eNew">Otra carpeta</button></div>`;$('#eNew').onclick=()=>{S.done={apply:false,cues:false};render();chooseFolder();};return;
  }
  if(!S.rows.length){
    const has=S.cfg.folder;
    el.innerHTML=`<div class="empty"><div class="eq"><i></i><i></i><i></i><i></i><i></i></div><h2>Prepara tu música antes de Rekordbox</h2>
      <p>Elige la carpeta con las canciones nuevas (ya pasadas por Mixed In Key). Dmzeta Workflow propone el nombre, los compases, los cues y el grid, tú lo revisas escuchando la onda.</p>
      <button class="btn pri" id="eChoose">Elegir carpeta</button>${has?`<button class="btn" id="eCont">Continuar con ${esc(has.split('/').pop())}</button>`:''}
      <div class="mini">Atajos: Espacio reproducir · ↑↓ cambiar de pista · S / E / L marcar START MIX, END MIX y loop</div></div>`;
    $('#eChoose').onclick=chooseFolder; const c=$('#eCont'); if(c)c.onclick=()=>loadReview(S.cfg.folder); return;
  }
  const r=S.rows[S.sel];
  if(!r){el.innerHTML=`<div class="empty"><h2>Selecciona una pista</h2><p>Haz clic en una tarjeta para revisarla. Si está desmarcada (☐) no se renombrará.</p></div>`;return;}
  const p=r.p,fl=flagsOf(r),T=(k,l,on)=>`<button class="tgb ${on?'on':''}" data-t="${k}">${l}</button>`;
  const bars=[4,8,16,24,32].map(b=>`<button data-b="${b}" class="${p.bars===b&&!p.aca_starter?'on':''}">${b}</button>`).join('');
  const types=['MOE','POE','FME'].map(t=>`<button data-v="${t}" data-ty="${t}" class="${p.type===t&&!p.aca_starter?'on':''}">${t}</button>`).join('');
  el.innerHTML=`
   <div><div class="lbl">Título</div><input class="fld big" id="fBase" value="${esc(p.base)}" spellcheck="false"><div class="orig" title="${esc(r.original)}">Original · ${esc(r.original)}</div></div>
   <div class="row2"><div><div class="lbl">Artista(s) · separados por comas</div><input class="fld" id="fArt" value="${esc(r.artist)}" spellcheck="false"></div>
     <div class="row2" style="gap:10px"><div><div class="lbl">Tono</div><input class="fld" id="fKey" value="${esc(p.key||'')}" maxlength="3" style="text-transform:uppercase"></div><div><div class="lbl">BPM</div><div style="display:flex;gap:5px"><input class="fld" id="fBpm" value="${p.bpm||''}" inputmode="decimal" style="min-width:0"><button class="btn sm ghost" id="fBpmH" title="Mitad de BPM" type="button">÷2</button><button class="btn sm ghost" id="fBpmD" title="Doble de BPM" type="button">×2</button></div></div></div></div>
   <div><div class="lbl">Nombre final · puedes editarlo a mano</div><div class="preview" id="fPrev">${previewHTML(r)}</div><input class="fld" id="fFinal" value="${esc(r.final)}" spellcheck="false" style="margin-top:8px;font-family:ui-monospace,Menlo,monospace;font-size:13px"></div>
   <div class="row2"><div><div class="lbl">Extended (compases y tipo)</div><div class="seg" id="sBars">${bars}</div></div><div><div class="lbl">Tipo</div><div class="seg t" id="sTy">${types}</div></div></div>
   <div><div class="lbl">Marcas del nombre</div><div class="tg" id="tgs">${T('mashup','Mashup',p.mashup)}${T('open_show','Open Show',p.open_show)}${T('aca_starter','Aca Starter',p.aca_starter)}${T('In Aca','In Aca',p.after==='In Aca')}${T('In Hype','In Hype',p.after==='In Hype')}${T('short_edit','Short Edit',p.short_edit)}${T('aca_out','Aca Out',p.aca_out)}</div></div>
   ${startHintHTML()}
   <div><div class="lbl">Género${(curMarks().genre_conf!=null&&!curMarks().genre_edit)?` · detectado (${Math.round(curMarks().genre_conf*100)} %)`:''}</div><input class="fld" id="fGen" list="dlGen" value="${esc(curMarks().genre||'')}" placeholder="sin género" spellcheck="false"><datalist id="dlGen">${(S.st.genres||[]).map(g=>`<option value="${esc(g)}">`).join('')}</datalist>${(curMarks().genre_top||[]).length?`<div class="tg" id="gTop" style="margin-top:6px">${curMarks().genre_top.map(g=>`<button class="tgb ${g===curMarks().genre?'on':''}" data-g="${esc(g)}">${esc(g)}</button>`).join('')}</div>`:''}</div>
   <div><div class="lbl">Categoría (color en Rekordbox)${curMarks().cat_conf!=null&&!curMarks().cat_edit?` · detectada (${Math.round(curMarks().cat_conf*100)} %)`:''}</div><div class="tg" id="tCat">${CATS.map(([n,h])=>`<button class="tgb ${curMarks().cat===n?'on':''}" data-c="${n}" style="${curMarks().cat===n?`background:#${h};color:#000;border-color:#${h}`:`border-color:#${h}88`}"><i style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#${h};margin-right:6px"></i>${n}</button>`).join('')}</div></div>
   <div><div class="lbl">Valoración${curMarks().stars_auto?' · propuesta':''}</div><div class="tg" id="tStar">${[1,2,3,4,5].map(i=>`<button class="tgb ${(curMarks().stars||0)>=i?'on':''}" data-s="${i}" style="font-size:18px;padding:2px 10px;${(curMarks().stars||0)>=i?'color:#ffd54a':''}">${(curMarks().stars||0)>=i?'★':'☆'}</button>`).join('')}</div></div>
   <div><button class="tbtn" id="bAcc" style="width:100%;height:44px;background:linear-gradient(135deg,#059669,#34d399);border:0;color:#04140d;font-size:13px">✓ ACEPTAR Y SIGUIENTE <small style="opacity:.6;margin-left:8px">Enter</small></button></div>
   <div><div class="lbl">Avisos</div><div class="flags">${fl.length?fl.map(f=>`<div class="flag ${f.k==='info'?'':f.k}"><i>${{bad:'⛔',warn:'⚠️',good:'✅',info:'ℹ️'}[f.k]}</i><span>${esc(f.t)}</span></div>`).join(''):'<div class="flag good"><i>✅</i><span>Sin avisos. Aun así, escucha el corte antes de aplicar.</span></div>'}</div></div>`;
  const upd=()=>{r.final=finalOf(r);r.reviewed=true;$('#fPrev').innerHTML=previewHTML(r);{const ff=$('#fFinal');if(ff&&document.activeElement!==ff)ff.value=r.final;}patchCard(S.sel);queueSave();drawDeck();};
  $('#fBase').oninput=e=>{p.base=e.target.value;upd();}; $('#fArt').oninput=e=>{r.artist=e.target.value;upd();};
  $('#bAcc').onclick=acceptNext;
  {const ta=$('#tAlt');if(ta)ta.onclick=e=>{const b=e.target.closest('[data-alt]');if(b)pickStart(+b.dataset.alt);};}
  $('#tCat').onclick=e=>{const b=e.target.closest('[data-c]');if(!b)return;const mk=curMarks();mk.cat=(mk.cat===b.dataset.c?'':b.dataset.c);mk.cat_edit=true;if(!mk.cat)delete mk.cat;r.reviewed=true;queueSave();renderInsp();};
  $('#tStar').onclick=e=>{const b=e.target.closest('[data-s]');if(!b)return;const mk=curMarks(),n=+b.dataset.s;mk.stars=(mk.stars===n?0:n);delete mk.stars_auto;r.reviewed=true;queueSave();renderInsp();};
  const setGen=v=>{const mk=curMarks();mk.genre=v.trim();mk.genre_edit=true;if(!mk.genre)delete mk.genre;r.reviewed=true;queueSave();};
  $('#fGen').onchange=e=>{setGen(e.target.value);renderInsp();};
  const gt=$('#gTop');if(gt)gt.onclick=e=>{const g=e.target.dataset.g;if(!g)return;setGen(g);renderInsp();};
  $('#fFinal').oninput=e=>{const v=e.target.value;r.final=v.trim();r.reviewed=true;const n=parseName(v+'.mp3');if(!n.key)n.key=p.key;if(!n.bpm)n.bpm=p.bpm;Object.assign(p,n);$('#fPrev').innerHTML=previewHTML(r);patchCard(S.sel);queueSave();};
  $('#fFinal').onchange=()=>renderInsp();
  $('#fKey').oninput=e=>{p.key=e.target.value.toUpperCase();upd();}; $('#fBpm').oninput=e=>{p.bpm=parseFloat(e.target.value)||0;upd();};
  // Si cambias el BPM de forma notable (p. ej. 82 → 164), el grid se recalcula con ese tempo; si no, la onda seguiría mostrando el anterior.
  const applyBpm=async()=>{if(!(p.bpm>0)||!D.bpm||D.name!==r.original||Math.abs(p.bpm-D.bpm)/D.bpm<0.01)return;setMsg('BPM cambiado: reanalizando grid…',true);try{api('/api/bpmfix',{name:r.original,detected:D.bpm,corrected:p.bpm}).catch(()=>{});await regrid(r);await loadTrack(S.sel);setMsg('Grid recalculado a '+p.bpm+' BPM ✓');}catch(err){showErr(err);}};
  $('#fBpm').onchange=applyBpm;
  const scaleBpm=k=>{if(!(p.bpm>0))return;p.bpm=+(p.bpm*k).toFixed(2);$('#fBpm').value=p.bpm;upd();applyBpm();};
  $('#fBpmH').onclick=()=>scaleBpm(0.5); $('#fBpmD').onclick=()=>scaleBpm(2);
  $('#sBars').onclick=e=>{const b=e.target.dataset.b;if(!b)return;if(p.bars===+b&&!p.aca_starter){p.bars=null;p.type=null;}else{p.bars=+b;p.aca_starter=false;if(!p.type)p.type='POE';}r.final=finalOf(r);r.reviewed=true;renderInsp();patchCard(S.sel);queueSave();drawDeck();};
  $('#sTy').onclick=e=>{const t=e.target.dataset.ty;if(!t)return;if(p.type===t&&!p.aca_starter){p.type=null;p.bars=null;}else{p.type=t;p.aca_starter=false;if(!p.bars)p.bars=8;}r.final=finalOf(r);r.reviewed=true;renderInsp();patchCard(S.sel);queueSave();drawDeck();};
  $('#tgs').onclick=e=>{const t=e.target.dataset.t;if(!t)return;
    if(t==='In Aca'||t==='In Hype')p.after=(p.after===t?null:t);
    else if(t==='aca_starter'){p.aca_starter=!p.aca_starter;}
    else p[t]=!p[t];
    r.final=finalOf(r);r.reviewed=true;renderInsp();patchCard(S.sel);queueSave();drawDeck();};
}
function setChecked(i,v){const r=S.rows[i];r.checked=v;patchCard(i);queueSave();}
function queueSave(){clearTimeout(S.saveT);S.saveT=setTimeout(saveReview,500);}
async function saveReview(){
  if(!S.folder)return; const rows=S.rows.map(r=>({original:r.original,final:r.final,artist:r.artist,confidence:r.confidence,flags:r.flags,checked:r.checked,reviewed:r.reviewed}));
  try{await api('/api/review',{folder:S.folder,rows,marks:S.marks});}catch(e){}
}
function render(){renderFilters();renderList();renderInsp();renderSteps();}
function renderSteps(){
  const cur=S.done.cues?4:S.done.apply?3:!S.rows.length?1:2;
  $$('.step').forEach(s=>{const n=+s.dataset.s;s.classList.toggle('on',n===cur&&!(n===4&&S.done.cues));s.classList.toggle('done',n<cur||(n===4&&S.done.cues));});
  const b=$('#bCta'); b.textContent=S.done.cues?'Mostrar en Finder':!S.rows.length?'Elegir carpeta':'Aplicar + generar cues';
  $('#bUndo').style.display=S.st.undo?'grid':'none';
}

