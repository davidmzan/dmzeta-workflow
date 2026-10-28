'use strict';
/* ───────── nombre: mismo formato que tu biblioteca ───────── */
function parseName(n){
  let s=n.replace(/\.(mp3|m4a|flac|wav|aiff?)$/i,''),key=null,bpm=null,m=s.match(/\s*-\s*(\d{1,2}[AB])\s*-\s*(\d+)\s*$/);
  if(m){key=m[1];bpm=+m[2];s=s.slice(0,m.index);}
  const o={mashup:/\(Mashup\)/.test(s),open_show:/\(Open Show\)/.test(s),bars:null,type:null,aca_starter:/\(Aca Starter\)/.test(s),after:null,short_edit:/\(Short Edit\)/.test(s),aca_out:/\(Aca Out\)/.test(s),key,bpm};
  const mb=s.match(/\((\d+) Bars (POE|MOE|FME)\)/); if(mb){o.bars=+mb[1];o.type=mb[2];}
  const ma=s.match(/\((In Aca|In Hype)\)/); if(ma)o.after=ma[1];
  o.base=s.replace(/\s*\((?:Mashup|Open Show|\d+ Bars (?:POE|MOE|FME)|Aca Starter|In Aca|In Hype|Short Edit|Aca Out)\)/g,'').trim();
  return o;
}
function buildName(p){
  let s=p.base||''; if(p.mashup)s+=' (Mashup)'; if(p.open_show)s+=' (Open Show)'; if(p.aca_starter)s+=' (Aca Starter)'; else if(p.bars&&p.type)s+=` (${p.bars} Bars ${p.type})`;
  if(p.after)s+=` (${p.after})`; if(p.short_edit)s+=' (Short Edit)'; if(p.aca_out)s+=' (Aca Out)'; return `${s} - ${p.key} - ${Math.round(p.bpm)}`;
}
const finalOf=r=>(r.p.key&&r.p.bpm&&r.p.base)?buildName(r.p):'';
function previewHTML(r){
  const p=r.p; let h=`<span>${esc(p.base)}</span>`;
  if(p.mashup)h+=` <span class="p-m">(Mashup)</span>`; if(p.open_show)h+=` <span class="p-a">(Open Show)</span>`; if(p.aca_starter)h+=` <span class="p-b">(Aca Starter)</span>`; else if(p.bars&&p.type)h+=` <span class="p-b">(${p.bars} Bars ${p.type})</span>`;
  if(p.after)h+=` <span class="p-a">(${p.after})</span>`; if(p.short_edit)h+=` <span class="p-a">(Short Edit)</span>`; if(p.aca_out)h+=` <span class="p-m">(Aca Out)</span>`;
  return h+` <span class="p-k">- ${esc(p.key||'?')}</span> <span class="p-n">- ${p.bpm?Math.round(p.bpm):'?'}</span>`;
}
function keyBadge(k){const m=/^(\d+)([AB])$/.exec(k||'');if(!m)return{bg:'#3a3a48',t:'—'};const h=(parseInt(m[1])*30+150)%360,a=m[2]==='A';return{bg:`linear-gradient(135deg,hsl(${h} 90% ${a?58:72}%),hsl(${(h+30)%360} 90% ${a?46:60}%))`,t:k};}

