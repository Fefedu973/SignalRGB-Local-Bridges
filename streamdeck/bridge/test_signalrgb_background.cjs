const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const file=require('node:path').join(__dirname,'SignalRGB_StreamDeck_Background.js');
const template=fs.readFileSync(file,'utf8');
const ID='streamdeck-background-canvas-v2';
let passed=0;
function check(name,run){run();passed++;console.log('PASS '+name);}
// Framing fixture only. Receiver tests validate actual JPEG decoding.
function jpegBytes(length=9500){const b=Array.from({length},(_,i)=>(i*31)%256);b[0]=255;b[1]=216;b[length-2]=255;b[length-1]=217;return b;}
function fixture({token=true,port=47685}={}) {
 let source=template.replace(/^import .*;\r?\n/m,'').replace(/export function /g,'function ');
 if(token)source=source.replace('const BRIDGE_TOKEN = "__LOCAL_SESSION_TOKEN__";', 'const BRIDGE_TOKEN = "synthetic-test-token-1234567890123456";');
 source=source.replace('const BRIDGE_PORT = 47685;',`const BRIDGE_PORT = ${port};`);
 const clock={now:100000},sends=[],captures=[],sockets=[],logs=[],controllers=new Map(),events=[],geometry={},native={bytes:jpegBytes()};
 const device={setName(){},setSize(v){geometry.size=Array.from(v);},setControllableLeds(n,p){geometry.names=Array.from(n);geometry.positions=Array.from(p,v=>Array.from(v));},
  setFrameRateTarget(v){geometry.target=v;},color(){throw Error('Full Canvas must never sample individual pixels/keys');},
  getImageBuffer(x,y,w,h,options){captures.push({x,y,w,h,options:JSON.parse(JSON.stringify(options))});assert(x+w<geometry.size[0]);assert(y+h<geometry.size[1]);return native.bytes;},log:v=>logs.push(v)};
 for(const key of ['write','read','send_report','get_report','control_transfer','bulk_transfer'])device[key]=()=>{throw Error('No USB');};
 const service={hasController:id=>controllers.has(id),addController(c){assert(!controllers.has(c.id));controllers.set(c.id,c);events.push('add');},updateController(c){assert(controllers.has(c.id));controllers.set(c.id,c);events.push('update');},announceController(c){assert(controllers.has(c.id));events.push('announce');}};
 const context=vm.createContext({device,service,controller:{id:ID},Date:{now:()=>clock.now},LightingMode:'Canvas',forcedColor:'#00ff80',BackgroundFps:20,udp:{createSocket(){
  const handlers={},socket={closed:false,handlers,on:(event,fn)=>handlers[event]=fn,write(msg,ip,port){assert(!socket.closed);assert.equal(typeof msg,'string');sends.push({msg:JSON.parse(msg),wire:msg,ip,port});},close(){socket.closed=true;}};sockets.push(socket);return socket;}}});
 vm.runInContext(source+';globalThis.api={Initialize,Render,Shutdown,Validate,DiscoveryService,Type,Size,DefaultScale,DefaultPosition,RenderFrameDelay,Version};',context);
 return {api:context.api,context,clock,sends,captures,sockets,logs,events,controllers,geometry,native};
}
check('single native full-source crop reconstructs all JPEG bytes from bounded datagrams',()=>{
 const s=fixture();s.api.Initialize();s.api.Render();assert.equal(s.api.Type(),'network');assert.equal(s.api.Version(),'0.2.0');assert(s.api.Validate());
 assert.deepEqual(s.geometry.size,[321,201]);assert.equal(s.api.DefaultScale(),1);assert.equal(s.api.RenderFrameDelay(),10);assert.equal(s.captures.length,1);
 assert.deepEqual(s.captures[0],{x:0,y:0,w:320,h:200,options:{outputWidth:480,outputHeight:272,format:'JPEG',flipV:false,flipH:false}});
 assert.equal(s.sends.length,10);assert.deepEqual(s.sends.flatMap(v=>v.msg.data),s.native.bytes);
 s.sends.forEach(({msg,ip,port},i)=>{assert.equal(msg.kind,'canvas-jpeg');assert.equal(msg.part,i);assert.equal(msg.total,10);assert.equal(msg.frame,s.sends[0].msg.frame);assert.equal(msg.lease_ms,2000);assert(msg.data.length<=1024);assert.equal(ip,'127.0.0.1');assert.equal(port,47685);assert(!('colors'in msg));assert(Buffer.byteLength(JSON.stringify(msg))<5000);});
});
check('layout markers follow15 native tile centers without shrinking capture',()=>{
 const s=fixture();s.api.Initialize();assert.equal(s.geometry.names.length,15);assert.deepEqual(s.geometry.positions[0],[31,30]);assert.deepEqual(s.geometry.positions[14],[290,173]);assert.equal(s.geometry.target,60);assert.deepEqual(Array.from(s.api.DefaultPosition()),[0,0]);
});
check('20fps pacing skips capture before50ms and frame IDs increase',()=>{
 const s=fixture();s.api.Initialize();s.api.Render();s.clock.now+=49;s.api.Render();assert.equal(s.captures.length,1);s.clock.now++;s.api.Render();assert.equal(s.captures.length,2);assert(s.sends[10].msg.frame>s.sends[0].msg.frame);
});
check('FPS caps at30; missing settings default20',()=>{
 const s=fixture();delete s.context.BackgroundFps;delete s.context.LightingMode;s.api.Initialize();s.api.Render();s.clock.now+=49;s.api.Render();assert.equal(s.captures.length,1);s.clock.now++;s.api.Render();s.context.BackgroundFps=1000;s.clock.now+=33;s.api.Render();assert.equal(s.captures.length,2);s.clock.now++;s.api.Render();assert.equal(s.captures.length,3);
});
check('Forced is the only15-color path and does not capture',()=>{
 const s=fixture();s.context.LightingMode='Forced';s.api.Initialize();s.api.Render();assert.equal(s.captures.length,0);assert.equal(s.sends.length,1);assert(s.sends[0].msg.colors.every(c=>JSON.stringify(c)==='[0,255,128]'));s.clock.now+=50;s.context.forcedColor='invalid';s.api.Render();assert(s.sends[1].msg.colors.every(c=>JSON.stringify(c)==='[0,0,0]'));
});
check('inert template never captures or sends',()=>{const s=fixture({token:false});s.api.Initialize();s.api.Render();assert.equal(s.sends.length,0);assert.equal(s.captures.length,0);});
check('custom local session port preserves loopback for all fragments',()=>{const s=fixture({port:47800});s.api.Initialize();s.api.Render();assert(s.sends.every(v=>v.port===47800&&v.ip==='127.0.0.1'));});
check('Initialize replaces socket; Shutdown suppresses captures and writes',()=>{
 const s=fixture();s.api.Initialize();s.api.Initialize();assert(s.sockets[0].closed);s.api.Render();s.api.Shutdown();assert(s.sockets[1].closed);s.clock.now+=500;s.api.Render();assert.equal(s.captures.length,1);s.api.Shutdown();
});
check('discovery uses fresh full-canvas identity and reannounces afterreload',()=>{
 const s=fixture();let d=new s.api.DiscoveryService();d.Initialize();d.Update();d=new s.api.DiscoveryService();d.Initialize();assert.deepEqual(s.events,['add','announce','update','announce']);assert.equal(s.controllers.size,1);assert.equal([...s.controllers.values()][0].id,ID);
});
check('Validate excludes old15-color controller and unrelated/missing data',()=>{
 const s=fixture();for(const id of ['streamdeck-background-loopback','other']){s.context.controller={id};assert.equal(s.api.Validate(),false);}s.context.controller=null;assert.equal(s.api.Validate(),false);delete s.context.controller;assert.equal(s.api.Validate(),false);
});
check('256KiB produces exactly256 compactfragments',()=>{
 const s=fixture();s.native.bytes=jpegBytes(256*1024);s.api.Initialize();s.api.Render();assert.equal(s.sends.length,256);assert(s.sends.every(v=>v.msg.data.length===1024&&v.msg.total===256&&Buffer.byteLength(v.wire)<5000));assert.deepEqual(s.sends.flatMap(v=>v.msg.data),s.native.bytes);
});
check('oversize/malformed images send nothing and never fallback to singlecolor',()=>{
 for(const bytes of [null,[],[255,216,0],jpegBytes(256*1024+1),[0,0,255,217],[255,216,0,0]]){const s=fixture();s.native.bytes=bytes;s.api.Initialize();s.api.Render();assert.equal(s.sends.length,0);assert(s.logs.some(v=>v.includes('invalid')));}
});
check('missing nativeAPI fails explicitly and throttles repeaterrors',()=>{
 const s=fixture();delete s.context.device.getImageBuffer;s.api.Initialize();s.api.Render();s.clock.now+=50;s.api.Render();assert.equal(s.sends.length,0);assert.equal(s.logs.filter(v=>v.includes('unavailable')).length,1);
});
check('capture/socket exceptions never expose token orpayload',()=>{
 const s=fixture();s.api.Initialize();s.context.device.getImageBuffer=()=>{throw Error('synthetic-test-token-private');};s.api.Render();s.clock.now+=50;s.context.LightingMode='Forced';s.sockets[0].write=()=>{throw Error('secret-packet');};s.api.Render();s.sockets[0].handlers.error('secret-packet');assert(!s.logs.join('\n').includes('secret'));assert(!s.logs.join('\n').includes('synthetic-test-token'));
});
check('typed bytearray becomes numericJSONarrays preservingbytes',()=>{
 const s=fixture();s.native.bytes=Uint8Array.from(jpegBytes());s.api.Initialize();s.api.Render();assert.deepEqual(s.sends.flatMap(v=>v.msg.data),Array.from(s.native.bytes));
});
check('old renderer cannot send even if native host skipped Validate on hot reload',()=>{const s=fixture();s.context.controller.id='streamdeck-background-loopback';s.api.Initialize();s.api.Render();assert.equal(s.sockets.length,0);assert.equal(s.captures.length,0);assert(s.logs.some(v=>v.includes('inactive')));});
assert(!/export function (VendorId|ProductId)|device\.(write|read|send_report|get_report|control_transfer|bulk_transfer|color)\s*\(/.test(template));
console.log(`${passed} tests passed; no native, USB, or network I/O executed.`);
