import unittest
from receive_pipeline import process_form1_packet
from uv_reference import encode_byte_array_fields, encode_typed_transport_frame, FrameStream


class ReceivePipelineTests(unittest.TestCase):
    def packet(self, fields, **options):
        return process_form1_packet(encode_byte_array_fields(fields), source='192.0.2.4',
                                    source_port=1234, unicode_bytes=False, **options)

    def test_framed_binary_response_retains_every_field(self):
        # Synthetic sixteen-field response, passed through the actual stream codec.
        fields = [b'\0', b'\x02\0\0\0'] + [b''] * 14
        fields[6] = b'6.6.124'
        frame = encode_typed_transport_frame(encode_byte_array_fields(fields), kind=1)
        stream = FrameStream()
        bodies = []
        for byte in frame:
            bodies.extend(stream.feed(bytes([byte])))
        self.assertEqual(len(bodies), 1)
        self.assertEqual(bodies[0][0], 1)
        result = process_form1_packet(bodies[0][1:], source='192.0.2.4',
                                     source_port=1234, unicode_bytes=False)
        self.assertEqual(result.event_id, 9)
        self.assertEqual(result.event_arguments[2], fields)
        self.assertEqual(result.fields[6], b'6.6.124')

    def test_audio_consumption_and_microphone_forwarding_on_sink_failure(self):
        def failing_sink(operation, data):
            raise RuntimeError('synthetic playback failure')
        for kind in (42, 43, 50, 51):
            with self.subTest(kind=kind):
                result = self.packet([bytes([kind]), b'\x04\0\0\0'],
                                     playback_enabled=True, audio_sink=failing_sink)
                self.assertEqual(result.audio_error, 'RuntimeError')
                self.assertEqual(result.event_id, None if kind < 50 else 9)
        disabled = self.packet([b'*', b'encoded'])
        self.assertIsNone(disabled.audio_operation)
        self.assertIsNone(disabled.event_id)

    def test_silence_is_generated_and_malformed_split_is_forwarded_as_null(self):
        played = []
        result = self.packet([b'2', b'\x03\0\0\0'], audio_sink=lambda op, data: played.append(data))
        self.assertEqual(played, [b'\0\0\0'])
        self.assertEqual(result.event_id, 9)
        invalid = process_form1_packet(b'\x01', source='peer', source_port=1, unicode_bytes=False)
        self.assertEqual(invalid.event_id, 9)
        self.assertIsNone(invalid.event_arguments[2])
        with self.assertRaises(ValueError):
            self.packet([])


if __name__ == '__main__':
    unittest.main()
