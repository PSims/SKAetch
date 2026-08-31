const STAGE_ORDER=['AA0.5','AA1','AA2','AA*','AA4'];
const DEMO_STORIES={
 interferometry:{
  label:'Build + Earth rotation',
  visitorStages:['AA1','AA4'],
  states:[
   {stage:'AA1',duration:'snapshot'},
   {stage:'AA4',duration:'snapshot'},
   {stage:'AA4',duration:'6h'}
  ]
 },
 build:{
  label:'Build the SKA',
  visitorStages:['AA1','AA2','AA*','AA4'],
  states:[
   {stage:'AA1',duration:'snapshot'},
   {stage:'AA1',duration:'6h'},
   {stage:'AA2',duration:'6h'},
   {stage:'AA*',duration:'6h'},
   {stage:'AA4',duration:'6h'}
  ]
 }
};
const state={stage:'AA1',duration:'snapshot',demoStory:'build',imageRevealMode:'after',imageMode:'outreach',uvDisplayMode:'animated',capture:null,capturedCameraImage:null,mode:null,sourceLabel:'No source',metadata:null,stream:null,screen:'capture',scienceTab:'layout',requestToken:0,aborter:null,trackCache:{},trackAnimationId:0,pendingUvAnimationPromise:Promise.resolve(),delayNextImageReveal:false};

const story={
 'AA0.5':{
  title:'Start with just four stations',
  snapshot:'Can four stations recover your portrait?',
  six:'The same four stations observe from more directions — but there are still only six station pairs.',
  questionSnapshot:'What information is missing?',questionSix:'Did rotation help — and what can it not create?',
  lesson:'With only four stations, the telescope measures very few spatial patterns.'
 },
 'AA1':{
  title:'Start with 16 stations',
  snapshot:'Sixteen stations make 120 pairs. Can this small array recover the picture?',
  six:'Earth rotation gives those pairs more directions to measure, but the visitor path normally builds the full array first.',
  questionSnapshot:'What information is missing?',questionSix:'Which structures have become easier to recognise?',
  lesson:'Each pair of stations measures a different spatial pattern in the imaginary radio sky.'
 },
 'AA2':{
  title:'Now make the baselines much longer',
  snapshot:'AA2 reaches tens of kilometres — but more resolution does not automatically mean a better picture.',
  six:'Rotation fills directions, while the unusual mix of baseline lengths still leaves a distinctive reconstruction.',
  questionSnapshot:'Why can a bigger array still make a strange image?',questionSix:'What does Earth rotation fix — and what does station placement still control?',
  lesson:'Long spacings measure fine detail; short spacings are needed for broad structure.'
 },
 'AA*':{
  title:'Add a much richer range of spacings',
  snapshot:'Now short and long baselines work together, so much more of the portrait is recoverable.',
  six:'Earth rotation fills the Fourier plane further and the portrait becomes much cleaner.',
  questionSnapshot:'Which details suddenly become recognisable?',questionSix:'What changed: station number, station placement, or both?',
  lesson:'A good interferometer needs many different baseline lengths and directions.'
 },
 'AA4':{
  title:'Build the full 512-station array',
  snapshot:'The full design samples a much richer set of spatial scales in one instant.',
  six:'Now let Earth rotate: each baseline sweeps through new Fourier directions and the reconstruction becomes cleaner.',
  questionSnapshot:'How much did building the full SKA improve the picture?',questionSix:'What changed when Earth rotation filled in more of the Fourier plane?',
  lesson:'Many baselines + many spacings + Earth rotation give a much more complete picture.'
 }
};

const buildStory={
 'AA1':{title:'Start with the early 16-station array',snapshot:'First take an instant snapshot with 16 stations and only 120 independent station pairs.',six:'Now let Earth rotate. The same 120 pairs sweep through more Fourier directions — but rotation cannot create the missing variety of baseline lengths.',questionSnapshot:'Can you recognise the source from one instant?',questionSix:'Did Earth rotation add information — and why is the image still poor?',lesson:'Earth rotation adds sampling directions, but it cannot replace the missing baselines of a small array.'},
 'AA2':{title:'Build the next major array: 68 stations',six:'AA2 adds many more stations and much longer baselines. A recognisable image is beginning to emerge.',questionSix:'What can you recognise now that was missing at AA1?',lesson:'Adding stations creates many more baseline pairs, but their lengths and directions still matter.'},
 'AA*':{title:'Grow to the 307-station deployment array',six:'A much richer mix of short and long spacings now recovers a clear picture.',questionSix:'Which details become clear at AA*?',lesson:'Dense short-baseline coverage plus many longer spacings recovers both broad structure and fine detail.'},
 'AA4':{title:'Reach the full 512-station SKA-Low design',six:'The full design gives an exceptionally rich six-hour Fourier sampling pattern and a polished reconstruction.',questionSix:'How much more complete is the final picture?',lesson:'The full array combines 130,816 independent station pairs with Earth rotation to sample the Fourier plane densely.'}
};

