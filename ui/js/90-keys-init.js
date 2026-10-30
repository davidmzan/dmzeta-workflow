'use strict';
/* ───────── teclado + init ───────── */
function trackSecs(){const now=Date.now();if(S.selAt!=null&&S.sel>=0&&S.rows[S.sel]&&S.folder){const o=S.rows[S.sel].original,m=S.marks[o]||(S.marks[o]={});m.secs=+((m.secs||0)+Math.min(120,(now-S.selAt)/1000)).toFixed(1);}S.selAt=now;}   // segundos que dedicas a cada pista (máx. 120 por visita)
function selectRow(i,load=true){if(i<0||i>=S.rows.length||i===S.sel&&load===false)return;trackSecs();S.sel=i;$$('.card').forEach(c=>c.classList.toggle('sel',+c.dataset.i===i));renderInsp();if(load)loadTrack(i);const el=$(`.card[data-i="${i}"]`);if(el)el.scrollIntoView({block:'nearest',behavior:'smooth'});}
function stepSel(d){const v=visible().map(x=>x[1]);if(!v.length)return;const k=v.indexOf(S.sel);selectRow(v[Math.max(0,Math.min(v.length-1,k<0?0:k+d))]);}
window.addEventListener('keydown',e=>{
  if(['INPUT','TEXTAREA'].includes(e.target.tagName)){if(e.key==='Escape')e.target.blur();return;}
  if(e.metaKey||e.ctrlKey||e.altKey)return;const k=e.key;
  if(k===' '){e.preventDefault();togglePlay();}else if(k==='ArrowDown'){e.preventDefault();stepSel(1);}else if(k==='ArrowUp'){e.preventDefault();stepSel(-1);}
  else if(k==='ArrowRight'||k==='ArrowLeft'){e.preventDefault();const sg=k==='ArrowRight'?1:-1;seek(D.q?snap(curPos()+sg*(e.shiftKey?4:1)*barLen()):curPos()+sg*(e.shiftKey?1:.1));}else if(k==='q'||k==='Q'){$('#tQ').click();}else if(k==='k'||k==='K'){setCuePt();}else if(k==='n'||k==='N'){addMem();}else if(/^Digit[1-8]$/.test(e.code)){padAct(String.fromCharCode(64+ +e.code.slice(5)),e.shiftKey);}else if(k==='j'||k==='J'){goCuePt();}else if(k==='g'||k==='G'){gridHere();}
  else if(k==='1'||k==='2'||k==='3')pickStart(+k-1);else if(k==='s'||k==='S')markHere('start');else if(k==='e'||k==='E')markHere('end');else if(k==='l'||k==='L')markHere('loop');else if(k==='x'||k==='X')markHere('clear');
  else if(k==='['){nudge('beat',-1);}else if(k===']'){nudge('beat',1);}else if(k===','){nudge('ms',-stepMs());}else if(k==='.'){nudge('ms',stepMs());}
  else if(k==='m'||k==='M'){$('#tClk').click();}else if(k==='+'||k==='='){zoom(.6);}else if(k==='-'){zoom(1.7);}
  else if(k==='Enter'&&S.sel>=0){acceptNext();}else if((k==='c'||k==='C')&&S.sel>=0){setChecked(S.sel,!S.rows[S.sel].checked);}
});
async function init(){
  S.st=await api('/api/state');S.cfg=Object.assign(S.cfg,S.st.cfg||{});try{S.rules=await api('/api/rules');}catch(e){}
  if(S.st.loop_len){D.loopLen=S.st.loop_len;const ll=$('#lLen');if(ll)ll.value=String(D.loopLen);}
  $('#list').onclick=e=>{const ch=e.target.closest('[data-chk]');if(ch){e.stopPropagation();setChecked(+ch.dataset.chk,!S.rows[+ch.dataset.chk].checked);return;}const c=e.target.closest('.card');if(c)selectRow(+c.dataset.i);};
  $('#bulk').onclick=e=>{const b=e.target.closest('[data-bulk]');if(b)bulk(b.dataset.bulk);};
  $('#filters').onclick=e=>{const b=e.target.closest('[data-f]');if(b){S.filter=b.dataset.f;renderFilters();renderList();}};
  $('#bCta').onclick=onCta;$('#bUndo').onclick=doUndo;$('#bSet').onclick=()=>{renderDrawer();$('#drawer').classList.add('show');};
  $('#scrim').onclick=e=>{if(e.target.id==='scrim'&&$('#mF').children.length===1)$('#scrim').classList.remove('show');};
  bindDeck();render();updateTop(null);drawDeck();
  if(DEMO){await loadReview(S.cfg.folder);}
}

