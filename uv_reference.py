"""Portable models recovered from UltraViewer 6.6.133. See README.md.
Only valid, non-overlapping buffers are modeled; malformed input raises ValueError.
"""
from dataclasses import dataclass
import struct


def dib_stride(width: int, bits_per_pixel: int) -> int:
    if width < 0 or bits_per_pixel <= 0:
        raise ValueError('invalid dimensions')
    return ((width * bits_per_pixel + 31) & -32) // 8


def _rows(src, dst, source, destination, source_step, destination_step, size, height):
    if size < 0 or height < 0:
        raise ValueError('negative copy dimensions')
    pairs = [(source + i * source_step, destination + i * destination_step)
             for i in range(height)]
    if any(s < 0 or d < 0 or s + size > len(src) or d + size > len(dst)
           for s, d in pairs):
        raise ValueError('copy exceeds buffer')
    for s, d in pairs:
        dst[d:d + size] = src[s:s + size]
    return size * height


def extract_tile(src, bpp, stride, x, y, width, height, full_height):
    """uvc ordinal 15 (0x10001920): bottom-up DIB to packed logical rows."""
    if width < 0 or height < 0 or bpp <= 0:
        raise ValueError('invalid dimensions')
    result = bytearray(width * height * bpp)
    _rows(src, result, (full_height-y-1)*stride+x*bpp, 0,
          -stride, width*bpp, width*bpp, height)
    return bytes(result)


def pack_atlas(src, dst, bpp, dest_stride, src_stride, src_x, src_y,
               dest_x, dest_y, width, height, src_height):
    """uvc ordinal 59 (0x10001890): bottom-up source to ascending atlas rows."""
    return _rows(src, dst, (src_height-src_y-1)*src_stride+bpp*src_x,
                 dest_stride*dest_y+bpp*dest_x, -src_stride, dest_stride,
                 bpp*width, height)


def restore_atlas(src, dst, bpp, dest_stride, src_stride, src_x, src_y,
                  dest_x, dest_y, width, height, dest_height):
    """uvc ordinal 60 (0x10001800): ascending atlas rows to bottom-up DIB."""
    return _rows(src, dst, src_stride*src_y+bpp*src_x,
                 (dest_height-dest_y-1)*dest_stride+bpp*dest_x,
                 src_stride, -dest_stride, bpp*width, height)


@dataclass(frozen=True)
class CachedItem:
    width: int
    height: int
    rect_hash: int
    data: bytes

    def serialize(self):
        return struct.pack('<iiii', self.width, self.height,
                           self.rect_hash, len(self.data)) + self.data

    @classmethod
    def parse(cls, payload):
        if len(payload) < 16:
            raise ValueError('truncated cache header')
        width, height, hash_value, size = struct.unpack_from('<iiii', payload)
        if size < 0 or len(payload) != 16 + size:
            raise ValueError('invalid cache payload length')
        return cls(width, height, hash_value, bytes(payload[16:]))


def export_cache(items):
    """Ordered iterable of (Int32 key, CachedItem), recovered method 0x060011e6."""
    out = bytearray()
    for key, item in items:
        payload = item.serialize()
        out += struct.pack('<ii', key, len(payload)) + payload
    return bytes(out)


def import_cache(data):
    """Recovered 0x060011e7 format with stricter validation and atomic return."""
    result = {}
    offset = 0
    while offset < len(data):
        if len(data)-offset < 8:
            raise ValueError('truncated outer header')
        key, size = struct.unpack_from('<ii', data, offset)
        offset += 8
        if size < 0 or size > len(data)-offset or key in result:
            raise ValueError('invalid size or duplicate key')
        result[key] = CachedItem.parse(data[offset:offset+size])
        offset += size
    return result


def atlas_layout(rectangles, block_size, atlas_height):
    """Yield (screen_x,screen_y,w,h,atlas_x,atlas_y) in observed tile order.

    Rectangles are already decoded (x,y,width,height). Selection/transport and
    atlas dimension calculation are outside this recovered loop model.
    """
    if block_size <= 0 or atlas_height <= 0:
        raise ValueError('invalid atlas geometry')
    atlas_y = 0
    column = 0
    for x, y, width, height in rectangles:
        if width < 0 or height < 0:
            raise ValueError('negative rectangle dimensions')
        for dx in range(0, width, block_size):
            tile_width = min(block_size, width-dx)
            for dy in range(0, height, block_size):
                tile_height = min(block_size, height-dy)
                if tile_height > atlas_height:
                    raise ValueError('tile cannot fit atlas height')
                if atlas_y + tile_height > atlas_height:
                    atlas_y = 0
                    column += 1
                yield (x+dx, y+dy, tile_width, tile_height,
                       column*block_size, atlas_y)
                atlas_y += tile_height