const currentStoryConfig=()=>DEMO_STORIES[state.demoStory]||DEMO_STORIES.interferometry;
const visitorStates=()=>currentStoryConfig().states;
const visitorStageOrder=()=>currentStoryConfig().visitorStages;
function recommendedVisitorStateForStage(stage){return visitorStates().find(x=>x.stage===stage)||null;}
function durationRank(duration){return duration==='snapshot'?0:1;}
function nextPrescribedState(){
 const states=visitorStates(),exact=visitorStateIndex();
 if(exact>=0)return exact<states.length-1?states[exact+1]:null;
 const j=states.findIndex(x=>x.stage===state.stage);
 if(j<0)return null;
 const rec=states[j];
 if(durationRank(state.duration)<durationRank(rec.duration))return rec;
 return j<states.length-1?states[j+1]:null;
}
function previousPrescribedState(){
 const states=visitorStates(),exact=visitorStateIndex();
 if(exact>=0)return exact>0?states[exact-1]:null;
 const j=states.findIndex(x=>x.stage===state.stage);
 if(j<0)return null;
 const rec=states[j];
 if(durationRank(state.duration)>durationRank(rec.duration))return rec;
 return j>0?states[j-1]:null;
}
const slug=s=>s.replace('.','p').replace('*','star');
const $=id=>document.getElementById(id);

async function init(){
 state.metadata=await (await fetch('/api/metadata',{cache:'no-store'})).json();
 buildStageTrack(); buildFacilitator(); bindEvents(); updateSourceButtons(); updateUI(false); setScienceTab('layout');
 loadUvTrack('AA1').catch(err=>console.warn('Could not pre-load uv tracks',err));
 $('operatorStatus').textContent=`${Object.keys(state.metadata.operators||{}).length||5} stage presets loaded · corrected exact SKAO v4.5.0 geometry`;
}

function bindEvents(){
 $('startCamera').onclick=startCamera; $('startCameraMobile').onclick=startCamera;
 $('captureButton').onclick=capture; $('captureButtonMobile').onclick=capture;
 $('useEinsteinButton').onclick=useEinsteinDemo; $('useEinsteinButtonMobile').onclick=useEinsteinDemo;
 $('buildPreviousButton').onclick=navigatePrevious; $('buildForwardButton').onclick=navigateForward; $('buildNextButton').onclick=buildNextStage; $('rotateButton').onclick=toggleRotation;
 $('newImageButton').onclick=resetForNewImage; $('facilitatorReset').onclick=resetForNewImage; $('facilitatorCapture').onclick=showCaptureScreen;
 $('facilitatorButton').onclick=()=>toggleFacilitator(true); $('closeFacilitator').onclick=()=>toggleFacilitator(false);
 $('fullscreenButton').onclick=toggleFullscreen; $('scienceToggle').onclick=toggleSciencePanel;
 document.querySelectorAll('[data-image-mode]').forEach(b=>b.onclick=()=>setImageMode(b.dataset.imageMode));
 document.querySelectorAll('[data-uv-view]').forEach(b=>b.onclick=()=>setUvDisplayMode(b.dataset.uvView,true));
 $('uvReplayButton').onclick=()=>replayUvAnimation();
 document.querySelectorAll('[data-science-tab]').forEach(b=>b.onclick=()=>setScienceTab(b.dataset.scienceTab));
 document.addEventListener('keydown',e=>{
  if(e.key.toLowerCase()==='f' && !/input|textarea/i.test(document.activeElement.tagName)){e.preventDefault();toggleFacilitator();}
  if(e.key==='Escape')toggleFacilitator(false);
  if(state.screen==='explore' && e.key==='ArrowRight')navigateForward();
  if(state.screen==='explore' && e.key==='ArrowLeft')navigatePrevious();
  if(state.screen==='explore' && e.key.toLowerCase()==='r')toggleRotation();
 });
}

function buildStageTrack(){
 const track=$('stageTrack'); track.innerHTML='';
 visitorStageOrder().forEach(stage=>{const d=document.createElement('button');d.type='button';d.className='stage-node';d.dataset.trackStage=stage;const stations=state.metadata?.stages?.[stage]?.stations;d.innerHTML=`<span class="stage-code">${stage}</span>${stations?`<small class="stage-count">${stations.toLocaleString()} stations</small>`:''}`;const rec=recommendedVisitorStateForStage(stage);const duration=rec?.duration==='6h'?'6 h':'snapshot';d.title=`Jump to ${stage} ${duration}`;d.onclick=()=>jumpVisitorStage(stage);track.appendChild(d);});
}


function buildFacilitator(){
 const stories=$('facilitatorStories');
 [['interferometry','Build + Earth rotation'],['build','Build the SKA']].forEach(([mode,label])=>{const b=document.createElement('button');b.className='button';b.textContent=label;b.dataset.demoStory=mode;b.onclick=()=>setDemoStory(mode);stories.appendChild(b);});
 const reveals=$('facilitatorImageReveal');
 [['after','After observation'],['immediate','Immediate']].forEach(([mode,label])=>{const b=document.createElement('button');b.className='button';b.textContent=label;b.dataset.imageReveal=mode;b.onclick=()=>setImageRevealMode(mode);reveals.appendChild(b);});
 const s=$('facilitatorStages');
 STAGE_ORDER.forEach(stage=>{const b=document.createElement('button');b.className='button';b.textContent=stage;b.dataset.facStage=stage;b.onclick=()=>jumpStage(stage);s.appendChild(b);});
 const d=$('facilitatorDurations');
 [['snapshot','Snapshot'],['6h','6 h rotation']].forEach(([duration,label])=>{const b=document.createElement('button');b.className='button';b.textContent=label;b.dataset.facDuration=duration;b.onclick=()=>jumpDuration(duration);d.appendChild(b);});
 const uvDisplays=$('facilitatorUvDisplays');
 [['animated','Animated tracks'],['static','Sampling plot']].forEach(([mode,label])=>{const b=document.createElement('button');b.className='button';b.textContent=label;b.dataset.uvView=mode;b.onclick=()=>setUvDisplayMode(mode,true);uvDisplays.appendChild(b);});
 const imageModes=$('facilitatorImageModes');
 [['outreach','Outreach view'],['science','Science image']].forEach(([mode,label])=>{const b=document.createElement('button');b.className='button';b.textContent=label;b.dataset.imageMode=mode;b.onclick=()=>setImageMode(mode);imageModes.appendChild(b);});
 const sources=$('facilitatorSources');
 const entries=[
  ['camera_capture','Camera image'],
  ['demo_einstein','Einstein'],
  ['demo_fornax','Fornax A'],
  ['demo_crab','Crab Nebula'],
  ['demo_cat','Cat']
 ];
 entries.forEach(([mode,label])=>{const b=document.createElement('button');b.className='button source-button';b.textContent=label;b.dataset.sourceMode=mode;b.onclick=()=>selectSource(mode,label);sources.appendChild(b);});
}

