import udp from "@SignalRGB/udp";

// Replaced locally by the launcher. Never put a live token in a public plugin.
const BRIDGE_TOKEN = "__LOCAL_SESSION_TOKEN__";
const BRIDGE_PORT = 47685;
const BRIDGE_ID = "streamdeck-background-canvas-v2";
// The native crop API requires x+width < Size().width (and the same for Y).
const DEFAULT_CANVAS_WIDTH = 32;
let sourceWidth = DEFAULT_CANVAS_WIDTH, sourceHeight = 20;
const OUTPUT_WIDTH = 480, OUTPUT_HEIGHT = 272;
const CHUNK_BYTES = 1024, MAX_JPEG_BYTES = 256 * 1024;
export function Name() { return "Stream Deck Background"; }
export function Version() { return "0.2.1"; }
export function Type() { return "network"; }
export function Publisher() { return "Fefedu973"; }
export function Size() { return [sourceWidth + 1, sourceHeight + 1]; }
export function DefaultPosition() { return [0, 0]; }
export function DefaultScale() { return 1; }
export function RenderFrameDelay() { return 10; }
export function ControllableParameters() {
    return [
        {property:"LightingMode", group:"lighting", label:"Lighting Mode", type:"combobox", values:["Canvas","Forced"], default:"Canvas"},
        {property:"forcedColor", group:"lighting", label:"Forced Color", type:"color", default:"#0055aa"},
        {property:"BackgroundFps", group:"lighting", label:"Background FPS", type:"number", min:1, max:30, step:1, default:20},
        {property:"CanvasWidth", group:"lighting", label:"Canvas Width (layout units)", type:"number", min:16, max:320, step:16, default:DEFAULT_CANVAS_WIDTH}
    ];
}
let socket = null;
let lastSent = -Infinity;
let frameSequence = 0;
let lastProblem = "";
let reportedImage = false;
let waitForCanvasRefresh = false;
function reportProblem(message) {
    if (message !== lastProblem) device.log(message, {toFile:true});
    lastProblem = message;
}
function configureCanvas() {
    const requested = Number(typeof CanvasWidth === "undefined" ? DEFAULT_CANVAS_WIDTH : CanvasWidth);
    sourceWidth = Number.isFinite(requested) ? Math.max(16, Math.min(320, Math.round(requested))) : DEFAULT_CANVAS_WIDTH;
    sourceHeight = Math.round(sourceWidth * 5 / 8);
    const names = [], positions = [];
    for (let y=0; y<3; y++) for (let x=0; x<5; x++) {
        names.push(`Key ${y*5+x+1} Background`);
        positions.push([Math.round((47 + x*97) * sourceWidth / OUTPUT_WIDTH),
                        Math.round((41 + y*97) * sourceHeight / OUTPUT_HEIGHT)]);
    }
    device.setSize(Size());
    device.setControllableLeds(names, positions);
    device.log(`Background bridge 0.2.1: Canvas source ${sourceWidth}x${sourceHeight}, layout ${sourceWidth+1}x${sourceHeight+1}, output ${OUTPUT_WIDTH}x${OUTPUT_HEIGHT}`, {toFile:true});
}
export function onCanvasWidthChanged() {
    if (!socket) return; // Initialize reads the setting before opening the socket.
    configureCanvas();
    // Property callbacks run after the host samples its current Canvas. Wait
    // one render so a larger crop cannot read the previous smaller framebuffer.
    waitForCanvasRefresh = true;
    lastSent = -Infinity;
    reportedImage = false;
}
export function Initialize() {
    if (socket) { socket.close(); socket = null; }
    const controllerId = typeof controller !== "undefined" && controller ? controller.id : "missing";
    const requestedFps = typeof BackgroundFps === "undefined" ? "default20" : String(BackgroundFps);
    device.log(`Background bridge 0.2.1: controller=${controllerId}; BackgroundFps=${requestedFps}; transport=compact-json`, {toFile:true});
    if (controllerId !== BRIDGE_ID) {
        device.log("Background bridge: old or unrelated controller inactive; rediscover the full Canvas controller", {toFile:true});
        return;
    }
    device.setName("Stream Deck MK.2 Background");
    configureCanvas();
    if (typeof device.setFrameRateTarget === "function") device.setFrameRateTarget(60);
    socket = udp.createSocket();
    // Never include a packet or its session token in error logs.
    socket.on("error", () => reportProblem("Background bridge: local UDP error"));
    lastSent = -Infinity;
    frameSequence = Math.max(0, Math.floor(Date.now()));
    lastProblem = "";
    reportedImage = false;
    waitForCanvasRefresh = false;
}
export function Render() {
    if (!socket || BRIDGE_TOKEN === "__LOCAL_SESSION_TOKEN__") return;
    if (waitForCanvasRefresh) { waitForCanvasRefresh = false; return; }
    const now = Date.now();
    const fps = Math.max(1, Math.min(30, Number(typeof BackgroundFps === "undefined" ? 20 : BackgroundFps) || 20));
    if (now - lastSent < 1000/fps) return;
    // Pace failures too: missing/invalid native image data must not spin at 60Hz.
    lastSent = now;
    try {
        if (typeof LightingMode !== "undefined" && LightingMode === "Forced") {
            const hex = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(String(typeof forcedColor === "undefined" ? "" : forcedColor));
            const color = hex ? hex.slice(1).map(v=>parseInt(v,16)) : [0,0,0];
            const colors = Array.from({length:15}, () => color.slice());
            socket.write(JSON.stringify({token:BRIDGE_TOKEN, colors, lease_ms:2000}), "127.0.0.1", BRIDGE_PORT);
            lastProblem = "";
            return;
        }
        if (typeof device.getImageBuffer !== "function") {
            reportProblem("Background bridge: native Canvas image API unavailable");
            return;
        }
        // One native crop/scale/encode for the whole image, no per-pixel JS calls.
        const jpeg = device.getImageBuffer(0, 0, sourceWidth, sourceHeight, {
            outputWidth:OUTPUT_WIDTH, outputHeight:OUTPUT_HEIGHT,
            format:"JPEG", flipV:false, flipH:false
        });
        const length = jpeg && jpeg.length;
        if (!Number.isInteger(length) || length < 4 || length > MAX_JPEG_BYTES ||
            typeof jpeg.slice !== "function" || jpeg[0] !== 255 || jpeg[1] !== 216 ||
            jpeg[length-2] !== 255 || jpeg[length-1] !== 217) {
            reportProblem("Background bridge: native Canvas JPEG is invalid or exceeds 256 KiB");
            return;
        }
        frameSequence = Math.max(frameSequence + 1, Math.floor(now));
        const total = Math.ceil(length / CHUNK_BYTES);
        for (let part=0; part<total; part++) {
            const data = Array.from(jpeg.slice(part*CHUNK_BYTES, (part+1)*CHUNK_BYTES));
            // SignalRGB's object overload pretty-prints nested arrays. Its string
            // overload sends UTF-8 directly, keeping this datagram below 5KiB.
            socket.write(JSON.stringify({token:BRIDGE_TOKEN, kind:"canvas-jpeg", frame:frameSequence,
                part, total, data, lease_ms:2000}), "127.0.0.1", BRIDGE_PORT);
        }
        if (!reportedImage) {
            device.log(`Background bridge: native Canvas JPEG sent (${length} bytes, ${total} parts)`, {toFile:true});
            reportedImage = true;
        }
        lastProblem = "";
    } catch (_) {
        reportProblem("Background bridge: native Canvas capture or local UDP write failed");
    }
}
export function Shutdown() {
    // The compositor restores its normal background when the two-second lease expires.
    if (socket) { socket.close(); socket = null; }
}
export function Validate() { return typeof controller !== "undefined" && !!controller && controller.id === BRIDGE_ID; }
export function DiscoveryService() {
    this.PollInterval = 5000;
    this.localController = {id:BRIDGE_ID, name:"Stream Deck MK.2 Background", ip:"127.0.0.1", port:BRIDGE_PORT};
    this.Refresh = function() {
        if (!service.hasController(this.localController.id)) {
            service.addController(this.localController);
        } else {
            service.updateController(this.localController);
        }
        // Reannounce on service initialization, including a plugin/session reload.
        service.announceController(this.localController);
    };
    this.Initialize = function() { this.Refresh(); };
    this.Update = function() {};
}
