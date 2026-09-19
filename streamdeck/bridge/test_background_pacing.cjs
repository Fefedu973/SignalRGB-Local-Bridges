const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const filename=process.argv[2]||'background-core.js';
const code=fs.readFileSync(require('node:path').join(__dirname,filename),'utf8');
const block=code.slice(code.indexOf('// BEGIN FRAME PACING'),code.indexOf('// END FRAME PACING'));
const context=vm.createContext({});vm.runInContext(block+';globalThis.Pacing=FramePacing;',context);
const Pacing=context.Pacing;
let passed=0;
function test(name,run){run();passed++;console.log('PASS '+name);}
test('config accepts 1..30 only and does not mutate rate on invalid input',()=>{
 const p=new Pacing(20,0);assert.equal(p.maxFps,20);
 for(const maxFps of [0,31,1.5,true,'30',null])assert.throws(()=>p.configure({maxFps},0));
 assert.equal(p.maxFps,20);p.configure({maxFps:30},0);assert.equal(p.maxFps,30);
 assert.throws(()=>p.configure({maxFps:25,resetMetrics:1},0));assert.equal(p.maxFps,30);
});
test('5ms dispatcher delivers configured 10/20/25/30 rates without a catch-up queue',()=>{
 for(const fps of [10,20,25,30]){
  const p=new Pacing(fps,0),times=[];let inFlight=null;
  for(let now=0;now<10000;now+=5){
   if(inFlight&&now-inFlight.at>=5){p.ack(inFlight,now);inFlight=null;}
   if(p.canQueue(true,!!inFlight,0,now)){p.queued(now,false);inFlight={at:now,inputAt:now,restore:false};times.push(now);}
  }
  assert(Math.abs(times.length-10*fps)<=1,`${fps}: ${times.length}`);
  assert(times.every((t,i)=>i===0||t-times[i-1]>=Math.floor(1000/fps/5)*5));
 }
});
test('pending, target absence and faults each prevent a second native notification',()=>{
 const p=new Pacing(30,0);
 assert.equal(p.canQueue(true,true,0,5000),false);
 assert.equal(p.canQueue(false,false,0,5000),false);
 assert.equal(p.canQueue(true,false,1,5000),false);
 assert.equal(p.canQueue(true,false,0,5000),true);
 p.queued(5000,false);assert.equal(p.canQueue(true,false,0,5005),false);
});
test('coalescence counts overwritten waiting frames and retains latest input timestamp',()=>{
 const p=new Pacing(20,0);p.input(false,10);p.input(true,20);p.input(true,30);
 assert.equal(p.received,3);assert.equal(p.coalesced,2);assert.equal(p.lastInputAt,30);
 p.ack({at:40,inputAt:p.lastInputAt,restore:false},45);
 const m=p.metrics(1000);assert.equal(m.ackLatencyMs.p50,5);assert.equal(m.inputToAckMs.p50,15);
});
test('latency and rolling-rate storage is bounded and excludes restoration',()=>{
 const p=new Pacing(30,0);
 for(let i=0;i<400;i++){p.queued(i*40,false);p.ack({at:i*40,inputAt:i*40-2,restore:false},i*40+(i%20));}
 assert.equal(p.latencies.length,256);assert.equal(p.ackTimes.length,256);assert.equal(p.queueTimes.length,256);
 const before=p.ackTimes.length;p.ack({at:0,inputAt:null,restore:true},999999);assert.equal(p.ackTimes.length,before);
 const m=p.metrics(16000);assert(m.ackLatencyMs.p50>=9&&m.ackLatencyMs.p50<=10);assert.equal(m.ackLatencyMs.p95,19);
 assert.equal(m.ackLatencyMs.max,19);assert(m.ackFps5s>24&&m.ackFps5s<26);
 assert.equal(p.metrics(30000).ackFps5s,0);
});
test('benchmark reset clears samples and latest timestamp without losing configured rate',()=>{
 const p=new Pacing(20,0);p.input(false,1);p.ack({at:1,inputAt:1,restore:false},5);
 p.configure({maxFps:25,resetMetrics:true},100);const m=p.metrics(200);
 assert.equal(m.received,0);assert.equal(m.ackLatencyMs.samples,0);assert.equal(m.maxFps,25);assert.equal(p.lastInputAt,null);
});
console.log(passed+' cadence tests passed; no native, USB or network calls.');