function sourceAvailable(mode){
 if(mode==='camera_capture')return Boolean(state.capturedCameraImage);
 if(mode==='demo_cat')return Boolean(state.metadata?.demo_sources?.[mode]?.installed);
 return Boolean(state.metadata?.demo_sources?.[mode]?.installed);
}

function activeSourceRecord(){return state.metadata?.demo_sources?.[state.mode]||null;}

function supportedImageModes(){return activeSourceRecord()?.available_image_modes||activeSourceRecord()?.supported_image_modes||['outreach','science'];}
function imageModeLabel(mode){if(mode==='science')return activeSourceRecord()?.science_mode_label||'Science image';return 'Outreach view';}

function updateImageModeAvailability(){
 const supported=supportedImageModes();
 document.querySelectorAll('[data-image-mode]').forEach(b=>{
  const ok=supported.includes(b.dataset.imageMode);b.disabled=!ok;
  b.textContent=imageModeLabel(b.dataset.imageMode);
  b.title=ok?'':`${state.sourceLabel||'This source'} uses Outreach view only at its adopted angular scale.`;
 });
 const help=$('imageModeHelp');
 if(help)help.textContent=state.mode==='demo_fornax'?'Outreach view shows the dirty interferometric image. Cleaned image uses a locally generated 1.5° natural-weighted constrained reconstruction when the optional Fornax cache is installed.':'Outreach view shows the dirty interferometric image. Science image uses a finer Fourier grid and an idealised constrained iterative reconstruction.';
}

function updateSourceButtons(){
 document.querySelectorAll('[data-source-mode]').forEach(b=>{b.disabled=!sourceAvailable(b.dataset.sourceMode);b.classList.toggle('active',(b.dataset.sourceMode==='camera_capture'&&state.mode==='capture')||b.dataset.sourceMode===state.mode);});
 const einsteinReady=sourceAvailable('demo_einstein');$('useEinsteinButton').disabled=!einsteinReady;$('useEinsteinButtonMobile').disabled=!einsteinReady;
 const missingOptional=['demo_fornax','demo_crab'].filter(m=>!sourceAvailable(m));
 const note=$('sourceInstallNote');if(note)note.textContent=missingOptional.length?'Fornax A and Crab are optional local assets and may be unavailable in a public installation.':'Optional Fornax A and Crab assets are enabled locally.';
 const active=activeSourceRecord();const credit=$('sourceCredit');if(credit)credit.textContent=active?`Source credit: ${active.credit}`:'';
 updateImageModeAvailability();
}


function updateAngularScaleNote(){
 const note=$('angularScaleNote');if(!note)return;
 const active=activeSourceRecord();
 const fieldKey=`field_deg_${state.imageMode}`;
 const field=Number(active?.[fieldKey]??(state.imageMode==='science'?0.7:1.5));
 const fieldMoon=`about ${(field/0.5).toFixed(1)} Moon diameters`;
 const key=`source_size_arcmin_${state.imageMode}`;
 const fallbackArcmin=Number(state.metadata?.default_test_pattern_size_arcmin??12);
 const arcmin=Number(active?.[key]??fallbackArcmin);
 const scaleNoun=active?.kind==='radio astronomy source'?'source':'test pattern';
 let sizeText;
 if(arcmin>=60){const deg=arcmin/60;sizeText=`${arcmin.toFixed(0)}′ (${deg.toFixed(1)}°) across, about ${(arcmin/30).toFixed(1)} Moon diameters`;}
 else sizeText=`${arcmin.toFixed(0)}′ across, about ${(arcmin/30).toFixed(1)} of the Moon’s apparent diameter`;
 const qualifier=active?.angular_scale_note?` ${active.angular_scale_note}`:'';
 note.innerHTML=`<strong>Current simulation:</strong> ${scaleNoun} ${sizeText}; field ${field.toFixed(1)}° across (${fieldMoon}).${qualifier}`;
}


async function setImageMode(mode){
 if(!['outreach','science'].includes(mode))return;
 if(!supportedImageModes().includes(mode)){toast(`${state.sourceLabel||'This source'} uses Outreach view only at its adopted angular scale.`);return;}
 state.imageMode=mode;
 document.querySelectorAll('[data-image-mode]').forEach(b=>b.classList.toggle('active',b.dataset.imageMode===mode));
 updateUI(false);
 if(state.mode)await processCurrent();
}


