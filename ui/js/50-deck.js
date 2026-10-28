'use strict';
/* ───────── DECK: onda, reproductor, marcas ───────── */
const AC=()=>D.ctx||(D.ctx=new (window.AudioContext||window.webkitAudioContext)());
const barLen=()=>240/(D.bpm||120), beatLen=()=>60/(D.bpm||120);
const fmt=t=>{t=Math.max(0,t||0);return Math.floor(t/60)+':'+(t%60).toFixed(1).padStart(4,'0');};
const curRow=()=>S.rows[S.sel];
const curMarks=()=>{const r=curRow();return r?(S.marks[r.original]||(S.marks[r.original]={})):{};};
const curPos=()=>D.playing?Math.min(D.dur,AC().currentTime-D.startedAt):D.pos;
function fitCanvas(cv){const d=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;if(cv.width!==Math.round(w*d)||cv.height!==Math.round(h*d)){cv.width=Math.round(w*d);cv.height=Math.round(h*d);}const c=cv.getContext('2d');c.setTransform(d,0,0,d,0,0);return{c,W:w,H:h};}

function buildPeaks(buf){
  const a=buf.getChannelData(0),b=buf.numberOfChannels>1?buf.getChannelData(1):null,n=a.length,base=64,nb=Math.ceil(n/base);
  let mn=new Float32Array(nb),mx=new Float32Array(nb);
  for(let i=0;i<nb;i++){let lo=1,hi=-1;const s=i*base,e=Math.min(n,s+base);for(let k=s;k<e;k++){const v=b?(a[k]+b[k])*.5:a[k];if(v<lo)lo=v;if(v>hi)hi=v;}mn[i]=lo;mx[i]=hi;}
  const L=[{size:base,mn,mx}];
  while(L[L.length-1].mn.length>400){const p=L[L.length-1],m=Math.ceil(p.mn.length/4),n2=new Float32Array(m),x2=new Float32Array(m);
    for(let i=0;i<m;i++){let lo=1,hi=-1;for(let k=i*4;k<Math.min(p.mn.length,i*4+4);k++){if(p.mn[k]<lo)lo=p.mn[k];if(p.mx[k]>hi)hi=p.mx[k];}n2[i]=lo;x2[i]=hi;}
    L.push({size:p.size*4,mn:n2,mx:x2});}
  return L;
}
function colPeak(spp,a){ // devuelve [min,max] para un rango de muestras
  const L=D.peaks;let lv=L[0];for(const l of L){if(l.size<=spp)lv=l;else break;}
  const i0=Math.floor(a/lv.size),i1=Math.max(i0+1,Math.ceil((a+spp)/lv.size));let lo=1,hi=-1;
  for(let i=i0;i<Math.min(i1,lv.mn.length);i++){if(lv.mn[i]<lo)lo=lv.mn[i];if(lv.mx[i]>hi)hi=lv.mx[i];}
  return lo>hi?null:[lo,hi];
}
const PAL=[['Rojo',[230,40,40]],['Naranja',[224,100,27]],['Amarillo',[180,190,4]],['Lima',[165,225,22]],['Verde',[40,226,20]],['Verde azulado',[16,177,118]],['Cian',[0,224,255]],['Azul claro',[80,180,255]],['Azul',[48,90,255]],['Morado',[180,50,255]],['Rosa',[255,18,123]],['Fucsia',[222,68,207]]];
const rgbHex=c=>'#'+c.map(v=>v.toString(16).padStart(2,'0')).join('');
function cColor(){const mk=curMarks();if(Array.isArray(mk.ccol))return rgbHex(mk.ccol);return D.ccol==='red'?'#e62828':'#a5e116';}
function renderPal(){const mk=curMarks(),cur=Array.isArray(mk.ccol)?mk.ccol.join(','):'';
  $('#pal').innerHTML=`<button class="sw ${cur?'':'on'}" data-auto="1" style="background:#2a2a3a" title="Automático (el detectado)">A</button>`+PAL.map(([n,c])=>`<button class="sw ${cur===c.join(',')?'on':''}" data-c="${c.join(',')}" title="${n}" style="background:${rgbHex(c)}"></button>`).join('');}