def tile_sample_score(src, width, height, stride):
    """uvc ordinal 3: return (unequal_samples, total_samples).

    Samples x=1,3,...; y advances ONE row for only ceil((height-2)/2)
    iterations. Compares 16-bit values at BGR offsets 0/1, ignores offset 2.
    This is a single-buffer spatial score, not a frame difference metric.
    """
    if width < 0 or height < 0 or stride < 0:
        raise ValueError('invalid geometry')
    nx = (width-3)//2+1 if width >= 3 else 0
    ny = (height-3)//2+1 if height >= 3 else 0
    equal = 0
    for ix in range(nx):
        for y in range(ny):
            offset = 3+6*ix+y*stride
            positions = (offset, offset-3, offset+stride)
            if any(p < 0 or p+2 > len(src) for p in positions):
                raise ValueError('sample exceeds buffer')
            current, left, below = (src[p:p+2] for p in positions)
            equal += current == left or current == below
    total = nx*ny
    return total-equal, total


def http_service_preface(host, post=True):
    """Recovered e25/e24/857 Windows HTTP tunnel preface, without network I/O.

    Constant content length is copied from the artifact, not calculated.
    The caller condition HTTPHostName nonempty is outside this pure builder.
    """
    lines = [f'{"POST" if post else "GET"} /UVService/ HTTP/1.1',
             'User-Agent: Mozilla/4.0 (compatible; MSIE5.01; Windows NT)',
             'Content-Type: application/octet-stream',
             'Connection: Keep-Alive', 'Content-length: 8589934590',
             'Host: '+host, '']
    return ('\r\n'.join(lines)+'\r\n').encode('ascii', errors='replace')


class FrameStream:
    """e29 framing model: optional header cut then LE UInt32 length + payload.

    No HTTP status validation, matching the observed header cut. Empty frames
    with exactly four buffered bytes remain pending due to original Length>4.
    Resource limits and downstream dispatch are outside this model.
    """
    def __init__(self, expect_http_header=False):
        self.buffer = bytearray()
        self.expect_http_header = expect_http_header

    def feed(self, chunk):
        self.buffer.extend(chunk)
        if self.expect_http_header:
            end = self.buffer.find(b'\r\n\r\n')
            if end == -1:
                return []
            del self.buffer[:end+4]
            self.expect_http_header = False
        frames = []
        while len(self.buffer) > 4:
            length = struct.unpack_from('<I', self.buffer)[0]
            if len(self.buffer) < length+4:
                break
            frames.append(bytes(self.buffer[4:4+length]))
            del self.buffer[:4+length]
        return frames


def decode_transport_body(body):
    """e37 transport dispatch header; preserves unresolved address as UInt32.

    Returns None for unknown kind; rejects short buffers explicitly, rather
    than relying on the original array access/BlockCopy exceptions.
    """
    if not body:
        raise ValueError('empty transport body')
    if body[0] == 0:
        if len(body) < 8:
            raise ValueError('truncated relay header')
        address, port = struct.unpack_from('<IH', body, 2)
        return {'kind': 'relay', 'flag': body[1] != 0,
                'address_value': address, 'port': port, 'data': body[8:]}
    if body[0] == 1:
        return {'kind': 'direct', 'data': body[1:], 'flag': False}
    return None


def decode_command_fields(payload: bytes, *, ansi_codec: str) -> tuple[str, ...]:
    """E115: nonempty zero-based byte array -> ANSI text -> colon fields.

    Caller must select the observed Windows ANSI code page. This does not
    interpret numeric fields, authenticate a response, or establish an ID.
    Strict decoding deliberately rejects bytes instead of mimicking Windows
    replacement behavior. Empty SAFEARRAY semantics are not reconstructed.
    """
    if not payload:
        raise ValueError("empty byte-array behavior is not reconstructed")
    text = bytes(payload).decode(ansi_codec, errors="strict")
    return tuple(text.split(":"))