function cancelUvAnimation(){state.trackAnimationId++;}
function sleep(ms){return new Promise(resolve=>setTimeout(resolve,ms));}

function decodeInt16Base64(encoded){
 const raw=atob(encoded);const bytes=new Uint8Array(raw.length);
 for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
 return new Int16Array(bytes.buffer);
}

async function loadUvTrack(stage){
 if(state.trackCache[stage])return state.trackCache[stage];
 const response=await fetch(`/assets/uv_tracks_${slug(stage)}.json`,{cache:'no-store'});
 if(!response.ok)throw new Error(`Could not load uv tracks for ${stage}`);
 const rec=await response.json();rec.coords=decodeInt16Base64(rec.uv_int16_base64);delete rec.uv_int16_base64;
 state.trackCache[stage]=rec;return rec;
}

function uvCanvasGeometry(){
 const canvas=$('uvTrackCanvas');const size=390,left=(canvas.width-size)/2,top=48;
 return {canvas,size,left,top,right:left+size,bottom:top+size,cx:left+size/2,cy:top+size/2};
}

function formatKlambda(value){const a=Math.abs(value);return a<10?value.toFixed(1):value.toFixed(0);}

function drawUvAxes(ctx,rec,title){
 const {canvas,size,left,top,right,bottom,cx,cy}=uvCanvasGeometry();
 ctx.clearRect(0,0,canvas.width,canvas.height);ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);
 ctx.strokeStyle='#d4dde2';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(cx,top);ctx.lineTo(cx,bottom);ctx.moveTo(left,cy);ctx.lineTo(right,cy);ctx.stroke();
 ctx.strokeStyle='#263b47';ctx.lineWidth=1.2;ctx.strokeRect(left,top,size,size);
 ctx.fillStyle='#142b37';ctx.font='700 17px system-ui, sans-serif';ctx.textAlign='center';ctx.fillText(`${rec.stage}: ${title}`,canvas.width/2,26);
 ctx.font='14px system-ui, sans-serif';ctx.fillStyle='#334c59';
 const lim=rec.axis_limit_klambda;const ticks=[-lim,-lim/2,0,lim/2,lim];
 for(const tick of ticks){
  const f=(tick+lim)/(2*lim);const x=left+f*size;const y=bottom-f*size;
  ctx.strokeStyle='#263b47';ctx.beginPath();ctx.moveTo(x,bottom);ctx.lineTo(x,bottom+5);ctx.moveTo(left-5,y);ctx.lineTo(left,y);ctx.stroke();
  ctx.textAlign='center';ctx.fillText(formatKlambda(tick),x,bottom+20);
  ctx.textAlign='right';ctx.fillText(formatKlambda(tick),left-9,y+4);
 }
 ctx.font='15px system-ui, sans-serif';ctx.textAlign='center';ctx.fillText('u (kλ)',canvas.width/2,canvas.height-14);
 ctx.save();ctx.translate(25,top+size/2);ctx.rotate(-Math.PI/2);ctx.fillText('v (kλ)',0,0);ctx.restore();
}

function uvPoint(rec,b,t){
 const nT=rec.array_shape[1],scale=rec.coordinate_scale_int16,{size,left,top}=uvCanvasGeometry();
 const base=(b*nT+t)*2;const qU=rec.coords[base],qV=rec.coords[base+1];
 return [left+size*(0.5+qU/(2*scale)),top+size*(0.5-qV/(2*scale))];
}

const UV_PRIMARY='#0b648f';
const UV_CONJUGATE='#e88426';
function drawUvSnapshot(rec){
 const ctx=$('uvTrackCanvas').getContext('2d');drawUvAxes(ctx,rec,'snapshot at transit');
 const {left,top,size,cx,cy}=uvCanvasGeometry();ctx.save();ctx.beginPath();ctx.rect(left,top,size,size);ctx.clip();
 const n=rec.display_baseline_pairs;const alpha=n<200?.86:n<3000?.52:.34;const r=n<20?4.2:n<200?2.8:n<3000?1.25:.85;
 for(let b=0;b<n;b++){const [x,y]=uvPoint(rec,b,rec.centre_index);ctx.fillStyle=`rgba(11,100,143,${alpha})`;ctx.fillRect(x-r,y-r,2*r,2*r);ctx.fillStyle=`rgba(232,132,38,${alpha})`;ctx.fillRect(2*cx-x-r,2*cy-y-r,2*r,2*r);}
 ctx.restore();
 $('uvTrackBadge').textContent=rec.display_subset?`Snapshot · ${rec.display_baseline_pairs.toLocaleString()} representative baseline samples + conjugates · imaging uses all ${rec.total_baseline_pairs.toLocaleString()} baselines`:`Snapshot · ${rec.total_baseline_pairs.toLocaleString()} independent baseline samples + conjugates`;
}

