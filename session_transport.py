"""Recovered TCP relay transport; Windows login is the caller's responsibility."""
import socket
import ssl
import time
from registration_transport import RegistrationTransport, TLS_TARGET_HOST
from uv_reference import http_service_preface, encode_relay_frame


class SessionTransport(RegistrationTransport):
    def connect(self, host, port=443, *, http_hostname="", use_ssl=True):
        if self.channel is not None:
            raise RuntimeError("already connected")
        raw = socket.create_connection((host, port), timeout=self.timeout)
        self.channel = raw
        try:
            if use_ssl:
                context = ssl.create_default_context()
                if self.original_certificate_policy:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                self.channel = context.wrap_socket(raw, server_hostname=TLS_TARGET_HOST)
            if http_hostname:
                self.channel.sendall(http_service_preface(http_hostname))
                deadline = time.monotonic() + self.timeout
                while b"\r\n\r\n" not in self.buffer:
                    if len(self.buffer) >= 16384:
                        raise ValueError("HTTP header exceeds limit")
                    self._receive(deadline)
                end = self.buffer.index(b"\r\n\r\n") + 4
                self.response_header = bytes(self.buffer[:end])
                del self.buffer[:end]
                if not self.response_header.startswith(b"HTTP/1.1 200 "):
                    raise ValueError("session tunnel did not return HTTP 200")
            return self.response_header
        except BaseException:
            raw.close()
            self.close()
            raise

    def send_relay(self, payload, *, target_ip, target_port, unicode_bytes):
        if self.channel is None:
            raise RuntimeError("not connected")
        frame = encode_relay_frame(payload, ipv4=target_ip, port=target_port,
                                   flag=1 if unicode_bytes else 0)
        if len(frame) - 4 > self.max_frame:
            raise ValueError("outbound frame exceeds limit")
        self.channel.sendall(frame)
