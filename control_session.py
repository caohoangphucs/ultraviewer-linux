"""Linux control session assembled from the verified registration/relay paths.

Private profiles use the same schema as request_partner_once. This class keeps
registration alive while relaying, provides input send methods and returns raw
split screen updates for a renderer. It does not silently discard image fields.
"""
import hashlib
import secrets
import socket
from registration_transport import RegistrationTransport
from session_transport import SessionTransport
from target_route import decode_target_route
from uv_reference import (build_registration_command, extract_command3_identity,
    connection_request_password_value, build_connection_request_command,
    build_login_with_password, decode_transport_body, decode_byte_array_fields)
from input_control import mouse_move, mouse_button, mouse_wheel, keyboard


class ControlSession:
    def __init__(self, *, timeout=8, original_certificate_policy=False):
        self.timeout = timeout
        self.original_certificate_policy = original_certificate_policy
        self.registration = None
        self.relay = None
        self.route = None
        self.login_acknowledged = False

    def connect(self, registration, partner):
        self.close()
        codec = registration['ansi_codec']
        terms = list(partner['request_terms'])
        if len(terms) != 17:
            raise ValueError('partner request needs seventeen terms')
        try:
            self.registration = RegistrationTransport(timeout=self.timeout,
                original_certificate_policy=self.original_certificate_policy)
            self.registration.connect()
            self.registration.send_command(build_registration_command(registration['terms'],ansi_codec=codec))
            identity = extract_command3_identity(self.registration.receive_mode1_payload(),ansi_codec=codec)
            terms[2] = connection_request_password_value(partner['password'],partner['password_type'],ansi_codec=codec)
            terms[6] = str(identity.client_id)
            terms[7] = hashlib.md5((terms[6]+registration['terms'][2]).encode(codec)).hexdigest()
            self.registration.send_command(build_connection_request_command(terms,ansi_codec=codec))
            for _ in range(4):
                response = self.registration.receive_mode1_payload()
                if response.startswith(b'8:'):
                    parts = response.decode(codec, errors='ignore').split(':')
                    if len(parts) >= 2 and parts[1] != '1':
                        status = parts[1]
                        if status == '2':
                            raise ValueError('Sai mật khẩu (Wrong Password)')
                        elif status == '11':
                            raise ValueError('Đối tác không online hoặc ID không tồn tại')
                        elif status == '99':
                            raise ValueError('Không thể kết nối tới đối tác (Status 99)')
                        else:
                            raise ValueError(f'Lỗi kết nối từ máy chủ (Mã: {status})')
                    self.route = decode_target_route(response,ansi_codec=codec)
                    break
            if self.route is None:
                raise ValueError('Không nhận được thông tin định tuyến từ đối tác')
            self.relay = SessionTransport(timeout=self.timeout,
                original_certificate_policy=self.original_certificate_policy)
            self.relay.connect(self.route.tcp_server_ip,443,http_hostname=self.route.tcp_server_hostname)
            digits = lambda count: ''.join(str(secrets.randbelow(10)) for _ in range(count))
            fields = ['','','1280','720','30','15','15','0','0',str(identity.client_id),
                socket.gethostname(),'0','','',digits(16),'2','80','0','0',
                self.route.partner_secret_token or '', '6.6.133','0']
            payload = build_login_with_password(fields,password=partner['password'],
                password_type=partner['password_type'],salt=digits(8),ansi_codec=codec)
            self.relay.send_relay(payload,target_ip=self.route.public_ip,
                target_port=self.route.tcp_port,unicode_bytes=True)
        except BaseException:
            self.close()
            raise

    def send(self, payload):
        if self.relay is None or self.route is None:
            raise RuntimeError('session is closed')
        self.relay.send_relay(payload,target_ip=self.route.public_ip,
            target_port=self.route.tcp_port,unicode_bytes=False)

    def receive(self):
        if self.relay is None:
            raise RuntimeError('session is closed')
        packet = decode_transport_body(self.relay.receive_body())
        if not packet or packet['kind'] != 'relay':
            raise ValueError('unexpected session transport packet')
        fields = decode_byte_array_fields(packet['data'])
        if not fields or not fields[0]:
            raise ValueError('empty session packet')
        kind = fields[0][0]
        if kind == 0:
            self.login_acknowledged = True
            self.send(b'17')
        elif kind == 3 and len(fields)>1 and len(fields[1]) == 4:
            self.send(('|||4'+str(int.from_bytes(fields[1],'little',signed=True))).encode('ascii'))
        return kind, fields

    def acknowledge_screen(self):
        # Renderer calls this only after it accepts the screen update.
        self.send(b'18')

    def move(self, x, y):self.send(mouse_move(x,y))
    def button(self, button, down):self.send(mouse_button(button,down))
    def wheel(self, delta):self.send(mouse_wheel(delta))
    def key(self, vk, down, *, system=False):self.send(keyboard(vk,down,system=system))

    def close(self):
        try:
            if self.relay is not None:self.relay.close()
        finally:
            self.relay = None
            try:
                if self.registration is not None:self.registration.close()
            finally:
                self.registration = None
                self.route = None
                self.login_acknowledged = False

    def __enter__(self):return self
    def __exit__(self, *args):self.close()
