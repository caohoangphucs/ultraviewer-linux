"""Recovered VTCPClient form receive path (RC40 e3a/e4a/de5).

This module handles already-decapsulated binary packets in form mode. Socket,
relay/P2P negotiation, Windows callbacks and audio codecs are separate layers.
"""
from dataclasses import dataclass
import struct
from uv_reference import decode_byte_array_fields


@dataclass(frozen=True, repr=False)
class FormReceiveResult:
    # Payloads can contain credentials; default object repr deliberately hides them.
    fields: list | None
    event_id: int | None
    event_arguments: tuple | None
    audio_operation: str | None
    parse_error: str | None = None
    audio_error: str | None = None


def process_form1_packet(payload, *, source, source_port, unicode_bytes,
                         playback_enabled=False, audio_sink=None,
                         max_silence_bytes=8 * 1024 * 1024):
    """Split and route one packet; audio_sink(operation, bytes) is optional.

    Ordinary packets queue event9 with five arguments. Kinds42/43 consume the
    packet even when playback is disabled or the audio sink raises. Kinds50/51
    also queue event9 after attempting microphone playback. Silent blocks42/50
    contain an Int32LE byte count, not PCM. A bounded allocation is a Linux
    resource policy; native code has no corresponding explicit limit.

    Parse errors queue event9 with a null split array, like e4a's error-string
    return followed by e3a's enqueue. Error diagnostics retain exception class
    names only; .NET error messages and VB coercion are not emulated.
    """
    if max_silence_bytes < 0:
        raise ValueError('negative silence allocation limit')
    raw = bytes(payload)
    try:
        fields = decode_byte_array_fields(raw)
    except ValueError as exc:
        return FormReceiveResult(None, 9,
                                 (source, source_port, None, raw, unicode_bytes),
                                 None, type(exc).__name__)
    # Native SplitData(empty) returns [Nothing]. The following nested index then
    # fails outside the audio try/catch; do not fabricate an ordinary packet.
    if not fields or not fields[0]:
        raise ValueError('packet has no discriminator byte')
    kind = fields[0][0]
    operation = {42: 'Play16BitAudio', 43: 'PlayEncodedAudio',
                 50: 'Play16BitMicrophoneAudio',
                 51: 'PlayMicrophoneEncodedAudio'}.get(kind)
    attempted = operation is not None and (kind >= 50 or playback_enabled)
    audio_error = None
    if attempted:
        try:
            audio = fields[1]
            if kind in (42, 50):
                if len(audio) < 4:
                    raise ValueError('truncated silence length')
                size = struct.unpack_from('<i', audio)[0]
                if size < 0 or size > max_silence_bytes:
                    raise ValueError('silence length outside allocation policy')
                audio = bytes(size)
            if audio_sink is not None:
                audio_sink(operation, audio)
        except Exception as exc:
            # e4a swallows audio exceptions, then follows the same return branch.
            audio_error = type(exc).__name__
    consumed = kind in (42, 43)
    arguments = None if consumed else (source, source_port, fields, raw, unicode_bytes)
    return FormReceiveResult(fields, None if consumed else 9, arguments,
                             operation if attempted else None,
                             audio_error=audio_error)