def encode_transport_frame(body: bytes) -> bytes:
    """E119 / RC40 e31: length prefix only; caller constructs body kind/header.

    Int32 length matches the Windows BitConverter.GetBytes overload. The
    receiver reads UInt32; valid managed array lengths have the same bytes.
    This is not the raw-send path e30 used for the HTTP preface.
    """
    body = bytes(body)
    if len(body) > 0x7fffffff - 4:
        raise ValueError("frame exceeds checked managed allocation size")
    return struct.pack("<i", len(body)) + body


def encode_typed_transport_frame(payload: bytes, *, kind: int) -> bytes:
    """E120 / e2c -> e2d -> e31, for an already integral byte kind.

    No default kind: call-site meaning must be recovered before network use.
    VB fractional Conversion.Int coercion is outside this model's domain.
    """
    if type(kind) is not int or not 0 <= kind <= 255:
        raise ValueError("kind must be an integral byte")
    return encode_transport_frame(bytes([kind]) + bytes(payload))


def encode_relay_frame(payload: bytes, *, ipv4: str, port: int, flag: int) -> bytes:
    """RC40 de1 mode0, field699 false; canonical IPv4 subset of helper333.

    Exact integral octets only. VB also coerces strings and applies Mod256;
    those noncanonical inputs are intentionally outside this model's domain.
    No claim that this suffices for authentication or a complete session.
    """
    parts = ipv4.split(".")
    if len(parts) != 4 or any(not s.isascii() or not s.isdecimal() for s in parts):
        raise ValueError("expected four decimal IPv4 octets")
    octets = [int(s) for s in parts]
    if any(n > 255 for n in octets):
        raise ValueError("IPv4 octet out of range")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("port out of range")
    if type(flag) is not int or not 0 <= flag <= 255:
        raise ValueError("flag out of range")
    address = sum(n << (8 * (3-i)) for i, n in enumerate(octets))
    return encode_transport_frame(struct.pack("<BBIH", 0, flag, address, port)
                                  + bytes(payload))


def derive_vfunction_key_bytes(password: str, length: int) -> bytes:
    """RC40 1485: SHA1(UTF16LE), resized with zero extension/truncation.

    This derives bytes only; TripleDES parity, CBC, padding and weak-key
    behavior belong to the crypto provider and are not modeled here.
    """
    import hashlib
    if length < 0:
        raise ValueError("negative length")
    digest = hashlib.sha1(password.encode("utf-16le", errors="surrogatepass")).digest()
    return (digest + bytes(max(0, length-len(digest))))[:length]


# E124: startup call 635a8c on global VFunction 7e2040.
REGISTRATION_PASSWORD = "".join(chr(n) for n in (5, 10, 15, 20, 25))


