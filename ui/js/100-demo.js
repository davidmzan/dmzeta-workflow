'use strict';
/* ───────── modo demo (?demo=1): datos y audio sintéticos para ver la interfaz sin servidor ───────── */
function synthBuffer(bpm=100,secs=150,K=40){
  const ctx=AC(),sr=22050,buf=ctx.createBuffer(1,sr*secs,sr),d=buf.getChannelData(0),beat=60/bpm,bar=beat*4;let seed=7;const rnd=()=>{seed=(seed*16807)%2147483647;return seed/2147483647-.5;};
  for(let t=0.05;t<secs-.4;t+=beat){const loud=(t-.05)/bar>=K,intro=(t-.05)/bar<8,i=Math.floor(t*sr),g=loud?.95:intro?.35:.6;
    for(let j=0;j<.12*sr;j++){const tt=j/sr;d[i+j]+=Math.sin(2*Math.PI*(55+120*Math.exp(-tt*40))*tt)*Math.exp(-tt*25)*g;}
    if(!intro||loud){const h=Math.floor((t+beat/2)*sr);for(let j=0;j<.03*sr;j++)d[h+j]+=rnd()*Math.exp(-j/(.006*sr))*(loud?.5:.25);}
    if(loud)for(let j=0;j<beat*sr;j++)d[i+j]+=Math.sin(2*Math.PI*110*j/sr)*.22*Math.exp(-j/(beat*sr*.8));}
  return buf;
}
const DEMO_ROWS=[
 ['Besalo (8 Bars MOE) (Aca Out) - 10A - 148','El Alfa, Ozuna',.70,'Live Mashup: regla fija (MOE, Aca Out); ¿Aca Out? (comprobar)'],
 ['Jamaican x Charger (Mashup) (8 Bars POE) - 9A - 128','HUGEL, Triangle Des Bermudes',.47,'Título con "x": (Mashup) automático; barras dudosas (8)'],
 ['Quiero Más (8 Bars FME) (Aca Out) - 12A - 143','La Pantera',.47,'barras dudosas (8); ¿Aca Out? (comprobar); START MIX propuesto: compás 40 (confianza 0.62)'],
 ['Hookah (8 Bars FME) - 2A - 105','Quevedo, Ozuna',.64,'tipo dudoso (FME)'],
 ['Ibiza (4 Bars MOE) - 6B - 96','Ozuna, Romeo Santos',.68,''],
 ['Yonaguni (8 Bars MOE) (Aca Out) - 3A - 90','Bad Bunny',.42,'barras dudosas (8); ¿Aca Out? (comprobar)'],
 ['Pa Que Bailen (8 Bars FME) - 2A - 125','Anuel AA',.66,'DUPLICADO: ya tienes "Pa Que Bailen (8 Bars POE) - 2A - 125"'],
 ['Tarara Remix (8 Bars MOE) (Aca Out) - 12A - 82','Alexio, Farruko, Ozuna, Arcangel, Zion, Cosculluela',.50,'Live Mashup: regla fija (MOE, Aca Out); tipo dudoso (FME)'],
 ['Agua (8 Bars POE) - 5A - 133','Shakira, Maluma',.67,''],
 ['Otro Trago Remix (Aca Starter) - 7A - 94','Sech, Ozuna, Anuel Aa, Darell, Nicky Jam',.55,'barras dudosas (8)'],
 ['Unica (8 Bars FME) - 8A - 87','Ozuna',.61,''],
 ['Me Niego (8 Bars FME) - 5A - 94','Ozuna, Reik, Wisin',.69,''],
 ['Rapapa (8 Bars MOE) (Aca Out) - 10A - 135','JC Reyes',.52,'Live Mashup: regla fija (MOE, Aca Out); barras dudosas (8)'],
 ['Coqueta (8 Bars FME) - 12B - 90','Grupo Frontera, Fuerza Regida',.59,'tipo dudoso (FME)'],
 ['Umbrella x Hips Dont Lie (Mashup) (8 Bars POE) - 3A - 100','Rihanna, Jay-Z, Shakira, Wyclef Jean',.66,'Título con "x": (Mashup) automático'],
 ['Flipa (8 Bars MOE) (Aca Out) - 10A - 100','JC Reyes',.98,'Live Mashup: regla fija (MOE, Aca Out)'],
 ['Loquita (8 Bars MOE) (Aca Out) - 7A - 120','JC Reyes',.95,'Live Mashup: regla fija (MOE, Aca Out)'],
 ['Bebe (8 Bars MOE) (Aca Out) - 11A - 85','Ozuna, Anuel Aa',.81,'Live Mashup: regla fija (MOE, Aca Out)'],
].map(([f,a,c,fl],i)=>({original:f.replace(/ - \d+A? - /,' - ').replace(/\s*\(.*?\)/g,'')+' [orig '+(i+1)+'].mp3',proposed:f,final:f,artist:a,confidence:c,flags:fl,dup:fl.startsWith('DUPLICADO'),checked:!fl.startsWith('DUPLICADO'),reviewed:i===4||i===15,parsed:parseName(f+'.mp3'),marks:i===2?{start:40,end:48,auto:true,conf:.62,alts:[40,56,28],loop:[104,8]}:null}));
let demoJob=0;
async function demoApi(path,body){
  await new Promise(r=>setTimeout(r,40));
  if(path.startsWith('/api/bpmfix'))return{ok:true};
  if(path.startsWith('/api/quality'))return{bpm_fixes:{total:5,double_half:3,last:[]},usage:{tracks:40,median_secs:74,fields:{name:{n:40,corrected:6,rate:.15},grid:{n:40,corrected:3,rate:.075},start_mix:{n:38,corrected:24,rate:.63},genre:{n:35,corrected:10,rate:.29}}},latest:[{model:'names',when:'demo',n:48,n_user:12,accuracy:.85,baseline:null,enabled:true},{model:'cvox',when:'demo',n:27,n_user:9,accuracy:.78,baseline:.67,enabled:true},{model:'start_mix',when:'demo',n:1234,n_user:34,accuracy:.21,baseline:.17,enabled:false}],history:[]};
  if(path.startsWith('/api/state'))return{cfg:{train:['/Users/demo/Music/Library/Latin/2026/Brunch','/Users/demo/Music/Library/Latin/2025/Dembow'],xml:'/Users/demo/djflow/rekordbox.xml',folder:'/Users/demo/Music/New',backup:true},model:true,marks_model:true,undo:true,learned:48};
  if(path.startsWith('/api/review')&&body===undefined)return{rows:DEMO_ROWS};
  if(path.startsWith('/api/track')){const n=decodeURIComponent((path.match(/name=([^&]*)/)||[])[1]||'');const r=DEMO_ROWS.find(x=>x.original===n);return{t0:.05+(DEMO_ROWS.indexOf(r)%3)*.01,bpm:r?r.parsed.bpm:100,score:2};}
  if(path.startsWith('/api/job')){demoJob++;return demoJob<4?{status:'running',progress:demoJob/4,log:['[ '+demoJob+'/4 ] Mayonesa (4 Bars POE) - 6B - 102']}:(demoJob=0,{status:'done',progress:1,log:[],result:'Informe de ejemplo\n- compases: 78 %'});}
  if(path.startsWith('/api/pick'))return{path:'/Users/demo/Music/New'};
  if(path.startsWith('/api/analyze')||path.startsWith('/api/apply')||path.startsWith('/api/undo')||path.startsWith('/api/train'))return{job:'d'};
  return{ok:true,cfg:{}};
}
window.addEventListener('error',e=>showErr(e.message+' @'+e.lineno));window.addEventListener('unhandledrejection',e=>showErr(String(e.reason&&e.reason.stack||e.reason)));
function showErr(m){let b=document.getElementById('errbox');if(!b){b=document.createElement('pre');b.id='errbox';b.style.cssText='position:fixed;left:12px;right:12px;bottom:12px;z-index:99;background:#300;color:#fbb;padding:10px;border-radius:10px;font:11px ui-monospace,monospace;white-space:pre-wrap;max-height:30vh;overflow:auto';document.body.append(b);}b.textContent+=m+'\n';}
init().catch(e=>showErr(String(e&&e.stack||e)));
if(!DEMO){const ping=()=>fetch('/api/ping').catch(()=>{});ping();setInterval(ping,5000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)ping();});window.addEventListener('focus',ping);}
