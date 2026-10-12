"""Local browser viewer for the recovered Linux UltraViewer controller.

Run with private registration/partner JSON profiles and original 8bit.dat.
The server binds loopback only. Open the printed URL, then click Connect.
"""
import argparse
import io
import json
import queue
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from control_session import ControlSession
from screen_decode import RGB555Screen, ZstdDictionaryDecoder
from input_control import mouse_move,mouse_button,mouse_wheel,keyboard


class Viewer:
    def __init__(self,registration,partner,dictionary,*,size=(1024,768),block_size=32,original_certificate_policy=False):
        self.registration=registration;self.partner=partner;self.dictionary=dictionary
        self.size=size;self.block_size=block_size;self.policy=original_certificate_policy
        self.lifecycle=threading.Lock();self.lock=threading.Lock();self.commands=queue.Queue(maxsize=1024)
        self.thread=None;self.stop=threading.Event();self.frame=b''
        self.state={'state':'disconnected','frames':0}

    def connect(self):
        with self.lifecycle:self._connect()

    def _connect(self):
        if self.thread and self.thread.is_alive():return
        self.stop.clear()
        while not self.commands.empty():self.commands.get_nowait()
        with self.lock:self.frame=b'';self.state={'state':'connecting','frames':0}
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def disconnect(self):self.stop.set()

    def event(self,value):
        kind=value.get('type')
        if kind=='move':payload=mouse_move(value['x'],value['y'])
        elif kind=='button':payload=mouse_button(value['button'],value['down'])
        elif kind=='wheel':payload=mouse_wheel(value['delta'])
        elif kind=='key':payload=keyboard(value['vk'],value['down'])
        else:raise ValueError('unknown input event')
        if self.state['state']!='connected':raise ValueError('session is not connected')
        self.commands.put_nowait((payload,value))

    def run(self):
        keys=set();buttons=set()
        try:
            screen=RGB555Screen(self.size,ZstdDictionaryDecoder(self.dictionary),block_size=self.block_size)
            with ControlSession(original_certificate_policy=self.policy) as session:
                session.connect(self.registration,self.partner)
                session.relay.timeout=.15
                try:
                    while not self.stop.is_set():
                        for _ in range(128):
                            try:payload,event=self.commands.get_nowait()
                            except queue.Empty:break
                            session.send(payload)
                            if event['type']=='key':
                                if event['down']:keys.add(event['vk'])
                                else:keys.discard(event['vk'])
                            elif event['type']=='button':
                                if event['down']:buttons.add(event['button'])
                                else:buttons.discard(event['button'])
                        try:kind,fields=session.receive()
                        except TimeoutError:continue
                        if kind==0:
                            with self.lock:self.state['state']='connected'
                        elif kind==1:
                            screen.apply(fields)
                            data=io.BytesIO();screen.canvas.save(data,format='PNG')
                            with self.lock:self.frame=data.getvalue();self.state['frames']+=1
                            session.acknowledge_screen()
                finally:
                    for vk in keys:session.key(vk,False)
                    for button in buttons:session.button(button,False)
        except Exception as exc:
            with self.lock:self.state['error']=type(exc).__name__
        finally:
            with self.lock:self.state['state']='disconnected'


def make_server(viewer,port):
    token=secrets.token_hex(24)
    html=Path(__file__).with_name('viewer.html').read_text().replace('__TOKEN__',token).encode()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,code,data,kind='application/json'):
            self.send_response(code);self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def valid_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        def do_GET(self):
            if not self.valid_host():return self.reply(403,b'{}')
            if self.path=='/':return self.reply(200,html,'text/html; charset=utf-8')
            with viewer.lock:
                if self.path=='/status':return self.reply(200,json.dumps(viewer.state).encode())
                if self.path=='/frame.png':return self.reply(200 if viewer.frame else 204,viewer.frame,'image/png')
            self.reply(404,b'{}')
        def do_POST(self):
            if not self.valid_host() or not secrets.compare_digest(self.headers.get('X-Viewer-Token',''),token):return self.reply(403,b'{}')
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):return self.reply(403,b'{}')
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<=length<=4096:raise ValueError()
                value=json.loads(self.rfile.read(length) or b'{}')
                if self.path=='/connect':viewer.connect()
                elif self.path=='/disconnect':viewer.disconnect()
                elif self.path=='/event':viewer.event(value)
                else:return self.reply(404,b'{}')
            except (ValueError,KeyError,TypeError,queue.Full):return self.reply(400,b'{}')
            self.reply(200,b'{}')
    return ThreadingHTTPServer(('127.0.0.1',port),Handler)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registration',type=Path);parser.add_argument('partner',type=Path)
    parser.add_argument('--dictionary',type=Path,required=True);parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--width',type=int,default=1024);parser.add_argument('--height',type=int,default=768)
    parser.add_argument('--block-size',type=int,default=32)
    parser.add_argument('--original-certificate-policy',action='store_true')
    argv=sys.argv[1:] if argv is None else argv
    if not argv or argv==['help']:parser.print_help();return 0
    args=parser.parse_args(argv)
    if not 0<args.width<=8192 or not 0<args.height<=8192:parser.error('invalid desktop dimensions')
    viewer=Viewer(json.loads(args.registration.read_text()),json.loads(args.partner.read_text()),
        args.dictionary.read_bytes(),size=(args.width,args.height),block_size=args.block_size,
        original_certificate_policy=args.original_certificate_policy)
    server=make_server(viewer,args.port)
    print(f'Viewer: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        viewer.disconnect()
        if viewer.thread:viewer.thread.join(timeout=10)
        server.server_close()
    return 0


if __name__=='__main__':raise SystemExit(main())