function drawUvSegment(rec,t0,t1){
 const ctx=$('uvTrackCanvas').getContext('2d'),n=rec.display_baseline_pairs,{left,top,size,cx,cy}=uvCanvasGeometry();
 const alpha=n<200?.80:n<3000?.23:n<20000?.095:.065;const width=n<200?1.45:n<3000?.95:n<20000?.72:.62;
 ctx.save();ctx.beginPath();ctx.rect(left,top,size,size);ctx.clip();
 ctx.beginPath();
 for(let b=0;b<n;b++){const [x0,y0]=uvPoint(rec,b,t0),[x1,y1]=uvPoint(rec,b,t1);ctx.moveTo(x0,y0);ctx.lineTo(x1,y1);}
 ctx.strokeStyle=`rgba(11,100,143,${alpha})`;ctx.lineWidth=width;ctx.stroke();
 ctx.beginPath();
 for(let b=0;b<n;b++){const [x0,y0]=uvPoint(rec,b,t0),[x1,y1]=uvPoint(rec,b,t1);ctx.moveTo(2*cx-x0,2*cy-y0);ctx.lineTo(2*cx-x1,2*cy-y1);}
 ctx.strokeStyle=`rgba(232,132,38,${alpha})`;ctx.lineWidth=width;ctx.stroke();ctx.restore();
}

function drawCurrentUvPoints(rec,t){
 const canvas=$('uvPointCanvas'),ctx=canvas.getContext('2d'),n=rec.display_baseline_pairs,{left,top,size,cx,cy}=uvCanvasGeometry();
 ctx.clearRect(0,0,canvas.width,canvas.height);ctx.save();ctx.beginPath();ctx.rect(left,top,size,size);ctx.clip();
 // The white halo marks the instantaneous position.  At dense stages the
 // accumulated tracks carry the coverage story, so cap endpoint markers to
 // keep animation responsive without reducing the number of displayed tracks.
 const endpointStep=Math.max(1,Math.ceil(n/9000));
 const r=n<20?4.8:n<200?3.1:n<3000?1.5:.9;const outline=Math.max(.8,r*.48);
 for(let b=0;b<n;b+=endpointStep){const [x,y]=uvPoint(rec,b,t);for(const [px,py,color] of [[x,y,UV_PRIMARY],[2*cx-x,2*cy-y,UV_CONJUGATE]]){ctx.beginPath();ctx.arc(px,py,r+outline,0,Math.PI*2);ctx.fillStyle='rgba(255,255,255,.90)';ctx.fill();ctx.beginPath();ctx.arc(px,py,r,0,Math.PI*2);ctx.fillStyle=color;ctx.fill();}}
 ctx.restore();
}

function clearCurrentUvPoints(){const c=$('uvPointCanvas');if(c)c.getContext('2d').clearRect(0,0,c.width,c.height);}

function drawUvAnimationStart(rec){
 const ctx=$('uvTrackCanvas').getContext('2d');drawUvAxes(ctx,rec,'6 h Earth-rotation synthesis');drawCurrentUvPoints(rec,0);
 $('uvTrackBadge').textContent=`Start of observation · H = ${rec.hour_angles_h[0].toFixed(1)} h`;
}

function drawCompleteUvTracks(rec){
 cancelUvAnimation();const ctx=$('uvTrackCanvas').getContext('2d');drawUvAxes(ctx,rec,'6 h Earth-rotation synthesis');
 for(let t=1;t<rec.array_shape[1];t++)drawUvSegment(rec,t-1,t);drawCurrentUvPoints(rec,rec.array_shape[1]-1);
 $('uvTrackBadge').textContent=rec.display_subset?`6 h complete · ${rec.display_baseline_pairs.toLocaleString()} representative baseline tracks + conjugates · imaging uses all ${rec.total_baseline_pairs.toLocaleString()} baselines`:`6 h complete · ${rec.total_baseline_pairs.toLocaleString()} independent baseline tracks + conjugates`;
}

async function animateUvTracks(rec){
 const animationId=++state.trackAnimationId;drawUvAnimationStart(rec);
 for(let t=1;t<rec.array_shape[1];t++){
  await sleep(70);if(animationId!==state.trackAnimationId||state.uvDisplayMode!=='animated'||state.stage!==rec.stage||state.duration!=='6h')return;
  drawUvSegment(rec,t-1,t);drawCurrentUvPoints(rec,t);
  const h=rec.hour_angles_h[t];$('uvTrackBadge').textContent=`Earth rotating · H = ${h.toFixed(1)} h · sampled tracks accumulating…`;
 }
 if(animationId===state.trackAnimationId)$('uvTrackBadge').textContent=rec.display_subset?`6 h complete · ${rec.display_baseline_pairs.toLocaleString()} representative baseline tracks + conjugates · imaging uses all ${rec.total_baseline_pairs.toLocaleString()} baselines`:`6 h complete · ${rec.total_baseline_pairs.toLocaleString()} independent baseline tracks + conjugates`;
}

async function refreshUvDisplay({animate=false}={}){
 const stack=$('uvStack');const animated=state.uvDisplayMode==='animated';stack.classList.toggle('track-mode',animated);
 document.querySelectorAll('[data-uv-view]').forEach(b=>b.classList.toggle('active',b.dataset.uvView===state.uvDisplayMode));
 $('uvReplayButton').disabled=!animated||state.duration!=='6h';
 if(!animated){cancelUvAnimation();clearCurrentUvPoints();return;}
 const stage=state.stage,duration=state.duration;const rec=await loadUvTrack(stage);
 if(state.stage!==stage||state.uvDisplayMode!=='animated')return;
 if(duration==='snapshot'){clearCurrentUvPoints();drawUvSnapshot(rec);}else if(animate)await animateUvTracks(rec);else drawCompleteUvTracks(rec);
}

