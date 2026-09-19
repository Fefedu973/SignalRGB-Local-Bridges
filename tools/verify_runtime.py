"""Read-only end-to-end bridge observations; no lighting commands are sent."""
import argparse
import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'streamdeck/bridge'))
from play_background import BackgroundClient


def udp_status(port, identifier):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
        sock.settimeout(3)
        sock.sendto(json.dumps({'id': identifier, 'op': 'status'}).encode(), ('127.0.0.1', port))
        reply = json.loads(sock.recvfrom(16384)[0])
        if reply.get('id') != identifier or reply.get('ok') is not True:
            raise RuntimeError(f'Invalid status response on port {port}')
        return reply


def sample(index, stream):
    bulbs = udp_status(47684, 90000 + index)['devices']
    gpu = udp_status(47687, 91000 + index)
    deck = stream.request('/health')
    return {
        'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'govee': [{k: b[k] for k in ('state', 'ready', 'frame_writes', 'error', 'restore_error')}
                  for b in bulbs],
        'nvidia': {k: gpu[k] for k in ('state', 'writes', 'error', 'lease_ms')},
        'streamdeck': {
            'ready': deck['ready'], 'errors': deck['status']['errors'],
            'painted_keys': len(deck['status']['paintedKeys']),
            'canvas_frames': deck['canvas']['frames'],
            'rejected': deck['canvas']['rejected'],
            'ack_fps_5s': deck['status']['pacing']['ackFps5s'],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error('seconds must be between 1 and 120')
    output = Path(args.output)
    if output.exists():
        raise SystemExit('Preserve existing verification report; choose a new output')
    session = ROOT / 'local-installation/streamdeck/api-session.json'
    stream = BackgroundClient(session)
    samples = []
    started = time.monotonic()
    try:
        while True:
            samples.append(sample(len(samples), stream))
            if time.monotonic() - started >= args.seconds:
                break
            time.sleep(min(5, args.seconds - (time.monotonic() - started)))
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'seconds': time.monotonic() - started, 'samples': samples}, indent=2), encoding='utf-8')
    last = samples[-1]
    assert all(b['ready'] and b['error'] is None for b in last['govee']), 'Govee not ready'
    assert last['nvidia']['state'] == 'streaming' and last['nvidia']['error'] is None, 'NVIDIA not streaming'
    assert last['streamdeck']['ready'] and last['streamdeck']['errors'] == 0 and last['streamdeck']['painted_keys'] == 15, 'Stream Deck not ready'
    print(json.dumps({'samples': len(samples), 'last': last, 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
