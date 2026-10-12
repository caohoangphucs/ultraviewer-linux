"""Known command8 route fields recovered from Form1.ManipulateTargetInfo.

This decodes a status1 route response, not Windows session authentication.
Endpoint strings retain native sentinel values (e.g. "0").
"""
from dataclasses import dataclass


@dataclass(frozen=True, repr=False)
class TargetRoute:
    lan_ip: str
    public_ip: str
    public_port: int
    lan_port: int
    command_port: int
    computer_name_encoded: str
    tcp_port: int
    tcp_server_ip: str
    matched_custom_password: int
    target_session_id: int
    tcp_server_hostname: str
    partner_secret_token: str | None


def decode_target_route(payload: bytes, *, ansi_codec: str) -> TargetRoute:
    fields = payload.decode(ansi_codec, errors="strict").split(":")
    if len(fields) < 15 or fields[:2] != ["8", "1"]:
        raise ValueError("expected status1 command8 route response")
    def integer(index, low, high):
        value = fields[index]
        if not value or not value.lstrip("-").isascii() or not value.lstrip("-").isdigit():
            raise ValueError("invalid numeric route field")
        result = int(value)
        if not low <= result <= high:
            raise ValueError("route field outside modeled range")
        return result
    return TargetRoute(fields[2], fields[4], integer(5,0,65535),
                       integer(6,0,65535), integer(7,0,65535), fields[8],
                       integer(9,0,65535), fields[11], integer(12,-32768,32767),
                       integer(13,-2147483648,2147483647), fields[14],
                       fields[20] if len(fields) > 20 else None)
