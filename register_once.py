"""One bounded registration attempt with explicit experimental request values.

Input JSON: {"terms": [26 strings], "ansi_codec": "cp1252"}.
Writes only sanitized diagnostics, never plaintext commands or passwords.
"""
import argparse
import dataclasses
import datetime
import hashlib
import json
import time
from pathlib import Path
from registration_transport import RegistrationTransport, DEFAULT_HOST
from uv_reference import build_registration_command, extract_command3_identity


def run(config, *, timeout=8.0, original_certificate_policy=False, observe_seconds=0.0):
    command = build_registration_command(config['terms'], ansi_codec=config['ansi_codec'])
    result = {
        'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'endpoint': DEFAULT_HOST, 'port': 443,
        'original_certificate_policy': original_certificate_policy,
        'request_bytes': len(command), 'wire_field_count': len(command.split(b':')),
        'registration_payload_sent': False, 'server_issued_id': None,
        'limitations': ['Experimental request values; server semantics not fully recovered.',
                        'Accept-all certificate mode does not authenticate server identity.']
    }
    transport = RegistrationTransport(timeout=timeout,
                                      original_certificate_policy=original_certificate_policy)
    try:
        result['stage'] = 'connect'
        transport.connect()
        result['http_status'] = transport.response_header.split(b'\r\n', 1)[0].decode('ascii')
        result['peer'] = transport.channel.getpeername()
        cert = transport.channel.getpeercert(binary_form=True)
        result['certificate_sha256'] = hashlib.sha256(cert).hexdigest()
        result['stage'] = 'send_registration'
        transport.send_command(command)
        result['registration_payload_sent'] = True
        result['stage'] = 'receive_reply'
        payload = transport.receive_mode1_payload()
        result['response_bytes'] = len(payload)
        result['response_sha256'] = hashlib.sha256(payload).hexdigest()
        # Save no arbitrary response text: other command fields can contain secrets.
        result['stage'] = 'parse_identity'
        identity = extract_command3_identity(payload, ansi_codec=config['ansi_codec'])
        result['identity'] = dataclasses.asdict(identity)
        result['server_issued_id'] = identity.client_id
        result['stage'] = 'identity_received'
        if observe_seconds > 0:
            started = time.monotonic()
            deadline = started + observe_seconds
            result['post_identity_observation'] = {'requested_seconds': observe_seconds,
                                                  'frames': [], 'closed_by_peer': False}
            while time.monotonic() < deadline:
                transport.timeout = deadline - time.monotonic()
                try:
                    message = transport.receive_mode1_payload()
                except TimeoutError:
                    break
                except EOFError:
                    result['post_identity_observation']['closed_by_peer'] = True
                    break
                result['post_identity_observation']['frames'].append({
                    'bytes': len(message), 'sha256': hashlib.sha256(message).hexdigest()})
                if len(result['post_identity_observation']['frames']) >= 32:
                    result['post_identity_observation']['frame_limit_reached'] = True
                    break
            result['post_identity_observation']['elapsed_seconds'] = round(time.monotonic()-started, 3)
            result['post_identity_observation']['buffered_bytes'] = len(transport.buffer)
    except Exception as exc:
        # Exception messages can include protocol data; retain only the class.
        result['error_type'] = type(exc).__name__
        result['buffered_response_bytes'] = len(transport.buffer)
    finally:
        transport.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=8.0)
    parser.add_argument('--observe-seconds', type=float, default=0.0)
    parser.add_argument('--original-certificate-policy', action='store_true')
    args = parser.parse_args()
    result = run(json.loads(args.config.read_text()), timeout=args.timeout,
                 original_certificate_policy=args.original_certificate_policy,
                 observe_seconds=args.observe_seconds)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0 if result['server_issued_id'] is not None else 1

if __name__ == '__main__':
    raise SystemExit(main())