async function setUvDisplayMode(mode,replay=false){
 if(!['animated','static'].includes(mode))return;state.uvDisplayMode=mode;
 await refreshUvDisplay({animate:replay&&mode==='animated'&&state.duration==='6h'&&state.scienceTab==='uv'});
}

async function replayUvAnimation(){
 if(state.uvDisplayMode!=='animated'||state.duration!=='6h')return;
 const rec=await loadUvTrack(state.stage);await animateUvTracks(rec);
}

async function selectSource(mode,label){
 if(!sourceAvailable(mode)){toast(mode==='camera_capture'?'Take a camera photo first.':'This optional demo source is not installed yet.');return;}
 if(mode==='camera_capture'){state.capture=state.capturedCameraImage;state.mode='capture';state.sourceLabel='Camera image';}
 else{state.mode=mode;state.sourceLabel=state.metadata?.demo_sources?.[mode]?.label||label;}
 if(!supportedImageModes().includes(state.imageMode))state.imageMode='outreach';
 updateSourceButtons();toggleFacilitator(false);
 if(state.screen!=='explore'){startStory();return;}
 updateUI(false);await processCurrent();
}

async function startCamera(){
 try{
  state.stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user',width:{ideal:1280},height:{ideal:720}},audio:false});
  const v=$('video'); v.srcObject=state.stream; $('cameraFallback').hidden=true;
  $('captureButton').disabled=false; $('captureButtonMobile').disabled=false;
  toast('Camera ready — keep the subject inside the square.');
 }catch(err){$('cameraFallback').innerHTML='<strong>Camera unavailable</strong><span>Use Einstein instead, or choose another demo in Facilitator mode.</span>';console.error(err);}
}

function capture(){
 const v=$('video'); if(!v.videoWidth){toast('Start the camera first.');return;}
 const c=$('captureCanvas'),ctx=c.getContext('2d'); const side=Math.min(v.videoWidth,v.videoHeight),sx=(v.videoWidth-side)/2,sy=(v.videoHeight-side)/2;
 ctx.save();ctx.translate(c.width,0);ctx.scale(-1,1);ctx.drawImage(v,sx,sy,side,side,0,0,c.width,c.height);ctx.restore();
 state.capture=c.toDataURL('image/jpeg',0.9);state.capturedCameraImage=state.capture;state.mode='capture';state.sourceLabel='Camera image';updateSourceButtons();startStory();
}

function startStory(){const first=visitorStates()[0];state.stage=first.stage;state.duration=first.duration;showExploreScreen();updateUI(false);processCurrent();}

async function useEinsteinDemo(){await selectSource('demo_einstein','Einstein');}

function showExploreScreen(){state.screen='explore';$('captureScreen').hidden=true;$('exploreScreen').hidden=false;window.scrollTo({top:0,behavior:'smooth'});}
function showCaptureScreen(){state.screen='capture';$('exploreScreen').hidden=true;$('captureScreen').hidden=false;toggleFacilitator(false);window.scrollTo({top:0,behavior:'smooth'});}

function visitorStateIndex(){return visitorStates().findIndex(x=>x.stage===state.stage&&x.duration===state.duration);}

async function applyVisitorState(rec){state.stage=rec.stage;state.duration=rec.duration;updateUI(true);await processCurrent();}

async function navigatePrevious(){
 const prescribed=previousPrescribedState();
 if(prescribed){await applyVisitorState(prescribed);return;}
 const j=STAGE_ORDER.indexOf(state.stage);if(j<=0){toast('This is the first visitor step.');return;}
 state.stage=STAGE_ORDER[j-1];updateUI(true);await processCurrent();
}

async function navigateForward(){
 const prescribed=nextPrescribedState();
 if(prescribed){await applyVisitorState(prescribed);return;}
 const inStoryStage=visitorStageOrder().includes(state.stage);
 if(inStoryStage){toast('This is the final visitor step.');return;}
 const j=STAGE_ORDER.indexOf(state.stage);if(j<0||j>=STAGE_ORDER.length-1){toast('The full AA4 array is already built.');return;}
 state.stage=STAGE_ORDER[j+1];updateUI(true);await processCurrent();
}

async function buildNextStage(){await navigateForward();}

async function toggleRotation(){
 state.duration=state.duration==='snapshot'?'6h':'snapshot';
 updateUI(true);
 if(state.duration==='6h'){$('earthIcon').classList.remove('spinning');void $('earthIcon').offsetWidth;$('earthIcon').classList.add('spinning');if(state.uvDisplayMode==='static'){$('uvStack').classList.add('rotating');setTimeout(()=>$('uvStack').classList.remove('rotating'),1550);}}
 await processCurrent();
}

async function jumpVisitorStage(stage){const rec=recommendedVisitorStateForStage(stage)||{stage,duration:'snapshot'};state.stage=rec.stage;state.duration=rec.duration;if(state.screen!=='explore'&&state.mode)showExploreScreen();updateUI(true);if(state.mode)await processCurrent();}
async function setDemoStory(mode){
 if(!DEMO_STORIES[mode]||mode===state.demoStory)return;state.demoStory=mode;buildStageTrack();
 const first=visitorStates()[0];state.stage=first.stage;state.duration=first.duration;
 document.querySelectorAll('[data-demo-story]').forEach(b=>b.classList.toggle('active',b.dataset.demoStory===state.demoStory));
 if(state.screen!=='explore'&&state.mode)showExploreScreen();updateUI(false);if(state.mode)await processCurrent();
}
function setImageRevealMode(mode){if(!['after','immediate'].includes(mode))return;state.imageRevealMode=mode;document.querySelectorAll('[data-image-reveal]').forEach(b=>b.classList.toggle('active',b.dataset.imageReveal===mode));toast(mode==='after'?'Animated observations reveal the image when the tracks finish.':'Images appear as soon as reconstruction is ready.');}
async function jumpStage(stage){state.stage=stage;if(state.screen!=='explore'&&state.mode)showExploreScreen();updateUI(true);if(state.mode)await processCurrent();}
async function jumpDuration(duration){state.duration=duration;updateUI(true);if(state.mode)await processCurrent();}

