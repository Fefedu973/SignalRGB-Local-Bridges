const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
async function main(){
 const source=fs.readFileSync(__dirname+'/NVIDIA_RTX3080Ti_FE_Bridge.js','utf8');
 const packets=[],events=[],controllers=new Map(),clock={now:0};let socket;
 const context=vm.createContext({Date:{now:()=>clock.now},LightingMode:'Canvas',GpuBrightness:75,
  controller:{id:'nvidia-fe-2208-1535-nvapi'},device:{setName(){},setSize(){},setControllableLeds(){},color:(x,y)=>x?[120,120,120]:[30,50,70],log(){}},
  service:{hasController:id=>controllers.has(id),addController:c=>controllers.set(c.id,c),updateController:c=>controllers.set(c.id,c),announceController:c=>events.push(c.id)}});
 const udp=new vm.SyntheticModule(['default'],function(){this.setExport('default',{createSocket(){socket={closed:false,bind:p=>assert.equal(p,0),on(){},write(msg,ip,port){assert.equal(typeof msg,'string');assert.equal(ip,'127.0.0.1');assert.equal(port,47687);packets.push(JSON.parse(msg));},close(){this.closed=true;}};return socket;}});},{context});
 const module=new vm.SourceTextModule(source,{context});await module.link(name=>{assert.equal(name,'@SignalRGB/udp');return udp;});await module.evaluate();const p=module.namespace;
 const discovery=new p.DiscoveryService();discovery.Initialize();discovery.Refresh();assert.equal(controllers.size,1);assert.equal(events.length,2);
 p.Initialize();p.Render();assert.deepEqual(packets[0].colors,[[30,50,70],[120,120,120]]);assert.equal(packets[0].brightness,75);
 clock.now=99;p.Render();assert.equal(packets.length,1);clock.now=100;p.Render();assert.equal(packets.length,1);
 clock.now=500;p.Render();assert.equal(packets.length,2);assert.equal(packets[1].op,'colors');
 context.LightingMode='Forced';context.forcedColor='#ff0040';clock.now=600;p.Render();assert.deepEqual(packets[2].colors,[[255,0,64],[255,0,64]]);
 p.Shutdown();assert.equal(packets[3].op,'release');assert(socket.closed);clock.now=1000;p.Render();assert.equal(packets.length,4);
 context.controller.id='other';p.Initialize();p.Render();assert.equal(packets.length,4);
 console.log('Actual ES module linked: Canvas, forced color, JSON UDP,100ms pacing,500ms refresh, shutdown, discovery and allowlist passed; no I/O.');
}
main().catch(error=>{console.error(error);process.exitCode=1;});