def encrypt_registration_bytes(payload: bytes, *, password: str = REGISTRATION_PASSWORD) -> bytes:
    """RC40 1486 with .NET Framework TripleDES/CBC/PKCS7 defaults.

    Requires cryptography. Not a complete request builder or authentication.
    Valid non-weak 192-bit keys only; provider error behavior is not modeled.
    """
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    from cryptography.hazmat.primitives.padding import PKCS7
    key = derive_vfunction_key_bytes(password, 24)
    iv = derive_vfunction_key_bytes("", 8)
    padder = PKCS7(64).padder()
    padded = padder.update(bytes(payload)) + padder.finalize()
    encryptor = Cipher(TripleDES(key), modes.CBC(iv)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def decrypt_registration_bytes(ciphertext: bytes, *, password: str = REGISTRATION_PASSWORD) -> bytes:
    """RC40 1487 counterpart; PKCS7 validity is not authenticity proof."""
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    from cryptography.hazmat.primitives.padding import PKCS7
    decryptor = Cipher(TripleDES(derive_vfunction_key_bytes(password, 24)),
                       modes.CBC(derive_vfunction_key_bytes("", 8))).decryptor()
    padded = decryptor.update(bytes(ciphertext)) + decryptor.finalize()
    unpadder = PKCS7(64).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def registration_fingerprint_digest(data: bytes) -> str:
    """E130: VFunction.GetMD5 bytes -> x2 hex, then VB6 uppercase.

    Caller must supply the recovered preimage bytes; this does not allocate a
    server ID or reproduce the unresolved machine fingerprint input policy.
    """
    import hashlib
    return hashlib.md5(data).hexdigest().upper()


@dataclass(frozen=True)
class Command3Identity:
    client_id: int
    public_source_port: int
    public_ip: str


def extract_command3_identity(payload: bytes, *, ansi_codec: str) -> Command3Identity:
    """E131: identity/endpoint subset of plaintext command 3, not full handshake.

    Accepts positive ASCII decimal Int32 IDs and decimal UInt16 ports only.
    Native VB IsNumeric/I4 coercion accepts additional formats not modeled here.
    Input must already be the DataReceived plaintext, not a transport frame or
    ciphertext. A parsed value alone proves neither origin nor registration.
    """
    fields = decode_command_fields(payload, ansi_codec=ansi_codec)
    if len(fields) < 4 or fields[0] != "3":
        raise ValueError("expected command 3 with endpoint and ID fields")
    port, identity = fields[1:3]
    for value in (port, identity):
        if not value or any(c < "0" or c > "9" for c in value):
            raise ValueError("expected ASCII decimal numeric fields")
    if len(port) > 5 or len(identity) > 10:
        raise ValueError("numeric field exceeds modeled range")
    port_number, id_number = int(port), int(identity)
    if not 0 <= port_number <= 65535 or not 1 <= id_number <= 2147483647:
        raise ValueError("numeric field outside modeled range")
    return Command3Identity(id_number, port_number, fields[3])


def encode_utf8_base64(value: str) -> str:
    """VFunction.EncodeUTF8Base64 (060014b1); valid Unicode input."""
    import base64
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def encode_base64_if_not_ascii(value: str) -> str:
    """VFunction.EncodeBase64IfNotASCII (060013f3); no marker/prefix."""
    return encode_utf8_base64(value) if any(ord(c) > 127 for c in value) else value


def fallback_registration_fingerprint(mac_address: str,
                                      program_files_creation_ticks: str,
                                      system_directory_creation_ticks: str,
                                      *, ansi_codec: str) -> str:
    """Observed startup fallback at63c66b..63c7a5.

    Caller supplies the actual source strings. This does not emulate Windows
    directories or select a Linux identity policy. Concatenation has no separator.
    """
    value = mac_address + program_files_creation_ticks + system_directory_creation_ticks
    return registration_fingerprint_digest(value.encode(ansi_codec))


def build_registration_command(terms: list[str] | tuple[str, ...], *, ansi_codec: str) -> bytes:
    """Build the observed 26-term InitMyPassword command (E147).

    Terms follow work/vb6-init-password-command3-field-sources.json.
    Term 22 contains three colon-separated directory creation tick strings.
    Caller must supply recovered machine/settings values; no defaults are guessed.
    This deliberately supports only colon-free values outside term 22.
    """
    if len(terms) != 26 or any(not isinstance(value, str) for value in terms):
        raise ValueError('registration requires exactly 26 string terms')
    for index, expected in ((0, '3'), (3, '0'), (5, '0'), (12, '')):
        if terms[index] != expected:
            raise ValueError(f'term {index} must equal {expected!r}')
    for index, value in enumerate(terms):
        if '\x00' in value or (index != 22 and ':' in value):
            raise ValueError(f'unsupported delimiter or NUL in term {index}')
    ticks = terms[22].split(':')
    if len(ticks) != 3 or any(not t or not t.isascii() or not t.isdecimal() for t in ticks):
        raise ValueError('term 22 requires three unsigned decimal tick strings')
    # Strict encoding: do not silently replace Linux host metadata characters.
    return ':'.join(terms).encode(ansi_codec, errors='strict')


def read_referral_int32(data: bytes) -> int:
    """ReadAllBytes + BitConverter.ToInt32(bytes,0), Windows x86 (E147).

    Extra bytes are ignored by the original helper. Missing/short file policy
    belongs to the caller; a missing file is not implicitly assigned zero.
    """
    if len(data) < 4:
        raise ValueError('Referral.ini requires at least four bytes')
    return int.from_bytes(data[:4], byteorder='little', signed=True)


def format_os_version_combine(major: int, minor: int, build: int, revision: int) -> str:
    """VFunction worker146e: Build|Major|MajorRevision|Minor|MinorRevision|Revision.

    This formats supplied version components; it does not claim that a Linux
    kernel release is a Windows/.NET OSVersion. Revision halves are signed Int16.
    """
    for value in (major, minor, build, revision):
        if type(value) is not int or not -1 <= value <= 2147483647:
            raise ValueError('expected .NET Version component range')
    if major < 0 or minor < 0:
        raise ValueError('major/minor must be nonnegative')
    def signed16(value):
        value &= 65535
        return value - 65536 if value >= 32768 else value
    return '|'.join(map(str, (build, major, signed16(revision >> 16),
                             minor, signed16(revision), revision)))


def connection_request_password_value(password: str, password_type: int, *, ansi_codec: str) -> str:
    """Observed request helper 0x6edc60, E162; not a complete login protocol.

    Type zero hashes ANSI(32 spaces + password) as lowercase MD5 hex.
    Other values reuse the string. Explicit codec and strict conversion omit
    Windows replacement-character behavior; caller must choose the codec.
    """
    import hashlib
    if password_type == 0:
        return hashlib.md5((" " * 32 + password).encode(ansi_codec, errors="strict")).hexdigest()
    return password


def connection_request_p2p_suffix(*, enabled: bool, public_ip: str,
                                  public_source_port: str, local_ip: str,
                                  local_port: str, encryption_key: str) -> str:
    """Command8 suffix, E164. Strings retain caller's VB numeric formatting.

    Input delimiters are rejected as a reconstruction policy, not native
    escaping behavior. This function neither opens a socket nor enables P2P.
    """
    if not enabled or not public_ip:
        return ""
    fields = (public_ip, public_source_port, local_ip, local_port, encryption_key)
    if any(any(c in value for c in "|:\0") for value in fields):
        raise ValueError("P2P suffix fields must not contain wire delimiters")
    return "|".join(fields)


def build_connection_request_command(terms: list[str], *, ansi_codec: str) -> bytes:
    """17 explicit terms of command8, E163/E165; no inferred defaults.

    Caller supplies recovered field order and VB-formatted numeric strings.
    Does not authenticate, encrypt, frame, or transmit the request. Colon/NUL
    rejection is an explicit restriction compared with native concatenation.
    """
    if len(terms) != 17 or any(not isinstance(term, str) for term in terms):
        raise ValueError("command8 requires 17 string terms")
    if terms[0] != "8":
        raise ValueError("command8 must begin with 8")
    if any(":" in term or "\0" in term for term in terms):
        raise ValueError("command8 terms must not contain colon or NUL")
    return ":".join(terms).encode(ansi_codec, errors="strict")


def login_numeric_salt_digest(password: str, salt: str, *, ansi_codec: str) -> str:
    """E168 type0 Login MD5(ANSI(local eight-digit salt + password)).

    Caller supplies salt; VB Randomize/Rnd state is not emulated. Does not model
    the nonzero PasswordType path or prove remote authentication success.
    """
    import hashlib
    if len(salt) != 8 or any(c not in "0123456789" for c in salt):
        raise ValueError("Login salt must contain eight ASCII digits")
    return hashlib.md5((salt + password).encode(ansi_codec, errors="strict")).hexdigest()


@dataclass(frozen=True, repr=False)
class LoginPasswordFields:
    """Sensitive login positions 0, 1 and 12; never log this object."""
    salt: str
    primary: str
    secondary: str


def login_password_fields(password: str, password_type: int, *,
                          salt: str | None, ansi_codec: str) -> LoginPasswordFields:
    """Login 6d6f3a..6d726e, R191; explicit local salt, no VB PRNG emulation.

    Type0 fills both digest positions. Other types copy TargetPassword to
    both positions and use 32 spaces for the salt. Strict ANSI is the existing
    reference subset; Windows replacement/DBCS copy behavior is not modeled.
    This computes packet fields, not successful remote authentication.
    """
    if type(password_type) is not int or not -(1 << 31) <= password_type < (1 << 31):
        raise ValueError("password_type must be a signed Int32")
    if not isinstance(password, str):
        raise TypeError("password must be a string")
    if password_type == 0:
        if salt is None:
            raise ValueError("type0 login requires an explicit eight-digit salt")
        return LoginPasswordFields(
            salt, login_numeric_salt_digest(password, salt, ansi_codec=ansi_codec),
            connection_request_password_value(password, 0, ansi_codec=ansi_codec))
    return LoginPasswordFields(" " * 32, password, password)


def build_login_with_password(fields: list[str], *, password: str,
                              password_type: int, salt: str | None,
                              ansi_codec: str) -> bytes:
    """Fill observed password positions in a caller-supplied 22-field schema.

    All other positions remain explicit; unresolved metadata has no defaults.
    The input list is not mutated. Returned bytes contain sensitive values.
    """
    if len(fields) != 22:
        raise ValueError("login requires exactly22 fields after its prefix")
    values = list(fields)
    auth = login_password_fields(password, password_type, salt=salt,
                                 ansi_codec=ansi_codec)
    values[0], values[1], values[12] = auth.salt, auth.primary, auth.secondary
    return build_login_command(values)


def encode_senddata_string(text: str, *, unicode_bytes: bool, ansi_codec: str) -> bytes:
    """Native helper6c10a0 via Form1.SendData, E171.

    True copies raw Windows BSTR bytes (UTF16LE, no BOM or terminator).
    False models ANSI only for the explicit codec; Windows DBCS copy-length
    behavior and replacement fallback are outside this reference model.
    """
    if unicode_bytes:
        return text.encode("utf-16le", errors="surrogatepass")
    return text.encode(ansi_codec, errors="strict")


def encode_p2p_boolean_body(payload: bytes, *, unicode_bytes: bool) -> bytes:
    """Managed e2c body: boxed Boolean -> Conversion.Int -> byte, E172.

    Returns body only. Socket worker framing/encryption is separate.
    """
    if type(unicode_bytes) is not bool:
        raise TypeError("unicode_bytes must be a Boolean")
    return bytes((1 if unicode_bytes else 0,)) + payload


def derive_p2p_aes_key(password: str) -> bytes:
    """RC40 AES.Init336: MD5 copied at offsets0 and15 into a zeroed32B key.

    ASCII-only subset includes the recovered generated key alphabet. .NET's
    replacement fallback for other input is intentionally not approximated.
    """
    import hashlib
    digest = hashlib.md5(password.encode("ascii", errors="strict")).digest()
    return digest[:15] + digest + b"\0"


def encrypt_p2p_aes_body(plaintext: bytes, password: str, *, iv: bytes | None = None) -> bytes:
    """AES_Encrypt338: IV16 || AES256-CBC-PKCS7(plaintext), E176.

    Omit IV for fresh random bytes. Explicit IV is for reproducible fixtures.
    Outer UInt32 frame prefix is not part of this returned body.
    """
    import os
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7
    iv = os.urandom(16) if iv is None else bytes(iv)
    if len(iv) != 16:
        raise ValueError("P2P IV must contain 16 bytes")
    padder = PKCS7(128).padder()
    padded = padder.update(bytes(plaintext)) + padder.finalize()
    encryptor = Cipher(algorithms.AES(derive_p2p_aes_key(password)), modes.CBC(iv)).encryptor()
    return iv + encryptor.update(padded) + encryptor.finalize()


def decrypt_p2p_aes_body(body: bytes, password: str) -> bytes:
    """AES_Decrypt339 valid-body subset; malformed framing/padding raises."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.padding import PKCS7
    body = bytes(body)
    if len(body) < 32 or (len(body) - 16) % 16:
        raise ValueError("P2P body needs IV16 and complete ciphertext blocks")
    decryptor = Cipher(algorithms.AES(derive_p2p_aes_key(password)), modes.CBC(body[:16])).decryptor()
    padded = decryptor.update(body[16:]) + decryptor.finalize()
    unpadder = PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def encode_p2p_frame(payload: bytes, *, unicode_bytes: bool,
                     encryption_password: str | None, iv: bytes | None = None) -> bytes:
    """P2P socket path: flag || payload, optional AES, UInt32 LE length.

    R195 combines recovered e2c, SendByteArray and framing operations. Caller
    must explicitly select the session encryption state; no handshake is
    performed and this function does not apply to the relay path.
    """
    body = encode_p2p_boolean_body(bytes(payload), unicode_bytes=unicode_bytes)
    if encryption_password is not None:
        body = encrypt_p2p_aes_body(body, encryption_password, iv=iv)
    elif iv is not None:
        raise ValueError("an IV requires enabled P2P encryption")
    return encode_transport_frame(body)


def decode_p2p_frame_body(body: bytes, *,
                          encryption_password: str | None) -> tuple[bytes, bool]:
    """RC40 303 -> 304: decrypt complete body, strip first byte, flag >0.

    Input excludes the four-byte stream length. Payload stays binary, so
    screen data is not prematurely decoded as text. Empty body is rejected
    explicitly instead of reproducing the original index exception.
    """
    body = bytes(body)
    if encryption_password is not None:
        body = decrypt_p2p_aes_body(body, encryption_password)
    if not body:
        raise ValueError("P2P body requires an encoding flag")
    return body[1:], body[0] > 0


def p2p_disabled_by_tick_entry(now_signed: int, saved_signed: int) -> bool:
    """E177 native signed GetTickCount difference, NOT wrap-safe elapsed time.

    Applies only after a dictionary entry exists; registry and empty-ID paths
    are separate. Caller provides the original signed32-bit values.
    """
    for value in (now_signed, saved_signed):
        if type(value) is not int or not -(1 << 31) <= value < (1 << 31):
            raise ValueError("tick input must be a signed Int32")
    delta = now_signed - saved_signed
    return 0 <= delta <= 12_000_000


def build_login_command(fields: list[str]) -> bytes:
    """E185 login: +22 preformatted fields, returned as raw BSTR UTF16LE.

    Callers supply recovered values and original VB numeric formatting.
    This does not compute unresolved defaults, authenticate or send a packet.
    Delimiter/NUL restrictions select an unambiguous valid-input subset.
    """
    if len(fields) != 22:
        raise ValueError("login requires exactly22 fields after its prefix")
    if any(not isinstance(value, str) for value in fields):
        raise TypeError("login fields must be preformatted strings")
    if any(":" in value or "\0" in value for value in fields):
        raise ValueError("login fields cannot contain colon or NUL")
    return ("login:" + ":".join(fields)).encode("utf-16-le", errors="surrogatepass")


def login_display_name(*, mode: str, custom_name: str, computer_name: str, username: str) -> str:
    """E187 helper6cb240 valid-string subset, with UTF16 code-unit Left20.

    Windows name APIs are replaced by explicit caller inputs on Linux.
    Original ASCII regex removes its listed characters, not backslash.
    UTF16 slicing can preserve a dangling surrogate, matching BSTR storage.
    """
    import re
    selected = {"custom": custom_name, "automaticgetcomputername": computer_name,
                "automaticgetusername": username}.get(mode, "")
    filtered = re.sub(r"[!#$&?:/\*,.@<>;'\"=]", "", selected)
    raw = filtered.encode("utf-16-le", errors="surrogatepass")[:40]
    return raw.decode("utf-16-le", errors="surrogatepass")


def version_equal_or_greater(current: str, minimum: str) -> bool:
    """R198: compare the first three numeric components of canonical versions.

    Models VFunction.IsVersionEqualOrGreater for ASCII decimal components only.
    VB ToLong's locale, rounding, signed or hexadecimal string conversions are
    deliberately outside this helper's supported domain. Extra components are
    ignored, as in the recovered CIL. A short current version returns False.
    """
    left = current.split('.')
    if len(left) < 3:
        return False
    right = minimum.split('.')
    if len(right) < 3:
        raise ValueError('minimum version requires three components')
    def component(value):
        if not value or any(c not in '0123456789' for c in value):
            raise ValueError('version component requires ASCII decimal digits')
        number = int(value)
        if number > 0x7fffffffffffffff:
            raise ValueError('version component exceeds signed Int64')
        return number
    for index in range(3):
        a, b = component(left[index]), component(right[index])
        if a != b:
            return a > b
    return True


def encode_byte_array_fields(fields) -> bytes:
    """R200: VFunction.CreateByteArrayDataFromByteArray's length/value layout.

    None and empty byte arrays both become a zero UInt32 LE length. No count
    or outer transport header is included. Nonzero-lower-bound VB arrays are
    outside this portable model.
    """
    result = bytearray()
    for field in fields:
        if field is None:
            value = b''
        elif isinstance(field, (bytes, bytearray, memoryview)):
            value = bytes(field)
        else:
            raise TypeError('field must be bytes-like or None')
        result.extend(struct.pack('<I', len(value)))
        result.extend(value)
    return bytes(result)


def decode_byte_array_fields(payload: bytes, *, expected_count=None):
    """Parse a complete R200 field payload; reject truncated length/value data.

    This strict inverse is reconstruction policy, not recovered error handling.
    None and empty arrays are indistinguishable on the wire and return b''.
    """
    fields = []
    offset = 0
    while offset < len(payload):
        if len(payload) - offset < 4:
            raise ValueError('truncated field length')
        length = struct.unpack_from('<I', payload, offset)[0]
        offset += 4
        if length > len(payload) - offset:
            raise ValueError('truncated field value')
        fields.append(bytes(payload[offset:offset + length]))
        offset += length
    if expected_count is not None and len(fields) != expected_count:
        raise ValueError('unexpected field count')
    return fields
