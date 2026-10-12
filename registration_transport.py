"""Recovered Linux registration transport; request fields still under investigation.

No registration request is generated automatically. The caller supplies the
recovered plaintext command. See E137, E142 and E143 in the investigation report.
"""
import socket
import ssl
import struct
import time
from uv_reference import (
    http_service_preface, encrypt_registration_bytes, encode_transport_frame,
    extract_command3_identity,
)

DEFAULT_HOST = "functions3.ultraviewer.net"
TLS_TARGET_HOST = "ultraviewer"


class RegistrationTransport:
    def __init__(self, *, timeout=8.0, max_frame=1024*1024,
                 original_certificate_policy=False):
        if timeout <= 0 or max_frame <= 0:
            raise ValueError("positive limits required")
        self.timeout = timeout
        self.max_frame = max_frame
        self.original_certificate_policy = original_certificate_policy
        self.channel = None
        self.buffer = bytearray()
        self.response_header = b""

    def connect(self, host=DEFAULT_HOST, port=443):
        if self.channel is not None:
            raise RuntimeError("already connected")
        context = ssl.create_default_context()
        if self.original_certificate_policy:
            # Original RC40 callback returns True for every certificate.
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
        raw = socket.create_connection((host, port), timeout=self.timeout)
        try:
            self.channel = context.wrap_socket(raw, server_hostname=TLS_TARGET_HOST)
            self.channel.sendall(http_service_preface(host))
            deadline = time.monotonic() + self.timeout
            while b"\r\n\r\n" not in self.buffer:
                if len(self.buffer) >= 16384:
                    raise ValueError("HTTP header exceeds limit")
                self._receive(deadline)
            end = self.buffer.index(b"\r\n\r\n") + 4
            self.response_header = bytes(self.buffer[:end])
            del self.buffer[:end]
            # Original just strips the header; reconstructed client checks status.
            if self.response_header.split(b"\r\n", 1)[0] != b"HTTP/1.1 200 OK":
                raise ValueError("registration tunnel did not return HTTP 200")
            return self.response_header
        except BaseException:
            raw.close()
            self.close()
            raise

    def _receive(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("transport deadline")
        self.channel.settimeout(remaining)
        data = self.channel.recv(4096)
        if not data:
            raise EOFError("server closed transport")
        self.buffer.extend(data)

    def send_command(self, plaintext: bytes):
        """Encrypt caller-supplied ANSI command and send VTCP mode1 frame with registration flag0.

        This does not validate/reconstruct the command3 registration schema.
        """
        if self.channel is None:
            raise RuntimeError("not connected")
        encrypted = encrypt_registration_bytes(plaintext)
        # InitMyPassword passes True as Send argument6 via native wrapper.
        # Argument5=False becomes byte0 at body offset1 (E151).
        body = b"\x01\x00" + encrypted
        if len(body) > self.max_frame:
            raise ValueError("outbound frame exceeds limit")
        self.channel.sendall(encode_transport_frame(body))

    def receive_body(self):
        if self.channel is None:
            raise RuntimeError("not connected")
        deadline = time.monotonic() + self.timeout
        while len(self.buffer) < 4:
            self._receive(deadline)
        size = struct.unpack_from("<I", self.buffer)[0]
        if not 1 <= size <= self.max_frame:
            raise ValueError("invalid inbound frame length")
        while len(self.buffer) < 4 + size:
            self._receive(deadline)
        body = bytes(self.buffer[4:4+size])
        del self.buffer[:4+size]
        return body

    def receive_mode1_payload(self):
        body = self.receive_body()
        if body[0] != 1:
            raise ValueError("expected mode1 frame")
        return body[1:]

    def receive_identity(self, *, ansi_codec):
        return extract_command3_identity(self.receive_mode1_payload(),
                                         ansi_codec=ansi_codec)

    def close(self):
        if self.channel is not None:
            self.channel.close()
            self.channel = None
        self.buffer.clear()
