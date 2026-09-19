'use strict';
// Exact-build, in-memory compositor bridge. All paint work stays in the native
// queued animate slot. No Storage calls, profile writes, or direct USB writes.
const exe=Process.getModuleByName('StreamDeck.exe'),gui=Process.getModuleByName('Qt6Gui.dll'),core=Process.getModuleByName('Qt6Core.dll');
// Frida process enumeration may omit this elevated process. Check the actual
// main module before any interceptor or native call is created instead.
const expectedPath='c:\\program files\\elgato\\streamdeck\\streamdeck.exe';
if(Process.mainModule.name.toLowerCase()!=='streamdeck.exe'||exe.path.replace(/\//g,'\\').toLowerCase()!==expectedPath)throw Error('Unexpected target main module/path');
const meta=exe.base.add(0x1578290),start=Date.now();
let target=null,armed=false,deadline=0,dirty=false,restore=false,colors=null,tiles=null;
let pending=null,sequence=0,lastQueued=0,errors=0,compositions=0,paints=0,acknowledged=0,restores=0,rejectedCandidates=0;
// BEGIN FRAME PACING
class FramePacing {
 constructor(maxFps=20,now=Date.now()){this.maxFps=maxFps;this.nextAt=0;this.reset(now);}
 reset(now){this.since=now;this.received=0;this.coalesced=0;this.queueTimes=[];this.ackTimes=[];this.latencies=[];this.inputAges=[];this.lastInputAt=null;}
 configure(options,now=Date.now()){
  if(!options||typeof options!=='object'||!Number.isInteger(options.maxFps)||options.maxFps<1||options.maxFps>30)throw Error('maxFps must be an integer from 1 to 30');
  if(options.resetMetrics!==undefined&&typeof options.resetMetrics!=='boolean')throw Error('resetMetrics must be boolean');
  this.maxFps=options.maxFps;this.nextAt=now;
  if(options.resetMetrics)this.reset(now);
  return {maxFps:this.maxFps,dispatchIntervalMs:5};
 }
 input(wasDirty,now){this.received++;if(wasDirty)this.coalesced++;this.lastInputAt=now;}
 canQueue(hasTarget,hasPending,fault,now){return hasTarget&&!hasPending&&!fault&&now>=this.nextAt;}
 push(array,value){array.push(value);if(array.length>256)array.shift();}
 queued(now,isRestore){
  const period=1000/this.maxFps;
  // Retain phase within one interval; after a stall resume from now without
  // building or replaying a catch-up queue.
  this.nextAt=this.nextAt===0||now-this.nextAt>=period?now+period:this.nextAt+period;
  if(!isRestore)this.push(this.queueTimes,now);
 }
 ack(frame,now){
  if(frame.restore)return;
  this.push(this.ackTimes,now);this.push(this.latencies,Math.max(0,now-frame.at));
  if(frame.inputAt!==null)this.push(this.inputAges,Math.max(0,now-frame.inputAt));
 }
 summary(values){
  if(!values.length)return {samples:0,mean:null,p50:null,p95:null,max:null};
  const sorted=values.slice().sort((a,b)=>a-b),pick=q=>sorted[Math.max(0,Math.ceil(q*sorted.length)-1)];
  return {samples:sorted.length,mean:Math.round(100*sorted.reduce((a,b)=>a+b,0)/sorted.length)/100,p50:pick(.5),p95:pick(.95),max:sorted[sorted.length-1]};
 }
 metrics(now=Date.now()){
  const seconds=Math.max(.001,Math.min(5,(now-this.since)/1000));
  const rate=times=>Math.round(100*times.filter(t=>t>now-5000).length/seconds)/100;
  return {maxFps:this.maxFps,dispatchIntervalMs:5,windowSeconds:seconds,received:this.received,coalesced:this.coalesced,
   queuedFps5s:rate(this.queueTimes),ackFps5s:rate(this.ackTimes),ackLatencyMs:this.summary(this.latencies),inputToAckMs:this.summary(this.inputAges)};
 }
}
// END FRAME PACING
const pacing=new FramePacing();
const paintedKeys=new Set(),nativeThreads=new Set(),activeFrames=new Map();
function emit(event,data={}){send({event,...data});}
function check(m,rva,hex){const b=Array.from(new Uint8Array(m.base.add(rva).readByteArray(hex.length/2))).map(x=>x.toString(16).padStart(2,'0')).join('');if(b!==hex)throw Error('Unsupported code '+m.name+'+'+rva.toString(16));}
function describe(p){try{const a=ptr(p),m=Process.findModuleByAddress(a);return m?m.name+'+'+a.sub(m.base):a.toString();}catch(_){return null;}}
function fail(e){armed=false;dirty=false;restore=false;errors++;emit('native-error',{message:String(e),type:e.type||null,address:e.address?describe(e.address):null,pc:e.context?describe(e.context.pc):null,stack:e.stack||null});}
if(Process.arch!=='x64'||exe.size!==0x1aab000)throw Error('Unsupported Stream Deck build');
check(exe,0x5c8550,'488bc444894018555356574154415541');
check(exe,0x419a80,'48895c24185556574154415541564157');
check(exe,0x41551b,'c744243002000000');
check(exe,0x177c80,'48895c24084889742410574883ec20');
check(gui,0x43970,'405355564883ec50');
check(gui,0x3ab50,'40534883ec204883791000');
const activate=new NativeFunction(core.getExportByName('?activate@QMetaObject@@SAXPEAVQObject@@PEBU1@HPEAPEAX@Z'),'void',['pointer','pointer','int','pointer'],'win64');
const fill=new NativeFunction(gui.getExportByName('?fill@QImage@@QEAAXI@Z'),'void',['pointer','uint'],'win64');
const bits=new NativeFunction(gui.getExportByName('?bits@QImage@@QEAAPEAEXZ'),'pointer',['pointer'],'win64');
function validTarget(t){return t&&t.composer.readPointer().equals(exe.base.add(0x166f090))&&t.owner.readPointer().equals(exe.base.add(0x16555e8))&&t.owner.add(0x18).readU32()===5&&t.owner.add(0x1c).readU32()===3;}
function ownerOf(bundle){const composer=bundle.add(0x28).readPointer().sub(0x10),owner=composer.sub(0x4f0),t={composer,owner};return validTarget(t)?t:null;}
function validTileImage(image){
 const d=image.add(16).readPointer();
 return !d.isNull()&&d.add(4).readS32()===72&&d.add(8).readS32()===72&&[4,5,6].includes(d.add(64).readS32())&&d.add(72).readS64().toNumber()===288;
}
function readLayout(t){
 if(!validTarget(t))throw Error('Target expired');
 const c=t.composer,b=c.add(0xe8).readPointer(),e=c.add(0xf0).readPointer();
 const vectorBytes=e.sub(b).toInt32();
 const tileWidth=c.add(0x28).readS32(),tileHeight=c.add(0x2c).readS32();
 // With no page background, native assign() legitimately leaves this vector
 // empty. Only a verified 72px composition of the pinned 5x3 device may use
 // the MK.2 geometry measured in the successful native-background session.
 if(vectorBytes===0&&t.tileVerified&&tileWidth===72&&tileHeight===72){
  return {width:480,height:272,tileWidth,tileHeight,positions:Array.from({length:15},(_,i)=>[11+(i%5)*97,5+Math.floor(i/5)*97]),columns:5,rows:3,source:'verified-mk2-fallback'};
 }
 if(vectorBytes!==120)throw Error('Unsupported native layout vector: '+vectorBytes+' bytes');
 const d=c.add(0xe0).readPointer();
 if(d.isNull())return null;
 const width=d.add(4).readS32(),height=d.add(8).readS32();
 const positions=Array.from({length:15},(_,i)=>[b.add(i*8).readS32(),b.add(i*8+4).readS32()]);
 if(tileWidth!==72||tileHeight!==72||width<72||width>4096||height<72||height>4096||positions.some(p=>p[0]<0||p[1]<0||p[0]+72>width||p[1]+72>height))throw Error('Unsupported background geometry');
 return {width,height,tileWidth,tileHeight,positions,columns:5,rows:3,source:'native-background'};
}
function layout(){return target?readLayout(target):null;}
function selectTarget(t,image){
 // Thumbnails, unloaded backgrounds and other renderers share this vtable.
 // An unselected candidate must never fault the bridge or retain its pointer.
 try{
  if(!validTileImage(image))return false;
  t.tileVerified=true;
  const candidate=readLayout(t);if(!candidate)return false;
  target=t;emit('target-ready',{layout:candidate});return true;
 }catch(e){
  rejectedCandidates++;
  if(rejectedCandidates<=5)emit('target-skipped',{reason:String(e)});
  return false;
 }
}
// Tag the actual Qt-owned vector, not unrelated native animation notifications.
Interceptor.attach(exe.base.add(0x177c80),{onEnter(a){
 if(pending&&a[1].equals(pending.input)){pending.copies.add(a[0].toString());}
}});
Interceptor.attach(exe.base.add(0x419a80),{onEnter(a){
 this.tagged=null;
 if(target&&a[0].equals(target.owner)&&pending&&pending.copies.has(a[1].toString())){
  this.tagged=pending;this.tid=Process.getCurrentThreadId();nativeThreads.add(this.tid);activeFrames.set(this.tid,this.tagged);
 }
},onLeave(){if(this.tagged)activeFrames.delete(this.tid);if(this.tagged&&pending===this.tagged){
 acknowledged++;if(pending.restore)restores++;
 pacing.ack(pending,Date.now());
 if(acknowledged<=3||acknowledged%100===0)emit('frame-ack',{sequence:pending.sequence,restore:pending.restore,latencyMs:Date.now()-pending.at});
 pending=null;
}}});
function queueFrame(isRestore){
 const now=Date.now();
 if(!pacing.canQueue(!!target,!!pending,errors,now))return false;
 if(!validTarget(target))throw Error('Target lifetime changed');
 const entries=Memory.alloc(240),v=Memory.alloc(24),argv=Memory.alloc(16);
 for(let i=0;i<15;i++){entries.add(i*16).writeU64(i);entries.add(i*16+8).writeU64(0);}
 v.writePointer(entries);v.add(8).writePointer(entries.add(240));v.add(16).writePointer(entries.add(240));argv.writePointer(ptr(0));argv.add(8).writePointer(v);
 pending={input:v,entries,argv,copies:new Set(),sequence:++sequence,restore:isRestore,at:now,
  inputAt:isRestore?null:pacing.lastInputAt,colors,tiles};
 lastQueued=now;pacing.queued(now,isRestore);activate(target.composer,meta,0,argv);
 if(pending&&pending.copies.size===0)throw Error('Qt vector copy not observed; refusing further notifications');
 return true;
}
// Only our exact Qt notification uses synchronous composition. Preserve
// bundle render options and set the non-filtering immediate-render bit0.
check(exe,0x5c8a80,'48895c242055565741564157');
Interceptor.attach(exe.base.add(0x5c8a80),{onEnter(a){
 if(errors||!activeFrames.has(Process.getCurrentThreadId()))return;
 try{
  const t=ownerOf(a[0]);if(!t||!target||!t.composer.equals(target.composer))return;
  a[3]=ptr((a[3].toInt32()||a[0].add(0x48).readU32())|1);
 }catch(e){fail(e);}
}});
Interceptor.attach(exe.base.add(0x5c8550),{onEnter(a){
 compositions++;
 try{
  const bundle=a[0],image=a[1],t=ownerOf(bundle);if(!t)return;
  if(target&&!t.composer.equals(target.composer))return;
  if(!target&&!selectTarget(t,image))return;
  if(!armed||Date.now()>=deadline||errors)return;
  const frame=activeFrames.get(Process.getCurrentThreadId());
  if(frame&&frame.restore)return;
  const frameTiles=frame?frame.tiles:tiles,frameColors=frame?frame.colors:colors;
  const key=bundle.readU64().toNumber();if(key<0||key>=15)return;
  const d=image.add(16).readPointer();if(d.isNull())return;
  if(d.add(4).readS32()!==72||d.add(8).readS32()!==72||![4,5,6].includes(d.add(64).readS32()))return;
  if(frameTiles){
   // Public bits() detaches the temporary QImage before exposing mutable pixels.
   const pixels=bits(image),owned=image.add(16).readPointer();
   if(pixels.isNull()||owned.add(72).readS64().toNumber()!==288)throw Error('Unexpected detached image stride');
   pixels.writeByteArray(frameTiles[key]);
  }else if(frameColors){const c=frameColors[key];fill(image,(0xff000000|(c[0]<<16)|(c[1]<<8)|c[2])>>>0);}
  paints++;paintedKeys.add(key);
 }catch(e){fail(e);}
}});
function lease(ms){if(!Number.isInteger(ms)||ms<500||ms>10000)throw Error('lease_ms must be500..10000');const now=Date.now();pacing.input(dirty,now);deadline=now+ms;armed=true;dirty=true;restore=false;}
function stop(){armed=false;dirty=false;restore=target!==null&&!errors;colors=null;tiles=null;return {stopped:true,restorationPending:restore};}
rpc.exports={
 layout,
 status(){return {ready:!!target,armed,restorationPending:restore,errors,compositions,paints,paintedKeys:[...paintedKeys],queued:sequence,acknowledged,restores,rejectedCandidates,pending:pending?pending.sequence:null,nativeThreads:[...nativeThreads],uptimeMs:Date.now()-start,pacing:pacing.metrics()};},
 configure(options){return pacing.configure(options);},
 setcolors(value,ms){if(!Array.isArray(value)||value.length!==15||value.some(c=>!Array.isArray(c)||c.length!==3||c.some(v=>!Number.isInteger(v)||v<0||v>255)))throw Error('Expected15 RGB triplets');if(errors)throw Error('Native bridge faulted');colors=value.map(c=>c.slice());tiles=null;lease(ms);return {accepted:true};},
 setframe(ms,data){if(!(data instanceof ArrayBuffer)||data.byteLength!==311040)throw Error('Expected311040 BGRA bytes');if(errors)throw Error('Native bridge faulted');const bytes=new Uint8Array(data);for(let i=3;i<bytes.length;i+=4)if(bytes[i]!==255)throw Error('Only opaque BGRA accepted');tiles=Array.from({length:15},(_,i)=>data.slice(i*20736,(i+1)*20736));colors=null;lease(ms);return {accepted:true};},
 stop
};
setInterval(()=>{
 if(errors)return;
 try{
  if(pending&&Date.now()-pending.at>3000)throw Error('Native queued frame timeout; bridge stopped');
  if(armed&&Date.now()>=deadline){stop();emit('lease-expired');}
  if(restore){if(queueFrame(true))restore=false;}
  else if(dirty&&armed){if(queueFrame(false))dirty=false;}
 }catch(e){fail(e);}
},5);
emit('ready',{stage:'background-api-core-fps-candidate',pid:Process.id,maxFps:pacing.maxFps});