function updateUI(animate=true){
 if(!state.metadata)return;
 const stage=state.stage,meta=state.metadata.stages[stage],six=state.duration==='6h';
 const coreIndex=visitorStateIndex(),states=visitorStates(),stageOrder=visitorStageOrder();
 const copy=state.demoStory==='build'&&buildStory[stage]?{...story[stage],...buildStory[stage]}:story[stage];
 if(state.demoStory==='build'&&coreIndex>=0)$('storyEyebrow').textContent=`Build the SKA · ${coreIndex+1} of ${states.length}`;
 else $('storyEyebrow').textContent=coreIndex===0?'Step 2 · Start with a small array':coreIndex===1?'Step 3 · Build the full SKA':coreIndex===2?'Step 4 · Let Earth rotate':`Facilitator view · ${stage}`;
 $('storyTitle').textContent=copy.title; $('storyPrompt').textContent=six?copy.six:copy.snapshot; $('heroQuestion').textContent=six?copy.questionSix:copy.questionSnapshot;
 $('sourceStatus').textContent=state.sourceLabel||'Source';$('resultStatus').textContent=`${stage} · ${six?'6 h Earth rotation':'Snapshot'} · ${imageModeLabel(state.imageMode)}`;
 $('stations').textContent=meta.stations.toLocaleString();$('pairs').textContent=meta.baseline_pairs.toLocaleString();$('maxBaseline').textContent=meta.max_baseline_km.toFixed(3)+' km';
 $('layoutImage').src=`/assets/layout_${slug(stage)}.png`; $('uvSnapshotImage').src=`/assets/uv_${slug(stage)}_snapshot.png`; $('uvEarthImage').src=`/assets/uv_${slug(stage)}_6h.png`;
 $('uvStack').classList.toggle('rotated',six); $('rotateButton').classList.toggle('active',six);
 const i=STAGE_ORDER.indexOf(stage),previous=STAGE_ORDER[i-1],next=STAGE_ORDER[i+1];
 const inStoryStage=stageOrder.includes(stage),prescribedPrevious=previousPrescribedState(),prescribedNext=nextPrescribedState();
 if(inStoryStage){$('buildPreviousButton').disabled=!prescribedPrevious;$('buildForwardButton').disabled=!prescribedNext;}else{$('buildPreviousButton').disabled=!previous;$('buildForwardButton').disabled=!next;}
 const coreNext=inStoryStage?prescribedNext:null;
 $('buildNextButton').disabled=inStoryStage?!coreNext:!next;
 if(coreNext){
  if(coreNext.stage===stage)$('buildNextLabel').textContent=coreNext.duration==='6h'?'Observe for 6 h':'Return to snapshot';
  else $('buildNextLabel').textContent=state.demoStory==='build'?`Build next → ${coreNext.stage}`:(coreNext.duration==='6h'?'Observe for 6 h':`Build full SKA → ${coreNext.stage}`);
 }else $('buildNextLabel').textContent=next?`Add stations → ${next}`:'Full array built';
 $('rotateButton').disabled=false;
 $('rotateLabel').textContent=six?'Return to snapshot':'Let Earth rotate';
 const visitorStageIndex=stageOrder.indexOf(stage);document.querySelectorAll('[data-track-stage]').forEach((n,j)=>{n.classList.toggle('done',visitorStageIndex>=0&&j<visitorStageIndex);n.classList.toggle('active',visitorStageIndex===j);});
 document.querySelectorAll('[data-demo-story]').forEach(b=>b.classList.toggle('active',b.dataset.demoStory===state.demoStory));
 document.querySelectorAll('[data-image-reveal]').forEach(b=>b.classList.toggle('active',b.dataset.imageReveal===state.imageRevealMode));
 document.querySelectorAll('[data-fac-stage]').forEach(b=>b.classList.toggle('active',b.dataset.facStage===stage)); document.querySelectorAll('[data-fac-duration]').forEach(b=>b.classList.toggle('active',b.dataset.facDuration===state.duration)); document.querySelectorAll('[data-image-mode]').forEach(b=>b.classList.toggle('active',b.dataset.imageMode===state.imageMode)); document.querySelectorAll('[data-uv-view]').forEach(b=>b.classList.toggle('active',b.dataset.uvView===state.uvDisplayMode));
 const fornaxCleaned=state.mode==='demo_fornax'&&state.imageMode==='science';
 $('scienceExplanation').textContent=copy.lesson+(six?' Earth rotation adds new sampling directions without moving the stations.':' A snapshot measures only one instant of the rotating sky.')+(fornaxCleaned?' Cleaned image uses a locally generated natural-weighted, positive support-constrained reconstruction on the same 1.5° field; the regeneration tool reproduces it from the optional source and exact geometry.':state.imageMode==='science'?' Science image uses a finer Fourier grid and an idealised positive, support-constrained iterative reconstruction; it is an exhibit diagnostic, not a replacement for research imaging software.':' Outreach view shows the dirty image directly so the effect of incomplete Fourier sampling stays visible.')+' For display, colour indicates intensity.';
 updateAngularScaleNote();
 $('lessonHeadline').textContent=copy.lesson;
 $('lessonDetail').textContent=stage==='AA2'?'AA2 is the surprise: lots of long baselines do not replace the short spacings needed for broad structure.':'Short spacings measure broad structure; long spacings measure fine detail; Earth rotation adds directions.';
 if(animate){$('layoutImage').classList.remove('active');void $('layoutImage').offsetWidth;if(state.scienceTab==='layout')$('layoutImage').classList.add('active');}
 const animateTracks=animate&&six&&state.uvDisplayMode==='animated'&&state.scienceTab==='uv';
 state.delayNextImageReveal=Boolean(animateTracks&&state.imageRevealMode==='after');
 state.pendingUvAnimationPromise=refreshUvDisplay({animate:animateTracks}).catch(err=>{console.warn('Could not refresh uv display',err);});
}

