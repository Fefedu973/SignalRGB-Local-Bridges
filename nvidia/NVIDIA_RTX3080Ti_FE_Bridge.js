import udp from "@SignalRGB/udp";

const PORT=47687, ID="nvidia-fe-2208-1535-nvapi";
export function Name(){return "NVIDIA RTX 3080 Ti FE — NVAPI";}
export function Version(){return "0.1.1";}
export function Publisher(){return "Fefedu973";}
export function Type(){return "network";}
export function Size(){return [2,1];}
export function DefaultPosition(){return [10,10];}
export function DefaultScale(){return 4;}
export function ControllableParameters(){return [
    {property:"LightingMode",group:"lighting",label:"Lighting Mode",type:"combobox",values:["Canvas","Forced"],default:"Canvas"},
    {property:"forcedColor",group:"lighting",label:"Forced Color",type:"color",default:"#0055aa"},
    {property:"GpuBrightness",group:"lighting",label:"Brightness",type:"number",min:0,max:100,step:1,default:100}
];}
let socket=null,lastSend=-Infinity,lastHeartbeat=-Infinity,lastColor=null,sequence=0,lastError="";
function report(text){if(text!==lastError)device.log(text,{toFile:true});lastError=text;}
export function Initialize(){
    if(socket){socket.close();socket=null;}
    if(!Validate())return;
    device.setName("RTX 3080 Ti FE — RGBW + monochrome");
    device.setSize(Size());
    device.setControllableLeds(["Front RGBW","Top / logo — monochrome brightness"],[[0,0],[1,0]]);
    socket=udp.createSocket();socket.bind(0);
    socket.on("message",message=>{
        if(!message || !["127.0.0.1","::ffff:127.0.0.1"].includes(message.address))return;
        if(message.port!==undefined && Number(message.port)!==PORT)return;
        try{const reply=JSON.parse(message.data);if(reply.ok===false || reply.error)report("NVAPI bridge: "+String(reply.error));}
        catch(_){report("NVAPI bridge: invalid local response");}
    });
    socket.on("error",()=>report("NVAPI bridge: local UDP error"));
    lastSend=-Infinity;lastHeartbeat=-Infinity;lastColor=null;
}
function sample(){
    if(typeof LightingMode!=="undefined" && LightingMode==="Forced"){
        const match=/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(String(typeof forcedColor==="undefined"?"#000000":forcedColor));
        const rgb=match?match.slice(1).map(v=>parseInt(v,16)):[0,0,0];return [rgb,rgb.slice()];
    }
    return [device.color(0,0),device.color(1,0)];
}
export function Render(){
    if(!socket)return;
    const now=Date.now();if(now-lastSend<100)return;
    const colors=sample();
    const brightness=Math.max(0,Math.min(100,Math.round(Number(typeof GpuBrightness==="undefined"?100:GpuBrightness))));
    const serialized=JSON.stringify([colors,brightness]);
    if(serialized!==lastColor || now-lastHeartbeat>=500){
        socket.write(JSON.stringify({id:++sequence,op:"colors",colors,brightness}),"127.0.0.1",PORT);
        lastSend=now;lastHeartbeat=now;lastColor=serialized;
    }
}
export function Shutdown(){
    if(socket){socket.write(JSON.stringify({id:++sequence,op:"release"}),"127.0.0.1",PORT);socket.close();socket=null;}
}
export function Validate(){return typeof controller!=="undefined" && !!controller && controller.id===ID;}
export function DiscoveryService(){
    this.PollInterval=5000;
    this.localController={id:ID,name:"RTX 3080 Ti FE — NVAPI",ip:"127.0.0.1",port:PORT};
    this.Refresh=function(){
        if(!service.hasController(ID))service.addController(this.localController);
        else service.updateController(this.localController);
        service.announceController(this.localController);
    };
    this.Initialize=function(){this.Refresh();};this.Update=function(){};
}