function setCCol(c){const r=curRow();if(!r)return;const mk=curMarks();if(c)mk.ccol=c;else delete mk.ccol;r.reviewed=true;patchCard(S.sel);queueSave();renderPal();drawDeck();}
function cuesList(){
  const mk=curMarks(),T=b=>D.t0+b*barLen(),R=Object.assign({a:0,b:4,c:8,off5:4,gap:8},S.rules||{}),hot=mk.hot||{},o=[];
  const pos=(k,def)=>hot[k]===false?null:(typeof hot[k]==='number'?hot[k]:def);
  const add=(k,c,b,lab,txt)=>o.push(b==null?{k,c}:{k,c,t:T(b),b,txt:txt!=null?txt:String(Math.round(b*4)/4),lab});
  const baseA=typeof hot.A==='number'?hot.A:R.a;      // B y C siguen al A si lo mueves
  add('A','#28e214',pos('A',R.a),'INTRO','Intro');add('B','#28e214',pos('B',baseA+(R.b-R.a)));add('C',cColor(),pos('C',baseA+(R.c-R.a)));add('D','#7c5cff',pos('D',null));
  add('E','#10b176',mk.start!=null?mk.start:null,'START MIX','START');
  add('F','#10b176',pos('F',mk.start!=null?mk.start+R.off5:null));
  add('G','#10b176',pos('G',null));
  if(mk.loop)o.push({k:'H',t:T(mk.loop[0]),b:mk.loop[0],c:'#ff127b',txt:'LOOP '+mk.loop[1],lab:'END LOOP',len:mk.loop[1]*barLen()});else o.push({k:'H',c:'#ff127b'});
  return o;
}
const ORANGE='#e0641b',YELLOW='#b4be04',MEMDEF={A:'#28e214',E:ORANGE,G:ORANGE,H:'#e62828'};
function memColorOf(k){const mk=curMarks(),c=(mk.mcol||{})[k];if(Array.isArray(c))return rgbHex(c);if(k==='G'&&mk.endWarn)return YELLOW;return MEMDEF[k]||'#cbd5e1';}
function memList(){
  const mk=curMarks(),T=b=>D.t0+b*barLen(),cl=cuesList(),ma=mk.memAuto||{},A=cl.find(x=>x.k==='A');
  mk.mem=mk.mem||[];const free=['B','C','D','F'];mk.mem.forEach(m=>{if(!m.s){const used=mk.mem.map(x=>x.s);m.s=free.find(f=>!used.includes(f))||'F';}});
  const mn=mk.mname||{},gp=(mk.start!=null&&mk.end!=null)?Math.round(mk.end-mk.start):8,defN={A:'INTRO',E:(gp===8||gp===16)?'START MIX '+gp:'START MIX',G:'END MIX',H:'END LOOP'},nameOf=k=>mn[k]||defN[k];
  const au=(key,def)=>ma[key]===false?null:(typeof ma[key]==='number'?ma[key]:def);
  const item=(k,c,b,txt,extra)=>Object.assign(b==null?{k,c}:{k,c,b,t:T(b),txt},extra||{});
  const cust=k=>{const m=mk.mem.find(x=>x.s===k);return item(k,memColorOf(k),m?m.b:null,m?(m.n||'MEM'):'',{custom:true,m});};
  return [
    item('A',memColorOf('A'),au('intro',A&&A.b!=null?A.b:0),nameOf('A'),{key:'intro',def:defN.A}),cust('B'),cust('C'),cust('D'),
    item('E',memColorOf('E'),au('start',mk.start!=null?mk.start:null),nameOf('E'),{key:'start',def:defN.E}),cust('F'),
    item('G',memColorOf('G'),mk.end!=null?mk.end:null,nameOf('G'),{key:'end',def:defN.G}),
    item('H',memColorOf('H'),au('loop',mk.loop?mk.loop[0]:null),nameOf('H'),{key:'loop',def:defN.H})
  ];
}
function jumpTo(t){seek(t);const sp=D.view[1]-D.view[0];setView(t-sp*.3,t+sp*.7);if(D.cuePt!=null&&!D.playing)startPlay(t);}
function renderMemPal(){
  const k=D.memSel||'G',mk=curMarks(),q=memList().find(x=>x.k===k),cur=Array.isArray((mk.mcol||{})[k])?mk.mcol[k].join(','):'';
  const nm=(q&&q.txt)||('Memory cue '+k);
  $('#palM').innerHTML=`<div class="pm-h">Color de: <b style="color:#fff">${nm}</b>${q&&q.b==null?' (vacío: ponlo primero)':''}</div>`+(q&&(q.custom?q.m:true)?`<input id="pmName" placeholder="${esc(q.def||'Nombre del memory cue')}" value="${esc(q.custom?(q.m.n||''):((mk.mname||{})[k]||''))}">`:'')+
   `<button class="sw ${cur?'':'on'}" data-auto="1" style="background:#2a2a3a" title="Automático (el de siempre)">A</button>`+PAL.map(([n,c])=>`<button class="sw ${cur===c.join(',')?'on':''}" data-c="${c.join(',')}" title="${n}" style="background:${rgbHex(c)}"></button>`).join('');
  const pn=$('#pmName');if(pn){pn.onclick=e=>e.stopPropagation();pn.oninput=e=>{const v=e.target.value;if(q.custom)q.m.n=v;else{mk.mname=mk.mname||{};if(v.trim())mk.mname[k]=v;else delete mk.mname[k];}const r=curRow();if(r){r.reviewed=true;}queueSave();drawDeck();};pn.onkeydown=e=>{e.stopPropagation();if(e.key==='Enter'||e.key==='Escape')$('#palM').classList.remove('show');};}
}
function setMemCol(c){const r=curRow();if(!r)return;const mk=curMarks(),k=D.memSel||'G';mk.mcol=mk.mcol||{};if(c){mk.mcol[k]=c;if(k==='G')delete mk.endWarn;}else{delete mk.mcol[k];if(k==='G')delete mk.endWarn;}r.reviewed=true;patchCard(S.sel);queueSave();renderMemPal();drawDeck();}
function openMemPal(k){if(k)D.memSel=k;renderMemPal();$('#palM').classList.add('show');drawDeck();setTimeout(()=>{const p=$('#pmName');if(p){p.focus();p.select();}},0);}
function memAct(k,rm){
  const r=curRow();if(!r||!D.buf||!D.bpm)return;const mk=curMarks(),q=memList().find(x=>x.k===k);if(!q)return;const has=q.b!=null,here=+((snap(curPos())-D.t0)/barLen()).toFixed(4);
  if(has&&!rm){jumpTo(q.t);return;}
  mk.memAuto=mk.memAuto||{};mk.mem=mk.mem||[];
  if(q.custom){if(has&&rm)mk.mem.splice(mk.mem.indexOf(q.m),1);else mk.mem.push({b:here,n:'',s:k});}
  else if(q.key==='end'){markHere('end');return;}
  else{if(has&&rm)mk.memAuto[q.key]=false;else mk.memAuto[q.key]=here;}
  r.reviewed=true;patchCard(S.sel);queueSave();drawDeck();
}
function renameMem(k){const mk=curMarks(),m=(mk.mem||[]).find(x=>x.s===k);if(!m)return;const n=prompt('Nombre del memory cue',m.n||'');if(n===null)return;m.n=n.trim();queueSave();drawDeck();}
function drawWF(){
  const cv=$('#wf'),{c,W,H}=fitCanvas(cv);c.clearRect(0,0,W,H);
  if(!D.buf)return;
  const [vs,ve]=D.view,span=ve-vs,pps=W/span,top=24,mid=(H+top)/2,amp=(H-top)/2-6,X=t=>(t-vs)*pps,bar=barLen(),beat=beatLen(),pos=curPos();
  // rejilla
  if(D.bpm){
    c.lineWidth=1;const n0=Math.floor((vs-D.t0)/beat);
    for(let n=n0;D.t0+n*beat<=ve;n++){const t=D.t0+n*beat,x=X(t),isBar=((n%4)+4)%4===0;if(t<0)continue;if(!isBar&&pps*beat<10)continue;if(isBar&&pps*bar<14&&((n/4)%8!==0))continue;
      c.strokeStyle=isBar?'rgba(255,255,255,.22)':'rgba(255,255,255,.07)';c.beginPath();c.moveTo(x+.5,top);c.lineTo(x+.5,H);c.stroke();
      if(isBar&&((n/4)%4===0)&&pps*bar>12){c.fillStyle='rgba(255,255,255,.45)';c.font='10px ui-monospace,Menlo,monospace';c.fillText(String(n/4),x+4,top+11);}}
  }
  // loop region
  const cl=cuesList(),H8=cl.find(q=>q.k==='H');
  if(H8&&H8.t!=null){c.fillStyle='rgba(236,72,153,.16)';c.fillRect(X(H8.t),top,H8.len*pps,H-top);c.strokeStyle='rgba(236,72,153,.8)';c.strokeRect(X(H8.t)+.5,top+.5,H8.len*pps,H-top-1);}
  // onda
  const g=c.createLinearGradient(0,mid-amp,0,mid+amp);g.addColorStop(0,'#ff3d8b');g.addColorStop(.32,'#7c5cff');g.addColorStop(.5,'#22d3ee');g.addColorStop(.68,'#7c5cff');g.addColorStop(1,'#ff3d8b');
  const spp=span*D.sr/W,px=X(pos);c.fillStyle=g;
  for(let x=0;x<W;x+=1){const a=(vs+x/pps)*D.sr;if(a<0||a>=D.buf.length)continue;const p=colPeak(spp,a);if(!p)continue;
    c.globalAlpha=x<px?1:.6;const y1=mid-Math.min(1,p[1]*1.0)*amp,y2=mid-Math.max(-1,p[0]*1.0)*amp;c.fillRect(x,y1,1,Math.max(1,y2-y1));}
  c.globalAlpha=1;
  if(D.cuePt!=null){const x=X(D.cuePt);if(x>=-2&&x<=W+2){c.strokeStyle='#22d3ee';c.lineWidth=2;c.beginPath();c.moveTo(x,top);c.lineTo(x,H);c.stroke();c.fillStyle='#22d3ee';c.beginPath();c.moveTo(x,top);c.lineTo(x+14,top+6);c.lineTo(x,top+12);c.fill();}}
  {c.font='10px ui-monospace,Menlo,monospace';memList().forEach(q=>{if(q.b==null||!q.custom&&q.k!=='G')return;const x=X(q.t);if(x<-2||x>W+2)return;c.strokeStyle=q.k==='G'?q.c:'rgba(229,231,235,.75)';c.lineWidth=1.5;c.beginPath();c.moveTo(x,top);c.lineTo(x,H);c.stroke();c.fillStyle=q.c;c.beginPath();c.moveTo(x,H-14);c.lineTo(x+10,H-8);c.lineTo(x,H-2);c.fill();if(q.custom&&q.m&&q.m.n)c.fillText(q.m.n,x+13,H-5);});}
  // corte del extender
  const r=curRow();
  if(r&&r.p.bars&&D.bpm){const x=X(D.t0+r.p.bars*bar);if(x>=-2&&x<=W+2){c.strokeStyle='#fbbf24';c.lineWidth=2;c.setLineDash([6,4]);c.beginPath();c.moveTo(x,top);c.lineTo(x,H);c.stroke();c.setLineDash([]);
    c.fillStyle='#fbbf24';c.font='700 10px -apple-system,sans-serif';c.fillText('CORTE · '+r.p.bars+' BARS',x+6,H-8);}}
  // cues
  for(const q of cl){if(q.t==null)continue;const x=X(q.t);if(x<-20||x>W+20)continue;
    c.strokeStyle=q.c;c.globalAlpha=.85;c.lineWidth=2;c.beginPath();c.moveTo(x,0);c.lineTo(x,H);c.stroke();c.globalAlpha=1;
    c.fillStyle=q.c;c.beginPath();c.roundRect?c.roundRect(x,0,q.lab?16+q.lab.length*6.2:16,15,[0,4,4,0]):c.rect(x,0,16,15);c.fill();
    c.fillStyle='#06060b';c.font='800 10px -apple-system,sans-serif';c.fillText(q.k+(q.lab?' '+q.lab:''),x+4,11);}
  // playhead
  if(px>=-2&&px<=W+2){c.shadowColor='#fff';c.shadowBlur=12;c.strokeStyle='#fff';c.lineWidth=2;c.beginPath();c.moveTo(px,0);c.lineTo(px,H);c.stroke();c.shadowBlur=0;c.fillStyle='#fff';c.beginPath();c.moveTo(px-6,0);c.lineTo(px+6,0);c.lineTo(px,8);c.fill();}
}
function drawOV(){
  const cv=$('#ov'),{c,W,H}=fitCanvas(cv);c.clearRect(0,0,W,H);if(!D.buf)return;
  const mid=H/2,amp=H/2-3,spp=D.buf.length/W;c.fillStyle='rgba(124,92,255,.85)';
  for(let x=0;x<W;x++){const p=colPeak(spp,x*spp);if(!p)continue;c.fillRect(x,mid-p[1]*amp,1,Math.max(1,(p[1]-p[0])*amp));}
  const k=W/D.dur,[vs,ve]=D.view;c.fillStyle='rgba(255,255,255,.14)';c.fillRect(vs*k,0,Math.max(4,(ve-vs)*k),H);c.strokeStyle='rgba(255,255,255,.7)';c.strokeRect(vs*k+.5,.5,Math.max(4,(ve-vs)*k),H-1);
  const r=curRow(),mk=curMarks();const line=(t,col)=>{c.strokeStyle=col;c.lineWidth=2;c.beginPath();c.moveTo(t*k,0);c.lineTo(t*k,H);c.stroke();};
  if(r&&r.p.bars&&D.bpm)line(D.t0+r.p.bars*barLen(),'#fbbf24'); if(mk.start!=null)line(D.t0+mk.start*barLen(),'#fb923c'); if(mk.end!=null)line(D.t0+mk.end*barLen(),'#ef4444');
  if(D.cuePt!=null)line(D.cuePt,'#22d3ee');
  c.strokeStyle='#fff';c.lineWidth=2;c.beginPath();c.moveTo(curPos()*k,0);c.lineTo(curPos()*k,H);c.stroke();
}
function updateReadout(){
  const p=curPos();$('#dTime').textContent=fmt(p);const r=curRow();
  $('#dBar').textContent=D.bpm?('COMPÁS '+Math.floor((p-D.t0)/barLen()+1e-6)+(r&&r.p.bars&&(p-D.t0)/barLen()<r.p.bars?' · EXTENDER':'')):'COMPÁS —';
  $('#tPlay').textContent=D.playing?'❚❚':'▶';$('#tClk').classList.toggle('on',D.clicks);$('#tQ').classList.toggle('on',D.q);$('#gDrag').classList.toggle('on',D.gm);{const m0=curMarks();if(m0.loop&&$('#lLen').value!=String(m0.loop[1])){const o=[...$('#lLen').options].find(x=>+x.value===m0.loop[1]);if(!o){const n=document.createElement('option');n.value=m0.loop[1];n.textContent=m0.loop[1]+' comp.';$('#lLen').appendChild(n);}$('#lLen').value=String(m0.loop[1]);}}$('#tMk').classList.toggle('on',D.cuePt!=null);
}
function renderPads(){
  const cl=cuesList(),ml=memList();{const dq=$('#cDot');if(dq)dq.style.background=cColor();const md=$('#memDot');if(md)md.style.background=memColorOf(D.memSel||'G');}
  $('#pads').innerHTML=cl.map(q=>{const on=q.t!=null&&D.buf;return `<button class="pad ${on?'on':''}" data-k="${q.k}" style="--pc:${q.c};${on?`background:${q.c}`:''}">${q.k}<small>${on?(q.txt!=null?q.txt:''):'—'}</small></button>`;}).join('');
  $('#mpads').innerHTML=ml.map(q=>{const on=q.t!=null&&D.buf;return `<button class="pad ${on?'on':''} ${q.k===(D.memSel||'G')?'sel':''}" data-k="${q.k}" title="${esc(q.txt||'')} · doble clic: editar nombre y color" style="--pc:${q.c};${on?`background:${q.c}`:''}">${on?esc(q.txt||'MEM'):'·'}</button>`;}).join('');
}
let padSig='';
function drawDeck(){if(D.raf)return;D.raf=requestAnimationFrame(()=>{D.raf=0;drawWF();drawOV();updateReadout();const sig=JSON.stringify([curMarks(),D.t0,!!D.buf]);if(sig!==padSig){padSig=sig;renderPads();}});}
function setMsg(t,shim){const m=$('#wfMsg');m.style.display=t?'grid':'none';m.textContent=t||'';m.classList.toggle('shim',!!shim);}
function setView(vs,ve){const span=Math.min(Math.max(ve-vs,0.8),D.dur||10);vs=Math.max(0,Math.min(vs,(D.dur||span)-span));D.view=[vs,vs+span];drawDeck();}
function zoom(f,anchor){const [vs,ve]=D.view,span=ve-vs,ns=Math.min(D.dur,Math.max(0.8,span*f)),a=anchor==null?curPos():anchor,fr=Math.min(1,Math.max(0,(a-vs)/span));setView(a-fr*ns,a-fr*ns+ns);}
function seek(t){t=Math.max(0,Math.min(D.dur,t));if(D.playing)startPlay(t);else{D.pos=t;}const [vs,ve]=D.view;if(t<vs||t>ve)setView(t-(ve-vs)*.25,t+(ve-vs)*.75);drawDeck();}

