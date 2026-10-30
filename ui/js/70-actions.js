'use strict';
/* ───────── acciones ───────── */
async function loadFolderStat(){
  const el=$('#fstat');if(!S.folder){el.innerHTML='';return;}
  try{const f=await api('/api/folder?folder='+enc(S.folder));
    el.innerHTML=`<b>${f.total}</b> pistas · <span class="ok"><b>${f.done}</b> procesadas</span> · <span class="pe"><b>${f.pending}</b> pendientes</span> · ${f.cues?`cues <span class="ok">✓ ${f.cues}</span>`:'cues sin generar'}`;
  }catch(e){}
}
function acceptNext(){
  const r=S.rows[S.sel];if(!r)return;r.checked=true;r.reviewed=true;{const m=S.marks[r.original];if(m&&m.start!=null&&m.auto)m.ok=true;}patchCard(S.sel);queueSave();
  const v=visible().map(x=>x[1]),k=v.indexOf(S.sel);if(k>=0&&k<v.length-1)selectRow(v[k+1]);else ask('Última pista revisada ✓','Ya las has revisado todas. Pulsa «Aplicar + generar cues» arriba.','Vale',true);
}
function mkRow(r){return Object.assign({},r,{p:Object.assign({},r.parsed)});}
async function loadReview(folder){
  const d=await api('/api/review?folder='+enc(folder));S.folder=folder;S.cfg.folder=folder;S.marks={};
  S.rows=d.rows.map(r=>{const o=mkRow(r);if(r.marks)S.marks[r.original]=r.marks;return o;});
  S.done={apply:false,cues:false};S.sel=S.rows.length?0:-1;D.cache.clear();render();loadFolderStat();if(S.sel>=0)loadTrack(S.sel);
}
async function chooseFolder(){const r=await api('/api/pick',{kind:'folder'});if(!r.path)return;await startAnalyze(r.path);}
async function startAnalyze(folder){S.folder=folder;const j=await api('/api/analyze',{folder});if(j.error)return ask('Error',j.error,'Cerrar',true);await runJob('Analizando',j.job,()=>loadReview(folder));}
async function confirmApply(){
  const on=S.rows.filter(r=>r.checked);if(!on.length)return ask('Nada que aplicar','No hay filas marcadas con ✓.','Vale',true);
  if(!S.cfg.xml){const p=await api('/api/pick',{kind:'xml'});if(p.path){S.cfg.xml=p.path;await api('/api/cfg',{xml:p.path});}}
  const xml=!!S.cfg.xml;
  if(!await ask('Aplicar a '+on.length+' pistas',`Se renombrarán y se limpiarán los tags (título, artista, álbum, BPM y tono)${xml?', y se generará djflow_cues.xml con los cues.':'. Sin cues: falta elegir rekordbox.xml en Ajustes.'}\n\n${S.cfg.backup?'Se guarda copia de los originales: podrás deshacer.':'Sin copia de seguridad: no podrás deshacer.'}\nNo lo hagas con pistas que ya estén en Rekordbox.`,'Aplicar'))return;
  clearTimeout(S.saveT);await saveReview();
  const rows=S.rows.map(r=>({original:r.original,final:r.final,artist:r.artist,confidence:r.confidence,flags:r.flags,checked:r.checked,reviewed:r.reviewed}));
  trackSecs();
  const j=await api('/api/apply',{folder:S.folder,rows,marks:S.marks,backup:S.cfg.backup,cues:xml});
  await runJob('Aplicando',j.job,async()=>{S.done={apply:true,cues:xml};S.st=await api('/api/state');S.st.undo=true;loadFolderStat();S.rows=[];S.sel=-1;stopPlay();D.buf=null;updateTop(null);setMsg('');render();drawDeck();
    ask('Listo ✓',xml?'Nombres, tags y cues listos.\n\nEn Rekordbox:\n1. Preferencias › Avanzado › Base de datos › Biblioteca importada: elige djflow_cues.xml de la carpeta.\n2. Panel «rekordbox xml» › djflow: arrastra las pistas a tu colección.':'Nombres y tags aplicados.','Entendido',true);});
}
async function onCta(){
  if(!S.rows.length&&S.done.cues){await api('/api/reveal',{path:S.folder+'/djflow_cues.xml'});return;}
  if(!S.rows.length)return chooseFolder();
  if(S.done.cues)return;confirmApply();
}
async function doUndo(){
  if(!await ask('Deshacer última tanda','Se restaurarán los archivos originales (nombre, tags y portada). Si ya los importaste a Rekordbox, tendrás que volver a localizarlos.','Deshacer'))return;
  const j=await api('/api/undo',{folder:''});await runJob('Deshaciendo',j.job,async()=>{S.st=await api('/api/state');S.done={apply:false,cues:false};S.rows=[];render();});
}

