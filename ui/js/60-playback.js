'use strict';
/* reproducción + clics de compás */
function stopSrc(){const s=D.src;D.src=null;if(s){try{s.onended=null;s.stop();}catch(e){}}clearInterval(D.timer);}
function startPlay(from){
  if(!D.buf)return;const ctx=AC();if(ctx.state==='suspended')ctx.resume();stopSrc();
  const s=ctx.createBufferSource();s.buffer=D.buf;s.connect(ctx.destination);D.startedAt=ctx.currentTime-from;s.start(0,from);D.src=s;D.playing=true;
  s.onended=()=>{if(D.src===s){D.playing=false;D.pos=D.dur;stopSrc();drawDeck();}};
  D.nextBar=Math.max(0,Math.ceil((from-D.t0)/barLen()-1e-6));D.timer=setInterval(sched,25);sched();tick();
}
function stopPlay(){if(D.playing)D.pos=curPos();stopSrc();D.playing=false;drawDeck();}
function togglePlay(){if(!D.buf)return;if(D.playing)stopPlay();else if(D.cuePt!=null)startPlay(D.cuePt);else startPlay(D.pos>=D.dur-.1?D.t0:D.pos);}
function beep(at,f,len,vol){const ctx=AC(),o=ctx.createOscillator(),g=ctx.createGain();o.type='sine';o.frequency.value=f;g.gain.setValueAtTime(.0001,at);g.gain.exponentialRampToValueAtTime(vol,at+.003);g.gain.exponentialRampToValueAtTime(.0001,at+len);o.connect(g);g.connect(ctx.destination);o.start(at);o.stop(at+len+.02);}
function sched(){
  if(!D.playing||!D.clicks||!D.bpm)return;const ctx=AC(),now=ctx.currentTime,r=curRow(),mk=curMarks(),bar=barLen();
  for(;;){const n=D.nextBar,at=D.startedAt+D.t0+n*bar;if(at>now+.18)break;
    if(at>=now-.02){if(r&&r.p.bars&&n===r.p.bars){beep(at,2600,.12,.55);beep(at+.1,2600,.12,.55);}
      else if(mk.start!=null&&n===mk.start)beep(at,1800,.1,.5);else if(mk.end!=null&&n===mk.end)beep(at,1400,.1,.5);else beep(at,1000,.05,.28);}
    D.nextBar=n+1;}
}
function tick(){
  if(!D.playing)return;const p=curPos(),[vs,ve]=D.view,span=ve-vs;if(p>ve-span*.08||p<vs)setView(p-span*.2,p+span*.8);
  drawDeck();requestAnimationFrame(tick);
}
async function fetchBuffer(r){
  if(DEMO)return synthBuffer(r.p.bpm||100);
  const res=await fetch(`/audio?folder=${enc(S.folder)}&name=${enc(r.original)}`,{headers:{'X-WF-Token':TOKEN}});if(!res.ok)throw new Error('audio '+res.status);
  const ab=await res.arrayBuffer();return AC().decodeAudioData(ab);
}
const MODEL_NAMES={names:'Nombres (compases, tipo…)',start_mix:'START MIX',cvox:'Color del cue C',genre:'Género',cat:'Categoría (color)',star:'Estrellas'};
async function loadQuality(){
  const el=$('#dQual');if(!el)return;
  try{
    const q=await api('/api/quality');if(!q.latest||!q.latest.length){el.textContent='Aún no hay entrenamientos anotados. Aparecerán aquí tras «Aprender» o tras unas cuantas correcciones tuyas.';return;}
    const pct=v=>v==null?'—':Math.round(v*100)+' %';
    el.innerHTML='<table style="width:100%;border-collapse:collapse;font-size:12px"><tr style="opacity:.6;text-align:left"><th>Modelo</th><th>Ejemplos</th><th>Tuyos</th><th>Acierto</th><th>Referencia</th><th>Estado</th></tr>'+
      q.latest.map(e=>`<tr style="border-top:1px solid var(--line)"><td>${esc(MODEL_NAMES[e.model]||e.model)}<div style="opacity:.5;font-size:10px">${esc(e.when||'')}</div></td><td>${e.n??'—'}</td><td>${e.n_user??'—'}</td><td>${pct(e.accuracy)}</td><td>${pct(e.baseline)}</td><td>${e.enabled===false?'<span style="color:#f59e0b">apagado</span>':'<span style="color:#34d399">activo</span>'}</td></tr>`).join('')+'</table>';
    const bf=q.bpm_fixes;if(bf&&bf.total)el.innerHTML+=`<p style="font-size:12px;opacity:.75;margin-top:8px">Correcciones de BPM: <b>${bf.total}</b>, de ellas ×2 / ×0,5: <b>${bf.double_half}</b>.</p>`;
  }catch(e){el.textContent='No se pudo cargar la calidad de los modelos.';}
}
async function regrid(r){
  const info=await api(`/api/track?folder=${enc(S.folder)}&name=${enc(r.original)}&bpm=${r.p.bpm||''}&fresh=1`);
  const mk=S.marks[r.original]||(S.marks[r.original]={});delete mk.t0;delete mk.bpm;D.cache.delete(r.original);r.reviewed=true;patchCard(S.rows.indexOf(r));queueSave();return info;
}
async function regridAll(){
  if(!S.rows.length)return;if(!await ask('Reanalizar el grid de toda la carpeta','Recalcula el grid de las '+S.rows.length+' pistas desde cero y descarta los grids/BPM ajustados a mano. No toca nombres ni cues. Tarda unos segundos por pista.','Reanalizar'))return;
  $('#drawer').classList.remove('show');let n=0;
  for(const r of S.rows){n++;setMsg(`Reanalizando grid ${n}/${S.rows.length}…`,true);try{await regrid(r);}catch(e){}}
  await loadTrack(S.sel);setMsg(`Grid reanalizado en ${n} pistas ✓`);
}
async function loadTrack(i){
  const r=S.rows[i];if(!r)return;stopPlay();const g=++D.gen;D.cuePt=null;D.buf=null;D.pos=0;D.name=r.original;updateTop(r);setMsg('Cargando onda…',true);drawDeck();
  try{
    let c=D.cache.get(r.original);
    if(!c){const [info,buf]=await Promise.all([api(`/api/track?folder=${enc(S.folder)}&name=${enc(r.original)}&bpm=${r.p.bpm||''}`),fetchBuffer(r)]);c={info,buf,peaks:buildPeaks(buf)};D.cache.set(r.original,c);if(D.cache.size>5)D.cache.delete(D.cache.keys().next().value);}
    if(g!==D.gen)return;
    D.buf=c.buf;D.peaks=c.peaks;D.sr=c.buf.sampleRate;D.dur=c.buf.duration;D.bpmdet=c.info.bpm||r.p.bpm||0;D.t0det=c.info.t0||0;D.ccol=c.info.ccol||null;
    const mk=S.marks[r.original]||{};D.bpm=mk.bpm||D.bpmdet;D.t0=mk.t0!=null?mk.t0:D.t0det;D.pos=D.t0;
    if(!mk.loop&&!mk.noLoop&&D.bpm&&D.dur){const bl=240/D.bpm,tb=Math.floor((D.dur-D.t0)/bl),ll=D.loopLen||8;if(tb>ll+8){mk.loop=[tb-ll,ll];mk.loopAuto=true;S.marks[r.original]=mk;}}
    const st=Math.max(0,D.t0-2*barLen()),sp=(D.bpm?32*barLen():30);setView(st,st+sp);setMsg('');updateTop(r);drawDeck();
  }catch(e){if(g===D.gen)setMsg('No se pudo cargar el audio ('+e.message+')');}
}
function updateTop(r){
  {const bi=$('#bpmIn');if(bi&&document.activeElement!==bi)bi.value=D.bpm?D.bpm.toFixed(2):'';}
  $('#dName').textContent=r?(r.final||r.original):'Sin pista seleccionada';
  const k=$('#dKey'),b=$('#dBpm'),kb=keyBadge(r&&r.p.key);k.style.display=r&&r.p.key?'':'none';k.textContent=kb.t;k.style.background=kb.bg;k.style.color='#0b0b10';
  b.style.display=D.bpm?'':'none';b.textContent=(D.bpm?D.bpm.toFixed(2):'')+' BPM';
}
function addMem(){const k=['B','C','D','F'].find(x=>!memList().find(q=>q.k===x&&q.b!=null));if(k)memAct(k,false);}
function padAct(k,rm){
  const r=curRow();if(!r||!D.buf||!D.bpm)return;const mk=curMarks(),q=cuesList().find(x=>x.k===k);if(!q)return;const has=q.t!=null;
  if(has&&!rm){jumpTo(q.t);return;}
  if(k==='E'){markHere('start');return;}if(k==='H'){markHere('loop');return;}
  mk.hot=mk.hot||{};if(has&&rm)mk.hot[k]=false;else mk.hot[k]=+((snap(curPos())-D.t0)/barLen()).toFixed(4);
  r.reviewed=true;patchCard(S.sel);queueSave();drawDeck();
}
function bindBpm(){
  const el=$('#bpmIn');
  el.addEventListener('wheel',e=>{e.preventDefault();const dy=e.deltaY||e.deltaX;if(!dy)return;const st=e.shiftKey?.1:e.altKey?.001:.01;nudgeBpm((dy<0?1:-1)*st);},{passive:false});
  el.addEventListener('change',()=>{const v=parseFloat(el.value);if(v>=40&&v<=240&&D.bpm)nudgeBpm(v-D.bpm);});
  el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key==='Escape')el.blur();});
}
function nudgeBpm(d){
  const r=curRow();if(!r||!D.buf||!D.bpm)return;const mk=curMarks(),pos=curPos(),n=Math.round((pos-D.t0)/beatLen()),anchor=D.t0+n*beatLen();
  D.bpm=Math.max(40,Math.min(240,+(D.bpm+d).toFixed(3)));mk.bpm=D.bpm;D.t0=anchor-n*beatLen();while(D.t0<0)D.t0+=beatLen();mk.t0=+D.t0.toFixed(4);
  r.reviewed=true;patchCard(S.sel);queueSave();updateTop(r);if(D.playing)startPlay(curPos());drawDeck();
}
function gridHere(){const r=curRow();if(!r||!D.buf)return;D.t0=Math.max(0,curPos());curMarks().t0=+D.t0.toFixed(4);r.reviewed=true;patchCard(S.sel);queueSave();if(D.playing)startPlay(curPos());drawDeck();}
function setCuePt(){if(!D.buf)return;if(D.cuePt!=null){D.cuePt=null;drawDeck();return;}D.cuePt=snap(curPos());startPlay(D.cuePt);drawDeck();}
function goCuePt(){if(!D.buf||D.cuePt==null)return;startPlay(D.cuePt);}
function snap(t){if(!D.q||!D.bpm)return t;const bl=beatLen();return Math.max(0,D.t0+Math.round((t-D.t0)/bl)*bl);}
function markHere(kind){
  const r=curRow();if(!r||!D.buf||!D.bpm)return;const mk=curMarks(),raw=(curPos()-D.t0)/barLen(),b=D.q?Math.round(raw):+raw.toFixed(4);
  if(kind==='start'){if(mk.start!=null)delete mk.start;else{mk.start=b;if(mk.end==null&&!mk.noEnd)mk.end=b+((S.rules&&S.rules.gap)||8);}delete mk.auto;}else if(kind==='end'){if(mk.end!=null){delete mk.end;mk.noEnd=true;}else{mk.end=b;delete mk.noEnd;}}else if(kind==='loop'){if(mk.loop){delete mk.loop;mk.noLoop=true;delete mk.loopAuto;}else{mk.loop=[b,D.loopLen||8];delete mk.noLoop;delete mk.loopAuto;}}else{delete mk.start;delete mk.end;delete mk.loop;delete mk.hot;delete mk.noEnd;mk.noLoop=true;delete mk.loopAuto;}
  r.reviewed=true;patchCard(S.sel);queueSave();drawDeck();
}
function stepMs(){const v=parseFloat($('#gStep').value);return (v>0?Math.min(v,500):5)/1000;}
function nudge(kind,v){
  const r=curRow();if(!r||!D.buf)return;const mk=curMarks();
  if(kind==='reset'){D.t0=D.t0det;delete mk.t0;D.bpm=D.bpmdet;delete mk.bpm;}else{D.t0=Math.max(0,D.t0+(kind==='beat'?v*beatLen():v));mk.t0=+D.t0.toFixed(4);}
  r.reviewed=true;patchCard(S.sel);queueSave();if(D.playing)startPlay(curPos());drawDeck();
}
function bindDeck(){
  const wf=$('#wf');let drag=null;
  wf.addEventListener('mousedown',e=>{drag={x:e.clientX,vs:D.view[0],moved:false,gm:D.gm||e.shiftKey,t0:D.t0};});
  window.addEventListener('mousemove',e=>{if(!drag||!D.buf)return;const dx=e.clientX-drag.x;if(Math.abs(dx)>4)drag.moved=true;if(drag.moved&&drag.gm){D.t0=Math.max(0,drag.t0+dx/(wf.clientWidth/(D.view[1]-D.view[0])));drawDeck();}else if(drag.moved){const span=D.view[1]-D.view[0];setView(drag.vs-dx/(wf.clientWidth/span),drag.vs-dx/(wf.clientWidth/span)+span);}});
  window.addEventListener('mouseup',e=>{if(drag&&drag.moved&&drag.gm&&D.buf){const r=curRow();if(r){curMarks().t0=+D.t0.toFixed(4);r.reviewed=true;patchCard(S.sel);queueSave();if(D.playing)startPlay(curPos());}}if(drag&&!drag.moved&&D.buf&&e.target===wf){const r=wf.getBoundingClientRect(),t=D.view[0]+(e.clientX-r.left)/r.width*(D.view[1]-D.view[0]);seek(snap(t));}drag=null;});
  wf.parentElement.addEventListener('wheel',e=>{if(!D.buf)return;e.preventDefault();const r=wf.getBoundingClientRect(),a=D.view[0]+(e.clientX-r.left)/r.width*(D.view[1]-D.view[0]);
    if(Math.abs(e.deltaX)>Math.abs(e.deltaY)*2.5){const sp=D.view[1]-D.view[0];setView(D.view[0]+e.deltaX/r.width*sp,D.view[0]+e.deltaX/r.width*sp+sp);}else zoom(Math.exp(e.deltaY*(e.ctrlKey?.012:.0045)),a);},{passive:false});
  // La app nunca hace zoom: se bloquea el zoom del navegador (pinch, Ctrl/⌘+rueda, Ctrl/⌘ +/−/0 y gestos de Safari). Solo hacen zoom la onda y la mini onda.
  window.addEventListener('wheel',e=>{if(e.ctrlKey||e.metaKey)e.preventDefault();},{passive:false});
  ['gesturestart','gesturechange','gestureend'].forEach(g=>document.addEventListener(g,e=>e.preventDefault()));
  window.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&['+','=','-','_','0'].includes(e.key))e.preventDefault();});
  const ov=$('#ov'),ovGo=e=>{if(!D.buf)return;const r=ov.getBoundingClientRect(),t=(e.clientX-r.left)/r.width*D.dur,sp=D.view[1]-D.view[0];setView(t-sp/2,t+sp/2);};let od=false;
  ov.addEventListener('wheel',e=>{if(!D.buf)return;e.preventDefault();const r=ov.getBoundingClientRect(),t=Math.max(0,Math.min(D.dur,(e.clientX-r.left)/r.width*D.dur)),sp=D.view[1]-D.view[0];
    if(Math.abs(e.deltaX)>Math.abs(e.deltaY)*2.5){const c=(D.view[0]+D.view[1])/2+e.deltaX/r.width*D.dur;setView(c-sp/2,c+sp/2);}
    else{const ns=Math.min(D.dur,Math.max(0.8,sp*Math.exp(e.deltaY*(e.ctrlKey?.012:.0045))));setView(t-ns/2,t+ns/2);}},{passive:false});   // rueda sobre la mini onda: zoom de la onda grande centrado donde apuntas
  ov.addEventListener('mousedown',e=>{od=true;ovGo(e);seek((e.clientX-ov.getBoundingClientRect().left)/ov.clientWidth*D.dur);});window.addEventListener('mousemove',e=>{if(od)ovGo(e);});window.addEventListener('mouseup',()=>od=false);
  $('#tPlay').onclick=togglePlay;$('#tStart').onclick=()=>seek(D.t0);$('#tCut').onclick=()=>{const r=curRow();if(r&&r.p.bars&&D.bpm){const t=D.t0+r.p.bars*barLen();seek(t-4*barLen());const sp=D.view[1]-D.view[0];setView(t-sp*.35,t+sp*.65);}};
  $('#lLen').onchange=e=>{D.loopLen=+e.target.value;const r=curRow(),m=curMarks();if(r&&m.loop){m.loop[1]=D.loopLen;delete m.loopAuto;r.reviewed=true;patchCard(S.sel);queueSave();}drawDeck();};$('#tMk').onclick=setCuePt;$('#tQ').onclick=()=>{D.q=!D.q;drawDeck();};$('#tClk').onclick=()=>{D.clicks=!D.clicks;if(D.playing)startPlay(curPos());drawDeck();};
  $('#tZp').onclick=()=>zoom(.6);$('#tZm').onclick=()=>zoom(1.7);$('#tFit').onclick=()=>setView(0,D.dur);
  $('#gMm').onclick=()=>nudge('ms',-stepMs());$('#gMp').onclick=()=>nudge('ms',stepMs());$('#gR').onclick=()=>nudge('reset');$('#gRe').onclick=async()=>{const r=curRow();if(!r)return;setMsg('Reanalizando grid…',true);await regrid(r);await loadTrack(S.sel);};bindBpm();$('#gDrag').onclick=()=>{D.gm=!D.gm;drawDeck();};
  $('#pads').onclick=e=>{const b=e.target.closest('.pad');if(b)padAct(b.dataset.k,e.shiftKey||e.altKey);};
  $('#mpads').onclick=e=>{const b=e.target.closest('.pad');if(b){D.memSel=b.dataset.k;memAct(b.dataset.k,e.shiftKey||e.altKey);drawDeck();}};
  $('#mpads').oncontextmenu=e=>{e.preventDefault();const b=e.target.closest('.pad');if(b)memAct(b.dataset.k,true);};
  $('#mpads').ondblclick=e=>{const b=e.target.closest('.pad');if(b){e.stopPropagation();openMemPal(b.dataset.k);}};
  $('#memCol').onclick=e=>{e.stopPropagation();$('#pal').classList.remove('show');if($('#palM').classList.contains('show'))$('#palM').classList.remove('show');else openMemPal();};
  $('#palM').onclick=e=>{e.stopPropagation();const b=e.target.closest('.sw');if(!b)return;if(b.dataset.auto)setMemCol(null);else setMemCol(b.dataset.c.split(',').map(Number));};
  $('#cColBtn').onclick=e=>{e.stopPropagation();$('#palM').classList.remove('show');renderPal();$('#pal').classList.toggle('show');};
  $('#pal').onclick=e=>{e.stopPropagation();const b=e.target.closest('.sw');if(!b)return;if(b.dataset.auto)setCCol(null);else setCCol(b.dataset.c.split(',').map(Number));$('#pal').classList.remove('show');};
  document.addEventListener('click',()=>{$('#pal').classList.remove('show');$('#palM').classList.remove('show');});
  $('#pads').oncontextmenu=e=>{e.preventDefault();const b=e.target.closest('.pad');if(b)padAct(b.dataset.k,true);};
  $('#pads').title='Clic: saltar al cue (o ponerlo en el cursor si está vacío) · Shift+clic o clic derecho: quitarlo · Teclas 1-8';
  window.addEventListener('resize',drawDeck);
}

