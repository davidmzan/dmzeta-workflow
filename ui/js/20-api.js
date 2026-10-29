'use strict';
/* ───────── API (con modo demo) ───────── */
const TOKEN=(document.querySelector('meta[name=wf-token]')||{}).content||'';
async function api(path,body){
  if(DEMO) return demoApi(path,body);
  let r;
  try{r=await fetch(path,body!==undefined?{method:'POST',headers:{'Content-Type':'application/json','X-WF-Token':TOKEN},body:JSON.stringify(body)}:{headers:{'X-WF-Token':TOKEN}});}
  catch(e){throw new Error('No se puede contactar con el servidor local (¿se cerró?). Vuelve a abrir Dmzeta Workflow.');}
  return r.json();
}
async function runJob(title,id,onDone){
  const t=$('#toast'),T=$('#tT'),B=$('#tB'),L=$('#tL'); t.classList.remove('err'); t.classList.add('show'); T.textContent=title+'…'; B.classList.add('ind'); B.firstElementChild.style.width=''; L.textContent='';
  for(;;){
    const j=await api('/api/job?id='+id);
    if(j.log&&j.log.length)L.textContent=j.log[j.log.length-1];
    if(j.progress!=null){B.classList.remove('ind');B.firstElementChild.style.width=Math.round(j.progress*100)+'%';T.textContent=`${title}… ${Math.round(j.progress*100)}%`;}
    if(j.status==='done'){T.textContent=title+' ✓';B.classList.remove('ind');B.firstElementChild.style.width='100%';setTimeout(()=>t.classList.remove('show'),1800);return onDone&&onDone(j);}
    if(j.status==='error'||j.status==='missing'){t.classList.add('err');T.textContent='Error';L.textContent=j.error||'';B.classList.remove('ind');setTimeout(()=>t.classList.remove('show'),9000);return ask('Algo ha fallado',j.error||'Error desconocido','Cerrar',true);}
    await new Promise(r=>setTimeout(r,DEMO?150:600));
  }
}
function ask(title,msg,ok='Aceptar',single=false){
  return new Promise(res=>{
    $('#mT').textContent=title;$('#mB').textContent=msg;const f=$('#mF');f.innerHTML='';
    const done=v=>{$('#scrim').classList.remove('show');res(v);};
    if(!single){const c=document.createElement('button');c.className='btn';c.textContent='Cancelar';c.onclick=()=>done(false);f.append(c);}
    const o=document.createElement('button');o.className='btn pri';o.textContent=ok;o.onclick=()=>done(true);f.append(o);$('#scrim').classList.add('show');
  });
}

