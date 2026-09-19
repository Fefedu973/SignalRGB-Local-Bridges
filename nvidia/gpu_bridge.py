"""Two-zone RTX3080Ti FE bridge. Default is read-only; explicit flags enable control."""
import argparse,json,select,socket,time
from pathlib import Path
from nvapi_backend import NvApi,build_colors,describe,validate_colors

PORT=47687
def receive_packet(sock):
    try:return sock.recvfrom(4097)
    except BlockingIOError:return None
    except OSError as ex:
        # Windows surfaces an earlier unreachable UDP peer on a subsequent read.
        # WSAEMSGSIZE consumes/discards the oversized datagram.
        if (getattr(ex,'winerror',None) or ex.errno) in (10054,10052,10040):return None
        raise

def send_reply(sock,payload,peer):
    try:sock.sendto(payload,peer)
    except OSError as ex:
        if (getattr(ex,'winerror',None) or ex.errno) not in (10054,10052):raise

class Bridge:
    def __init__(self,api,clock=time.monotonic):
        self.api=api;self.clock=clock;self.snapshot=None;self.pending=None;self.current=None
        self.deadline=0;self.last_write=-1e9;self.writes=0;self.restored=None;self.error=None;self.state='idle'

    def status(self):
        return {'state':self.state,'writes':self.writes,'last_colors':self.current,'restored_exact':self.restored,
                'error':self.error,'lease_ms':max(0,round((self.deadline-self.clock())*1000))}

    def handle(self,message):
        if not isinstance(message,dict):raise ValueError('Expected a JSON object')
        op=message.get('op')
        if op=='colors':
            colors=message.get('colors');brightness=message.get('brightness',100)
            validate_colors(colors,brightness)
            if self.error:raise RuntimeError('Release required after previous NVAPI error')
            self.pending=([rgb[:] for rgb in colors],brightness);self.deadline=self.clock()+2
        elif op=='heartbeat':
            if self.error:raise RuntimeError('Release required after previous NVAPI error')
            if self.snapshot is not None or self.pending is not None:self.deadline=self.clock()+2
        elif op=='release':self.release()
        elif op!='status':raise ValueError('Unsupported operation')
        return {'id':message.get('id'),'ok':True,**self.status()}

    def release(self):
        self.pending=None;self.deadline=0
        if self.snapshot is not None:
            saved=self.snapshot
            try:
                self.api.set_control(saved)
                self.restored=self.api.get_control()==saved
                if not self.restored:raise RuntimeError('GPU restoration readback differs')
            except Exception as ex:
                self.error=str(ex);self.state='failed';raise
            self.snapshot=None
        self.current=None;self.error=None;self.state='idle'

    def fail(self,exception):
        self.pending=None;self.deadline=0
        fault=str(exception)
        try:self.release()
        except Exception as restore_error:fault+='; restoration failed: '+str(restore_error)
        self.error=fault;self.state='failed'

    def tick(self):
        now=self.clock()
        if self.deadline and now>=self.deadline:
            self.release();return
        if self.pending is None or now-self.last_write<.1:return
        colors,brightness=self.pending
        if self.current==self.pending:return
        if self.snapshot is None:
            self.snapshot=self.api.get_control();self.restored=None
        self.api.set_control(build_colors(self.snapshot,colors,brightness))
        self.last_write=self.clock();self.current=(colors,brightness);self.writes+=1;self.state='streaming'

def serve(api,seconds=0,stop_file=None):
    bridge=Bridge(api);sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        sock.bind(('127.0.0.1',PORT));sock.setblocking(False);started=time.monotonic()
        print(json.dumps({'listening':'127.0.0.1:'+str(PORT),'gpu':'RTX3080Ti FE','zones':['RGBW','monochrome'],'cadence_ms':100}),flush=True)
        while (not seconds or time.monotonic()-started<seconds) and (stop_file is None or not Path(stop_file).exists()):
            readable,_,_=select.select([sock],[],[],.01)
            if readable:
                # Drain a bounded batch; pending stores only the newest sample.
                for _ in range(32):
                    packet=receive_packet(sock)
                    if packet is None:break
                    raw,peer=packet
                    if peer[0]!='127.0.0.1' or len(raw)>4096:continue
                    identity=None
                    try:
                        message=json.loads(raw);identity=message.get('id') if isinstance(message,dict) else None
                        reply=bridge.handle(message)
                    except Exception as ex:reply={'id':identity,'ok':False,'error':str(ex)}
                    send_reply(sock,json.dumps(reply,separators=(',',':')).encode(),peer)
            try:bridge.tick()
            except Exception as ex:
                bridge.fail(ex)
                print(json.dumps({'error':bridge.error}),flush=True)
    finally:
        try:bridge.release();print(json.dumps({'shutdown':bridge.status()}),flush=True)
        finally:sock.close();api.close()

def demo(api,output):
    snapshot=api.get_control();evidence={'initial':describe(snapshot),'steps':[],'restored_exact':False}
    Path(str(output)+'.snapshot.bin').write_bytes(snapshot)
    try:
        for colors in ([[64,0,0],[64,64,64]],[[0,64,0],[160,160,160]],[[0,0,64],[0,0,0]]):
            target=build_colors(snapshot,colors);api.set_control(target)
            readback=api.get_control();evidence['steps'].append({'requested':colors,'readback_matches':readback==target,'readback':describe(readback)})
            print(json.dumps(evidence['steps'][-1]),flush=True);time.sleep(2)
    finally:
        try:
            api.set_control(snapshot);evidence['restored_exact']=api.get_control()==snapshot
        finally:
            Path(output).write_text(json.dumps(evidence,indent=2),encoding='utf-8');api.close()
        print(json.dumps({'restored_exact':evidence['restored_exact'],'evidence':str(output)}),flush=True)
    if not evidence['restored_exact']:raise RuntimeError('GPU restoration did not match snapshot')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group();group.add_argument('--serve',action='store_true');group.add_argument('--demo',action='store_true')
    parser.add_argument('--allow-write',action='store_true');parser.add_argument('--seconds',type=float,default=0)
    parser.add_argument('--stop-file');parser.add_argument('--output',default='gpu-test.json')
    args=parser.parse_args()
    if (args.serve or args.demo) and not args.allow_write:parser.error('--serve/--demo requires --allow-write')
    if not 0<=args.seconds<=86400:parser.error('--seconds must be 0..86400')
    api=NvApi(allow_write=args.allow_write)
    if args.serve:
        try:serve(api,args.seconds,args.stop_file)
        except KeyboardInterrupt:pass
    elif args.demo:demo(api,args.output)
    else:
        try:print(json.dumps({'read_only':True,'write_called':False,**describe(api.get_control())},indent=2))
        finally:api.close()
if __name__=='__main__':main()
