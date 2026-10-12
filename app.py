#!/usr/bin/env python3
"""UltraViewer Linux Standalone Application.

Runs internal controller server and displays native GUI window.
"""
import argparse
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

from server import Viewer, make_server

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def main(argv=None):
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="UltraViewer Linux App")
    parser.add_argument('--registration', type=Path, default=base_dir / 'linux-controller-private.json')
    parser.add_argument('--partner', type=Path, default=base_dir / 'default-partner.json')
    parser.add_argument('--dictionary', type=Path, default=base_dir / '8bit.dat')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-gui', action='store_true', help="Run server only without native window")
    args = parser.parse_args(argv)

    port = args.port if args.port > 0 else find_free_port()

    viewer = Viewer(
        json.loads(args.registration.read_text()),
        json.loads(args.partner.read_text()),
        args.dictionary.read_bytes(),
        size=(1024, 768),
        block_size=32,
        original_certificate_policy=True
    )

    server = make_server(viewer, port, host='127.0.0.1')
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"UltraViewer Controller core listening on http://127.0.0.1:{port}", flush=True)

    if not args.no_gui and (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        try:
            time.sleep(0.1)
            import app_window
            app_window.main(port)
        except Exception as e:
            print(f"GUI launch failed: {e}. Falling back to console mode.", file=sys.stderr)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
    else:
        print(f"Mở ứng dụng tại http://127.0.0.1:{port} hoặc trên cửa sổ hiển thị.", flush=True)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    viewer.disconnect()
    server.shutdown()

if __name__ == '__main__':
    main()
