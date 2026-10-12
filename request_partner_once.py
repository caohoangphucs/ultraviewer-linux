"""Register and send one bounded, explicit command8 partner request.

Registration JSON: existing 26-term private profile plus ansi_codec.
Partner JSON: request_terms (17 strings), password, password_type.
Source ID/digest and target password value are filled from recovered algorithms;
all other request fields remain explicit. Never logs plaintext or passwords.
"""
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from registration_transport import RegistrationTransport
from uv_reference import (build_registration_command, extract_command3_identity,
                          build_connection_request_command,
                          connection_request_password_value)


def run(registration, partner, *, timeout=8, original_certificate_policy=False):
    codec = registration['ansi_codec']
    terms = list(partner['request_terms'])
    if len(terms) != 17:
        raise ValueError('partner request needs seventeen explicit terms')
    result = {'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'registration_sent': False, 'partner_request_sent': False,
              'controller_id': None, 'session_authenticated': False,
              'responses': [], 'original_certificate_policy': original_certificate_policy,
              'limitations': ['Explicit experimental Linux metadata.',
                              'Request response is not a complete control session.']}
    transport = RegistrationTransport(timeout=timeout,
                                      original_certificate_policy=original_certificate_policy)
    try:
        result['stage'] = 'connect'
        transport.connect()
        result['stage'] = 'register'
        transport.send_command(build_registration_command(registration['terms'], ansi_codec=codec))
        result['registration_sent'] = True
        identity = extract_command3_identity(transport.receive_mode1_payload(), ansi_codec=codec)
        result['controller_id'] = identity.client_id
        terms[2] = connection_request_password_value(partner['password'],
                                                     partner['password_type'], ansi_codec=codec)
        terms[6] = str(identity.client_id)
        terms[7] = hashlib.md5((terms[6] + registration['terms'][2]).encode(codec)).hexdigest()
        result['stage'] = 'partner_request'
        transport.send_command(build_connection_request_command(terms, ansi_codec=codec))
        result['partner_request_sent'] = True
        result['stage'] = 'partner_response'
        for _ in range(4):
            payload = transport.receive_mode1_payload()
            fields = payload.split(b':')
            response = {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest(),
                        'field_count': len(fields)}
            for index in range(min(2, len(fields))):
                if fields[index].isdigit() and len(fields[index]) < 5:
                    response[f'numeric_field_{index}'] = int(fields[index])
            result['responses'].append(response)
            if fields[0] == b'8':
                result['stage'] = 'partner_response_received'
                break
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    finally:
        transport.close()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('registration', type=Path)
    parser.add_argument('partner', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=8)
    parser.add_argument('--original-certificate-policy', action='store_true')
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv == ['help']:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    try:
        result = run(json.loads(args.registration.read_text()), json.loads(args.partner.read_text()),
                     timeout=args.timeout, original_certificate_policy=args.original_certificate_policy)
    except Exception as exc:
        # Configuration decoding errors must not echo credential content.
        result = {'stage': 'configuration', 'error_type': type(exc).__name__,
                  'session_authenticated': False}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    # Obtaining a response is a probe milestone, never a login-success exit status.
    return 0 if result.get('stage') == 'partner_response_received' else 1


if __name__ == '__main__':
    raise SystemExit(main())
