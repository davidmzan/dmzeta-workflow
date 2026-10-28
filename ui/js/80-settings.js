'use strict';
/* ───────── ajustes ───────── */
function renderDrawer(){
  const c=S.cfg,st=S.st,short=p=>p.split('/').slice(-2).join('/');
  $('#drawer').innerHTML=`<h3>Ajustes <button class="ico" id="dClose">✕</button></h3>
  <div class="sec"><h4>rekordbox.xml</h4><p>Se usa para aprender tus cues (INTRO, A, B, C), detectar duplicados y generar los cues de las pistas nuevas.</p>
    <div class="path">${c.xml?esc(c.xml):'Sin elegir'}</div><button class="btn sm" id="dXml">Elegir rekordbox.xml</button></div>
  <div class="sec"><h4>Aprender de mi biblioteca</h4><p>Carpetas con pistas ya bien nombradas. ${st.model?'Modelo entrenado ✓':'Aún sin entrenar.'} · ${st.learned||0} ejemplos guardados de tus correcciones.${st.new_examples?` <b style="color:#fbbf24">${st.new_examples} nuevos desde el último entrenamiento: pulsa Entrenar para que los use.</b>`:''}</p>
    ${(c.train||[]).map(p=>`<div class="path">${esc(short(p))}</div>`).join('')||'<div class="path">Ninguna carpeta añadida</div>'}
    <div style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn sm" id="dAdd">Añadir carpeta</button><button class="btn sm" id="dClr">Vaciar</button><button class="btn sm pri" id="dTrain">Entrenar</button></div></div>
  <div class="sec"><h4>START MIX, color del cue C, género, categoría y estrellas</h4><p>Aprende dónde pones START MIX, cuándo el cue C es rojo (voz antes del final del extender) o verde lima, y el género de tus pistas (campo Genre del XML), mirando tu colección (necesita los archivos de audio donde indica el XML). La primera vez tarda 20–40 min. ${st.marks_model?'Modelo entrenado ✓':'Aún sin entrenar.'}</p><button class="btn sm pri" id="dMarks">Aprender START MIX, color C y género</button></div>
  <div class="sec"><div class="line"><div><h4 style="margin:0 0 4px">Aprendizaje automático</h4><p style="margin:0">Tras cada Aplicar guarda tus correcciones y marcas, y reentrena solo al juntar ${c.auto_n||10} nuevas (guarda copia del modelo anterior). Nuevas ahora: ${st.new_examples||0} de nombres · ${st.new_marks||0} de START MIX. Grid: ${st.grid_samples||0} ajustes tuyos aprendidos${st.grid_bias_ms?` (corrección ${st.grid_bias_ms>0?'+':''}${st.grid_bias_ms} ms)`:''}.</p></div><div class="switch ${c.auto_learn!==false?'on':''}" id="dAL"></div></div></div>
  <div class="sec"><h4>Grid</h4><p>Recalcula el grid de todas las pistas de la carpeta actual desde cero (también las ya procesadas). Para una sola pista usa ⟳ REANALIZAR en la onda.</p><button class="btn sm" id="dRegrid">Reanalizar grid de la carpeta</button></div>
  <div class="sec"><h4>Calidad de los modelos</h4><p>Cada reentrenamiento queda anotado: con cuántos ejemplos (y cuántos tuyos), cuánto acierta y contra qué referencia. Un modelo solo se usa si supera a la referencia. Lo que corriges pesa 6 veces más que lo que das por bueno con ✓; lo que no revisas no se aprende.</p><div id="dQual" class="qual">Cargando…</div></div>
  <div class="sec"><h4>Desfase de exportación MP3 (ms)</h4><p>El desfase propio de cada MP3 con cabecera LAME (~38 ms) se compensa solo. Aquí va un ajuste fino extra, igual para todos los MP3: normalmente 0. Positivo = los cues y el grid se mueven más tarde.</p><input class="fld" id="dOff" type="number" step="5" value="${c.export_offset_ms||0}" style="width:120px"></div>
  <div class="sec"><div class="line"><div><h4 style="margin:0 0 4px">Copia de seguridad</h4><p style="margin:0">Guarda los originales antes de renombrar para poder deshacer.</p></div><div class="switch ${c.backup?'on':''}" id="dBk"></div></div></div>
  <div class="sec"><h4>Atajos</h4><div class="keys"><b>Espacio</b>Reproducir / pausa<b>↑ ↓</b>Pista anterior / siguiente<b>← →</b>Atrás / adelante 1 compás (Shift = 4)<b>S · E · L · X</b>START MIX · END MIX · Loop · Quitar<b>[ ]</b>Grid ±1 beat<b>, .</b>Grid ± los ms que pongas (por defecto 5)<b>M</b>Clics de compás<b>+ −</b>Zoom<b>Enter</b>Aceptar y pasar a la siguiente<b>C</b>Marcar / desmarcar ✓<b>1-8</b>Cues A-H: saltar / poner aquí (Shift = quitar)<b>N</b>Memory cue libre en el cursor<b>Q</b>Quantize<b>K · J</b>Marca y reproducir desde ella<b>G</b>Grid aquí</div></div>`;
  $('#dClose').onclick=()=>$('#drawer').classList.remove('show');
  $('#dXml').onclick=async()=>{const p=await api('/api/pick',{kind:'xml'});if(p.path){c.xml=p.path;await api('/api/cfg',{xml:p.path});renderDrawer();}};
  $('#dAdd').onclick=async()=>{const p=await api('/api/pick',{kind:'folder'});if(p.path&&!c.train.includes(p.path)){c.train.push(p.path);await api('/api/cfg',{train:c.train});renderDrawer();}};
  $('#dClr').onclick=async()=>{c.train=[];await api('/api/cfg',{train:[]});renderDrawer();};
  $('#dRegrid').onclick=regridAll;
  loadQuality();
  $('#dOff').onchange=async e=>{c.export_offset_ms=parseFloat(e.target.value)||0;await api('/api/cfg',{export_offset_ms:c.export_offset_ms});};
  $('#dAL').onclick=async()=>{c.auto_learn=!(c.auto_learn!==false);await api('/api/cfg',{auto_learn:c.auto_learn});renderDrawer();};
  $('#dBk').onclick=async()=>{c.backup=!c.backup;await api('/api/cfg',{backup:c.backup});renderDrawer();};
  $('#dTrain').onclick=async()=>{if(!c.train.length&&!st.learned)return ask('Falta algo','Añade al menos una carpeta con pistas ya nombradas.','Vale',true);$('#drawer').classList.remove('show');const j=await api('/api/train',{});await runJob('Entrenando',j.job,async j2=>{S.st=await api('/api/state');ask('Entrenamiento listo',j2.result||'','Genial',true);});};
  $('#dMarks').onclick=async()=>{if(!c.xml)return ask('Falta el XML','Elige primero tu rekordbox.xml.','Vale',true);if(!await ask('Aprender START MIX','Analiza el audio de tus pistas con START MIX. La primera vez puede tardar 20–40 minutos.','Empezar'))return;$('#drawer').classList.remove('show');const j=await api('/api/train_marks',{});await runJob('Aprendiendo START MIX',j.job,async j2=>{S.st=await api('/api/state');ask('START MIX aprendido',j2.result||'','Genial',true);});};
}

