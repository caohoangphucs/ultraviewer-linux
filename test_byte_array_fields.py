import unittest
from uv_reference import encode_byte_array_fields, decode_byte_array_fields


class FieldArrayTests(unittest.TestCase):
    def test_explicit_wire_fixture_and_null_collapse(self):
        wire = bytes.fromhex('0100000000030000004100420000000000000000')
        self.assertEqual(encode_byte_array_fields([b'\x00', b'A\x00B', None, b'']), wire)
        self.assertEqual(decode_byte_array_fields(wire, expected_count=4),
                         [b'\x00', b'A\x00B', b'', b''])

    def test_complete_payload_rejects_every_truncated_prefix(self):
        wire = bytes.fromhex('03000000616263')
        for size in range(1, len(wire)):
            with self.subTest(size=size), self.assertRaises(ValueError):
                decode_byte_array_fields(wire[:size])
        with self.assertRaises(ValueError):
            decode_byte_array_fields(wire, expected_count=16)
        self.assertEqual(decode_byte_array_fields(b'', expected_count=0), [])


if __name__ == '__main__':
    unittest.main()
