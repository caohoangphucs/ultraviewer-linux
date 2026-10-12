"""Web Portal for UltraViewer Linux Controller.

Supports dynamic Partner ID & Password from the web interface.
"""
import argparse
import copy
import io
import json
import queue
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from control_session import ControlSession
from screen_decode import RGB555Screen, ZstdDictionaryDecoder
from input_control import mouse_move, mouse_button, mouse_wheel, keyboard


class Viewer:
    def __init__(self, registration, default_partner, dictionary, *, size=(1024, 768), block_size=32, original_certificate_policy=True):
        self.registration = registration
        self.default_partner = default_partner
        self.dictionary = dictionary
        self.size = size
        self.block_size = block_size
        self.policy = original_certificate_policy
        self.lifecycle = threading.Lock()
        self.lock = threading.Lock()
        self.commands = queue.Queue(maxsize=1024)
        self.thread = None
        self.stop = threading.Event()
        self.frame = b''
        self.state = {'state': 'disconnected', 'frames': 0}

    def connect(self, partner_id=None, password=None):
        with self.lifecycle:
            self._connect(partner_id, password)

    def _connect(self, partner_id=None, password=None):
        if self.thread and self.thread.is_alive():
            self.disconnect()
            if self.thread:
                self.thread.join(timeout=2)

        partner_profile = copy.deepcopy(self.default_partner)
        if partner_id:
            # Update partner ID (term index 1)
            terms = list(partner_profile.get('request_terms', []))
            if len(terms) > 1:
                terms[1] = str(partner_id).strip()
                partner_profile['request_terms'] = terms
        if password is not None:
            partner_profile['password'] = str(password).strip()

        self.stop.clear()
        while not self.commands.empty():
            try:
                self.commands.get_nowait()
            except queue.Empty:
                break
        with self.lock:
            self.frame = b''
            self.state = {'state': 'connecting', 'frames': 0, 'error': None}
        self.thread = threading.Thread(target=self.run, args=(partner_profile,), daemon=True)
        self.thread.start()

    def disconnect(self):
        self.stop.set()

    def event(self, value):
        kind = value.get('type')
        if kind == 'move':
            payload = mouse_move(value['x'], value['y'])
        elif kind == 'button':
            payload = mouse_button(value['button'], value['down'])
        elif kind == 'wheel':
            payload = mouse_wheel(value['delta'])
        elif kind == 'key':
            payload = keyboard(value['vk'], value['down'])
        else:
            raise ValueError('unknown input event')
        if self.state['state'] != 'connected':
            raise ValueError('session is not connected')
        self.commands.put_nowait((payload, value))

    def run(self, partner_profile):
        keys = set()
        buttons = set()
        try:
            screen = RGB555Screen(self.size, ZstdDictionaryDecoder(self.dictionary), block_size=self.block_size)
            with ControlSession(original_certificate_policy=self.policy) as session:
                session.connect(self.registration, partner_profile)
                session.relay.timeout = 0.15
                try:
                    while not self.stop.is_set():
                        for _ in range(128):
                            try:
                                payload, event = self.commands.get_nowait()
                            except queue.Empty:
                                break
                            session.send(payload)
                            if event['type'] == 'key':
                                if event['down']:
                                    keys.add(event['vk'])
                                else:
                                    keys.discard(event['vk'])
                            elif event['type'] == 'button':
                                if event['down']:
                                    buttons.add(event['button'])
                                else:
                                    buttons.discard(event['button'])
                        try:
                            kind, fields = session.receive()
                        except TimeoutError:
                            continue
                        if kind == 0:
                            with self.lock:
                                self.state['state'] = 'connected'
                        elif kind == 1:
                            screen.apply(fields)
                            data = io.BytesIO()
                            screen.canvas.save(data, format='PNG')
                            with self.lock:
                                self.frame = data.getvalue()
                                self.state['frames'] += 1
                            session.acknowledge_screen()
                finally:
                    for vk in keys:
                        session.key(vk, False)
                    for button in buttons:
                        session.button(button, False)
        except Exception as exc:
            with self.lock:
                self.state['error'] = str(exc) if str(exc) else type(exc).__name__
        finally:
            with self.lock:
                self.state['state'] = 'disconnected'


def make_server(viewer, port, host='0.0.0.0'):
    html_path = Path(__file__).with_name('viewer.html')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, data, kind='application/json'):
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ('/', '/index.html'):
                content = html_path.read_bytes()
                return self.reply(200, content, 'text/html; charset=utf-8')
            with viewer.lock:
                if self.path == '/status':
                    return self.reply(200, json.dumps(viewer.state).encode())
                if self.path == '/frame.png':
                    return self.reply(200 if viewer.frame else 204, viewer.frame, 'image/png')
            self.reply(404, b'{}')

        def do_POST(self):
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 8192:
                    raise ValueError('payload too large')
                raw = self.rfile.read(length) if length > 0 else b'{}'
                value = json.loads(raw or b'{}')
                if self.path == '/connect':
                    p_id = value.get('id')
                    p_pass = value.get('pass')
                    viewer.connect(p_id, p_pass)
                elif self.path == '/disconnect':
                    viewer.disconnect()
                elif self.path == '/event':
                    viewer.event(value)
                else:
                    return self.reply(404, b'{}')
            except Exception as e:
                return self.reply(400, json.dumps({'error': str(e)}).encode())
            self.reply(200, b'{"ok":true}')

    return ThreadingHTTPServer((host, port), Handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration', type=Path, default=Path(__file__).with_name('linux-controller-private.json'))
    parser.add_argument('--partner', type=Path, default=Path(__file__).with_name('default-partner.json'))
    parser.add_argument('--dictionary', type=Path, default=Path(__file__).with_name('8bit.dat'))
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', type=str, default='0.0.0.0')
    parser.add_argument('--width', type=int, default=1024)
    parser.add_argument('--height', type=int, default=768)
    parser.add_argument('--block-size', type=int, default=32)
    parser.add_argument('--original-certificate-policy', action='store_true', default=True)

    args = parser.parse_args(argv)
    viewer = Viewer(
        json.loads(args.registration.read_text()),
        json.loads(args.partner.read_text()),
        args.dictionary.read_bytes(),
        size=(args.width, args.height),
        block_size=args.block_size,
        original_certificate_policy=args.original_certificate_policy
    )
    server = make_server(viewer, args.port, host=args.host)
    print(f'UltraViewer Web running on http://{args.host}:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        viewer.disconnect()
        if viewer.thread:
            viewer.thread.join(timeout=5)
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
