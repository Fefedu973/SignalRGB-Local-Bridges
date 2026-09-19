"""NVAPI illumination only. PCI allowlist + volatile state; no third-party driver."""
import ctypes as C
import os
from pathlib import Path
import time

U32=C.c_uint32;U8=C.c_ubyte
ALLOWED=(0x10de,0x2208,0x10de,0x1535)
class ZoneControl(C.Structure):
    _fields_=[('type',U32),('mode',U32),('data',U8*128),('reserved',U8*64)]
class Control(C.Structure):
    _fields_=[('version',U32),('flags',U32),('count',U32),('reserved',U8*64),('zones',ZoneControl*32)]
class ZoneInfo(C.Structure):
    _fields_=[('type',U32),('device',U8),('provider',U8),('location',U32),('data',U8*64),('reserved',U8*64)]
class Info(C.Structure):
    _fields_=[('version',U32),('count',U32),('reserved',U8*64),('zones',ZoneInfo*32)]

# Explicit-width fields, native handle width. No packed pointer assumptions.
assert C.sizeof(U32)==4 and C.sizeof(Control)==6476 and Control.zones.offset==76
assert C.sizeof(ZoneControl)==200 and C.sizeof(Info)==4552 and C.sizeof(ZoneInfo)==140
VERSION=C.sizeof(Control)|(1<<16)

def checked_control(raw):
    if not isinstance(raw,bytes) or len(raw)!=C.sizeof(Control):raise ValueError('Invalid NVAPI control buffer size')
    control=Control.from_buffer_copy(raw)
    if control.version!=VERSION or control.flags!=0:raise ValueError('Only current volatile NVAPI state is allowed')
    if control.count!=2 or [z.type for z in control.zones[:2]]!=[3,4]:raise ValueError('Unexpected GPU zone capabilities')
    return control

def validate_colors(colors,brightness):
    if not isinstance(colors,list) or len(colors)!=2:raise ValueError('Exactly two RGB samples required')
    if any(not isinstance(rgb,list) or len(rgb)!=3 or any(type(v) is not int or not 0<=v<=255 for v in rgb) for rgb in colors):
        raise ValueError('RGB values must be integer bytes')
    if type(brightness) is not int or not 0<=brightness<=100:raise ValueError('Brightness must be an integer percentage')

def build_colors(raw,colors,brightness=100):
    validate_colors(colors,brightness);control=checked_control(raw)
    red,green,blue=colors[0];white=0
    # FE RGBW conversion follows the observed OpenRGB path for nearly gray RGB.
    if max(red,green,blue)-min(red,green,blue)<=10:
        white=(max(red,green,blue)+min(red,green,blue))//2;red=green=blue=0
    control.zones[0].mode=0
    control.zones[0].data[:5]=[red,green,blue,white,brightness]
    # The top/logo zone is physically SINGLE_COLOR. Canvas intensity only.
    control.zones[1].mode=0
    control.zones[1].data[0]=round(max(colors[1])*brightness/255)
    return bytes(control)

def describe(raw):
    c=checked_control(raw)
    return {'version':c.version,'buffer_bytes':C.sizeof(Control),'volatile_flags':c.flags,
            'zones':[{'index':0,'type':'RGBW','mode':c.zones[0].mode,'rgbw_brightness':list(c.zones[0].data[:5])},
                     {'index':1,'type':'SINGLE_COLOR','mode':c.zones[1].mode,'brightness':c.zones[1].data[0]}]}

class NvApi:
    def __init__(self,allow_write=False):
        if os.name!='nt':raise RuntimeError('Windows NVIDIA driver required')
        self.allow_write=allow_write;self.last_call=-1e9;self.closed=False
        name='nvapi64.dll' if C.sizeof(C.c_void_p)==8 else 'nvapi.dll'
        self.dll=C.CDLL(str(Path(os.environ['SystemRoot'])/'System32'/name))
        self.query=self.dll.nvapi_QueryInterface;self.query.restype=C.c_void_p;self.query.argtypes=[U32]
        self.functions={};self._check(self.function(0x0150e828)(),'Initialize')
        handles=(C.c_void_p*64)();count=U32()
        self._check(self.function(0xe5ac921f,C.POINTER(C.c_void_p),C.POINTER(U32))(handles,C.byref(count)),'EnumPhysicalGPUs')
        if count.value>64:raise RuntimeError('Invalid GPU count')
        matches=[]
        for i in range(count.value):
            values=[U32() for _ in range(4)]
            self._check(self.function(0x2ddfb66e,C.c_void_p,*([C.POINTER(U32)]*4))(handles[i],*(C.byref(v) for v in values)),'PCIIdentifiers')
            combined,subsystem,revision,extended=[v.value for v in values]
            if (combined&65535,combined>>16,subsystem&65535,subsystem>>16)==ALLOWED:matches.append(handles[i])
        if len(matches)!=1:raise RuntimeError('Expected exactly one allowlisted RTX3080Ti FE (10DE:2208/10DE:1535)')
        self.handle=matches[0]
        self.initial_info=describe(self.get_control())

    def function(self,index,*args):
        if index not in self.functions:
            address=self.query(index)
            if not address:raise RuntimeError('NVAPI interface unavailable: '+hex(index))
            # NVAPI uses cdecl; CFUNCTYPE also handles the unified Windows x64 ABI.
            self.functions[index]=C.CFUNCTYPE(C.c_int32,*args)(address)
        return self.functions[index]

    @staticmethod
    def _check(status,label):
        if status:raise RuntimeError(label+' failed with NVAPI status '+str(status))

    def _pace(self):
        time.sleep(max(0,.03-(time.monotonic()-self.last_call)))
        self.last_call=time.monotonic()

    def get_control(self):
        self._pace();control=Control();control.version=VERSION;control.flags=0
        self._check(self.function(0x3dbf5764,C.c_void_p,C.POINTER(Control))(self.handle,C.byref(control)),'IllumZonesGetControl')
        raw=bytes(control);checked_control(raw);return raw

    def set_control(self,raw):
        if not self.allow_write:raise PermissionError('GPU writes require explicit --allow-write')
        control=checked_control(raw);self._pace()
        self._check(self.function(0x197d065e,C.c_void_p,C.POINTER(Control))(self.handle,C.byref(control)),'IllumZonesSetControl')

    def close(self):
        if not self.closed:
            self._check(self.function(0xd22bdd7e)(),'Unload');self.closed=True