async function processCurrent(){
 if(!state.mode)return;
 const token=++state.requestToken,delayForAnimation=state.delayNextImageReveal,animationPromise=state.pendingUvAnimationPromise;state.delayNextImageReveal=false;
 if(state.aborter)state.aborter.abort();state.aborter=new AbortController();
 $('workingText').textContent='Measuring the Fourier sky…';$('working').hidden=false;$('radioImage').parentElement.classList.add('transitioning');
 try{
  const payload={stage:state.stage,duration:state.duration,mode:state.mode,image_mode:state.imageMode};if(state.mode==='capture')payload.image_data=state.capture;
  const r=await fetch('/api/process',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),signal:state.aborter.signal});const j=await r.json();
  if(token!==state.requestToken)return;if(!j.ok)throw new Error(j.error);
  if(delayForAnimation){$('workingText').textContent='Collecting measurements…';await animationPromise;if(token!==state.requestToken)return;}
  state.sourceLabel=j.source_label||state.sourceLabel;$('sourceStatus').textContent=state.sourceLabel;$('skyImage').src=j.artificial_sky;$('radioImage').src=j.radio_portrait;
  $('timing').textContent=j.precomputed?`${imageModeLabel(j.image_mode)} · precomputed locally for instant display · reproducible with ${j.reproducible_with}`:`${imageModeLabel(j.image_mode)} · local processing ${j.timing_ms.total} ms · preprocess ${j.timing_ms.preprocess} · FFT ${j.timing_ms.fft_embed} · imaging ${j.timing_ms.imaging} · restoration ${j.timing_ms.restoration}`;
 }catch(err){if(err.name!=='AbortError'){toast('Could not reconstruct portrait.');console.error(err);}}
 finally{if(token===state.requestToken){$('working').hidden=true;$('workingText').textContent='Measuring the Fourier sky…';$('radioImage').parentElement.classList.remove('transitioning');}}
}

function setScienceTab(tab){state.scienceTab=tab;document.querySelectorAll('[data-science-tab]').forEach(b=>b.classList.toggle('active',b.dataset.scienceTab===tab));document.querySelectorAll('.science-image').forEach(x=>x.classList.remove('active'));const map={layout:'layoutImage',uv:'uvStack',sky:'skyImage'};$(map[tab]).classList.add('active');$('uvViewToggle').hidden=tab!=='uv';$('uvColourLegend').hidden=tab!=='uv';if(tab==='uv')refreshUvDisplay({animate:state.uvDisplayMode==='animated'&&state.duration==='6h'}).catch(err=>console.warn(err));}
function toggleSciencePanel(){const p=document.querySelector('.science-panel'),collapsed=p.classList.toggle('collapsed');$('scienceToggle').textContent=collapsed?'Show':'Hide';$('scienceToggle').setAttribute('aria-expanded',String(!collapsed));}
function toggleFacilitator(force){const d=$('facilitatorDrawer');const open=force===undefined?!d.classList.contains('open'):force;d.classList.toggle('open',open);d.setAttribute('aria-hidden',String(!open));}
async function toggleFullscreen(){try{if(!document.fullscreenElement)await document.documentElement.requestFullscreen();else await document.exitFullscreen();}catch(e){console.warn(e);}}

function resetForNewImage(){
 state.capture=null;state.capturedCameraImage=null;state.mode=null;state.sourceLabel='No source';state.demoStory='build';state.imageRevealMode='after';state.stage='AA1';state.duration='snapshot';state.imageMode='outreach';state.uvDisplayMode='animated';buildStageTrack();cancelUvAnimation();state.requestToken++;if(state.aborter)state.aborter.abort();
 const c=$('captureCanvas');c.getContext('2d').clearRect(0,0,c.width,c.height);updateSourceButtons();$('radioImage').removeAttribute('src');$('skyImage').removeAttribute('src');$('timing').textContent='No portrait processed yet.';updateUI(false);showCaptureScreen();toast('Ready for a new image.');
}
function toast(message){const t=$('toast');t.textContent=message;t.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.hidden=true,2200);}

init().catch(err=>{console.error(err);alert('Could not start the SKA Radio Portrait app.');});
