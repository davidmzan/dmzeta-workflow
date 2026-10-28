'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const enc=encodeURIComponent, DEMO=location.search.includes('demo');
const S={folder:'',rows:[],sel:-1,filter:'all',q:'',cfg:{train:[],xml:'',folder:'',backup:true,auto_learn:true,auto_n:10},st:{},step:1,marks:{},done:{apply:false,cues:false},saveT:null};
const D={loopLen:8,q:true,gm:false,cuePt:null,buf:null,peaks:null,sr:44100,dur:0,t0:0,t0det:0,bpm:0,view:[0,10],pos:0,playing:false,ctx:null,src:null,startedAt:0,clicks:true,loading:false,cache:new Map(),name:null,raf:0,nextBar:0,timer:null,drag:null,gen:0};

