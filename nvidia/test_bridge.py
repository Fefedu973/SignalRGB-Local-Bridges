"""Offline tests; no DLL is loaded and no GPU/network operation is performed."""
import unittest,socket,time
from nvapi_backend import Control,VERSION,build_colors,checked_control,describe
from gpu_bridge import Bridge,receive_packet,send_reply

def snapshot():
    value=Control();value.version=VERSION;value.count=2
    value.zones[0].type=3;value.zones[1].type=4
    value.zones[0].data[:5]=[12,34,56,0,70];value.zones[1].data[0]=33
    value.reserved[12]=77;value.zones[0].reserved[45]=89
    return bytes(value)
class FakeApi:
    def __init__(self):self.raw=snapshot();self.writes=[]
    def get_control(self):return self.raw
    def set_control(self,raw):self.writes.append(raw);self.raw=raw
class Tests(unittest.TestCase):
    def test_binary_layout_and_reserved_preservation(self):
        raw=snapshot();new=build_colors(raw,[[50,0,0],[255,255,255]])
        control=checked_control(new)
        self.assertEqual(len(new),6476);self.assertEqual(VERSION,72012)
        self.assertEqual(control.reserved[12],77);self.assertEqual(control.zones[0].reserved[45],89)
        self.assertEqual(list(control.zones[0].data[:5]),[50,0,0,0,100]);self.assertEqual(control.zones[1].data[0],100)
    def test_gray_rgbw_and_monochrome_intensity(self):
        c=checked_control(build_colors(snapshot(),[[120,124,122],[128,0,0]],50))
        self.assertEqual(list(c.zones[0].data[:5]),[0,0,0,122,50]);self.assertEqual(c.zones[1].data[0],25)
    def test_rejects_persistent_flags_and_unexpected_zones(self):
        value=Control.from_buffer_copy(snapshot());value.flags=1
        with self.assertRaises(ValueError):build_colors(bytes(value),[[1,2,3],[4,5,6]])
        value.flags=0;value.zones[1].type=3
        with self.assertRaises(ValueError):checked_control(bytes(value))
    def test_latest_color_coalescing_100ms_and_exact_lease_restore(self):
        api=FakeApi();clock=[0];bridge=Bridge(api,lambda:clock[0]);original=api.raw
        for i in range(100):bridge.handle({'op':'colors','colors':[[i,0,0],[i,i,i]]})
        bridge.tick();self.assertEqual(len(api.writes),1);self.assertEqual(describe(api.raw)['zones'][0]['rgbw_brightness'][0],99)
        clock[0]=.05;bridge.handle({'op':'colors','colors':[[1,2,3],[0,0,0]]});bridge.tick();self.assertEqual(len(api.writes),1)
        clock[0]=.11;bridge.tick();self.assertEqual(len(api.writes),2)
        clock[0]=2.06;bridge.tick();self.assertEqual(api.raw,original);self.assertTrue(bridge.restored)
    def test_static_heartbeat_and_explicit_shutdown(self):
        api=FakeApi();clock=[0];bridge=Bridge(api,lambda:clock[0]);original=api.raw
        bridge.handle({'op':'colors','colors':[[20,40,60],[128,128,128]]});bridge.tick()
        for now in (.5,1,1.5,2,2.5):clock[0]=now;bridge.handle({'op':'heartbeat'});bridge.tick()
        self.assertEqual(len(api.writes),1);reply=bridge.handle({'id':12,'op':'release'})
        self.assertEqual(reply['id'],12);self.assertEqual(api.raw,original);self.assertTrue(reply['restored_exact'])
    def test_malformed_input_cannot_mutate_pending_state(self):
        api=FakeApi();bridge=Bridge(api)
        for message in ({'op':'colors','colors':[[1,2,3]]},{'op':'colors','colors':[[256,2,3],[1,2,3]]},{'op':'colors','colors':[[True,2,3],[1,2,3]]},{'op':'colors','colors':[[1,2,3],[1,2,3]],'brightness':101}):
            with self.assertRaises(ValueError):bridge.handle(message)
        self.assertIsNone(bridge.pending);self.assertFalse(api.writes)
    def test_restoration_mismatch_is_reported(self):
        api=FakeApi();bridge=Bridge(api);bridge.handle({'op':'colors','colors':[[30,0,0],[0,0,0]]});bridge.tick()
        api.set_control=lambda raw:None
        with self.assertRaises(RuntimeError):bridge.release()
        self.assertEqual(bridge.state,'failed');self.assertFalse(bridge.restored);self.assertIsNotNone(bridge.snapshot)
    def test_partial_write_failure_restores_immediately_and_rejects_heartbeat(self):
        api=FakeApi();bridge=Bridge(api);original=api.raw
        bridge.handle({'op':'colors','colors':[[30,0,0],[80,0,0]]})
        real_set=api.set_control
        def partial_failure(raw):
            real_set(raw)
            if raw!=original:raise RuntimeError('synthetic partial write')
        api.set_control=partial_failure
        try:bridge.tick()
        except RuntimeError as ex:bridge.fail(ex)
        self.assertEqual(api.raw,original);self.assertTrue(bridge.restored);self.assertEqual(bridge.state,'failed')
        with self.assertRaises(RuntimeError):bridge.handle({'op':'heartbeat'})
        self.assertEqual(bridge.deadline,0)
        bridge.handle({'op':'release'});self.assertIsNone(bridge.error)
    def test_windows_icmp_errors_are_bounded_and_other_errors_propagate(self):
        class BrokenSocket:
            def __init__(self,code):self.code=code
            def recvfrom(self,size):raise OSError(self.code,'synthetic network error')
            def sendto(self,data,peer):raise OSError(self.code,'synthetic network error')
        for code in (10054,10052,10040):self.assertIsNone(receive_packet(BrokenSocket(code)))
        for code in (10054,10052):send_reply(BrokenSocket(code),b'ack',('127.0.0.1',123))
        with self.assertRaises(OSError):receive_packet(BrokenSocket(10038))
        with self.assertRaises(OSError):send_reply(BrokenSocket(10038),b'ack',('127.0.0.1',123))
    def test_real_loopback_closed_client_before_ack_then_live_client(self):
        # Real Windows UDP sockets, ephemeral loopback ports; no GPU or DLL.
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as server:
            server.bind(('127.0.0.1',0));server.settimeout(1)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as closed_client:
                closed_client.sendto(b'release',server.getsockname())
                raw,peer=server.recvfrom(1024)
            self.assertEqual(raw,b'release')
            send_reply(server,b'ack',peer) # Peer already closed: provokes Windows ICMP.
            time.sleep(.05)
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as live:
                live.bind(('127.0.0.1',0));live.settimeout(1)
                live.sendto(b'status',server.getsockname())
                packet=None
                for _ in range(3):
                    packet=receive_packet(server)
                    if packet is not None:break
                self.assertIsNotNone(packet);self.assertEqual(packet[0],b'status')
                send_reply(server,b'alive',packet[1]);self.assertEqual(live.recvfrom(100)[0],b'alive')
if __name__=='__main__':unittest.main(verbosity=2)
