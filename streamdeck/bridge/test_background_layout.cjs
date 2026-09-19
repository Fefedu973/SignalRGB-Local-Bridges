const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const code=fs.readFileSync(require('node:path').join(__dirname,process.argv[2]||'background-core.js'),'utf8');
// Execute the actual selection/read code with deterministic memory fixtures,
// including the empty QPoint vector seen during the failed live startup.
const selected=code.slice(code.indexOf('function validTarget('),code.indexOf('// Tag the actual'));
function fixture({vectorBytes=120,width=480,height=272,tile=72,nullImage=false,imageSize=72,imageFormat=5,imageStride=288,ownerColumns=5}={}) {
 const memory=new Map(),events=[];
 class P {
  constructor(n){this.n=n;} add(n){return new P(this.n+n);} sub(n){return new P(this.n-(n instanceof P?n.n:n));}
  readPointer(){return new P(memory.get(this.n)||0);} readU32(){return memory.get(this.n)||0;} readS32(){return this.readU32();}
  readS64(){return {toNumber:()=>this.readU32()};}
  toInt32(){return this.n;} equals(p){return this.n===p.n;} isNull(){return this.n===0;}
 }
 const owner=new P(0x100000),composer=owner.add(0x4f0),base=new P(0x4000000),begin=0x200000,data=0x300000,image=new P(0x310000),imageData=0x320000;
 memory.set(image.n+16,imageData);memory.set(imageData+4,imageSize);memory.set(imageData+8,imageSize);
 memory.set(imageData+64,imageFormat);memory.set(imageData+72,imageStride);
 memory.set(owner.n,base.n+0x16555e8);memory.set(composer.n,base.n+0x166f090);
 memory.set(owner.n+0x18,ownerColumns);memory.set(owner.n+0x1c,3);
 memory.set(composer.n+0xe8,begin);memory.set(composer.n+0xf0,begin+vectorBytes);
 memory.set(composer.n+0x28,tile);memory.set(composer.n+0x2c,tile);
 memory.set(composer.n+0xe0,nullImage?0:data);memory.set(data+4,width);memory.set(data+8,height);
 for(let i=0;i<15;i++){memory.set(begin+i*8,11+(i%5)*97);memory.set(begin+i*8+4,5+Math.floor(i/5)*97);}
 const context=vm.createContext({exe:{base},emit:(event,data)=>events.push({event,...data}),target:null,rejectedCandidates:0});
 vm.runInContext(selected+';globalThis.api={selectTarget,layout};',context);
 return {context,events,t:{owner,composer},memory,begin,image};
}
let n=0;
function test(name,fn){fn();console.log('PASS '+name);n++;}
test('unsupported nonempty candidate is skipped without retaining its native pointer',()=>{
 const f=fixture({vectorBytes:64});assert.equal(f.context.api.selectTarget(f.t,f.image),false);
 assert.equal(f.context.target,null);assert.equal(f.context.rejectedCandidates,1);assert.equal(f.context.api.layout(),null);
 assert.match(f.events[0].reason,/64 bytes/);
 f.memory.set(f.t.composer.n+0xf0,f.begin+120);
 assert.equal(f.context.api.selectTarget(f.t,f.image),true);assert.equal(f.context.api.layout().positions.length,15);
});
test('thumbnail geometry and unloaded images do not select a target',()=>{
 for(const options of [{tile:32},{width:72,height:72},{nullImage:true}]){
  const f=fixture(options);assert.equal(f.context.api.selectTarget(f.t,f.image),false);assert.equal(f.context.target,null);
 }
});
test('verified native coordinates are preserved once selected',()=>{
 const f=fixture();assert.equal(f.context.api.selectTarget(f.t,f.image),true);
 const l=f.context.api.layout();assert.equal(l.width,480);assert.equal(l.height,272);
 assert.deepEqual(Array.from(l.positions[14]),[399,199]);assert.equal(f.events[0].event,'target-ready');
});
test('empty background uses previously measured geometry only after tile verification',()=>{
 const f=fixture({vectorBytes:0,nullImage:true});assert.equal(f.context.api.selectTarget(f.t,f.image),true);
 const l=f.context.api.layout();assert.equal(l.source,'verified-mk2-fallback');
 assert.deepEqual(Array.from(l.positions[14]),[399,199]);assert.equal(l.width,480);assert.equal(l.height,272);
});
test('fallback rejects wrong native dimensions format stride or device geometry',()=>{
 for(const options of [{imageSize:32},{imageFormat:3},{imageStride:512},{tile:32},{ownerColumns:8}]){
  const f=fixture({vectorBytes:0,...options});assert.equal(f.context.api.selectTarget(f.t,f.image),false);assert.equal(f.context.target,null);
 }
});
console.log(n+' selection tests passed; no process or native calls.');
