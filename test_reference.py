import struct
import unittest
from uv_reference import (CachedItem, dib_stride, extract_tile, pack_atlas,
                          restore_atlas, import_cache, export_cache, atlas_layout, tile_sample_score, http_service_preface, FrameStream, decode_transport_body, encode_transport_frame, encode_relay_frame, extract_command3_identity)


class ReferenceTests(unittest.TestCase):
    def test_command3_id_is_distinct_from_public_endpoint(self):
        # Synthetic offline data: not a captured or server-issued ID.
        value = extract_command3_identity(b"3:45678:123456789:203.0.113.7:unused",
                                          ansi_codec="cp1252")
        self.assertEqual(value.client_id, 123456789)
        self.assertEqual(value.public_source_port, 45678)
        self.assertEqual(value.public_ip, "203.0.113.7")
        for payload in (b"3:45678:abc:203.0.113.7", b"3:45678:2147483648:x",
                        b"3:70000:123:x", b"3:45678:0:x", b"38:1:123:x"):
            with self.assertRaises(ValueError):
                extract_command3_identity(payload, ansi_codec="cp1252")

    def test_relay_outbound_address_and_port_wire(self):
        wire = encode_relay_frame(b"hi", ipv4="1.2.3.4", port=2000, flag=1)
        self.assertEqual(wire, bytes.fromhex("0a000000000104030201d0076869"))
        self.assertEqual(FrameStream().feed(wire), [wire[4:]])

    def test_outbound_frame_fixed_wire_and_receiver_fragmentation(self):
        body = b"\x013:123:0:abc"
        wire = encode_transport_frame(body)
        self.assertEqual(wire, b"\x0c\x00\x00\x00\x013:123:0:abc")
        receiver = FrameStream()
        self.assertEqual(receiver.feed(wire[:3]), [])
        self.assertEqual(receiver.feed(wire[3:7]), [])
        self.assertEqual(receiver.feed(wire[7:]), [body])

    def test_dib_stride_padding(self):
        self.assertEqual(dib_stride(3, 24), 12)

    def test_native_row_orientation_and_partial_rectangle(self):
        # Physical bottom-up 3x3 one-byte DIB; padding must remain untouched.
        source = bytes([7,8,9,99, 4,5,6,99, 1,2,3,99])
        self.assertEqual(extract_tile(source,1,4,1,0,2,2,3), bytes([2,3,5,6]))
        atlas = bytearray([88]*12)
        self.assertEqual(pack_atlas(source,atlas,1,4,4,1,0,1,1,2,2,3),4)
        self.assertEqual(atlas, bytearray([88]*4+[88,2,3,88]+[88,5,6,88]))
        restored = bytearray([77]*12)
        restore_atlas(atlas,restored,1,4,4,1,1,1,0,2,2,3)
        self.assertEqual(restored,bytearray([77]*4+[77,5,6,77]+[77,2,3,77]))

    def test_cache_against_explicit_wire_fixture(self):
        payload = struct.pack('<iiii',2,1,-7,2)+b'AB'
        fixture = struct.pack('<ii',123,18)+payload
        item = CachedItem(2,1,-7,b'AB')
        self.assertEqual(export_cache([(123,item)]),fixture)
        self.assertEqual(list(import_cache(fixture).items()),[(123,item)])
        with self.assertRaises(ValueError):
            import_cache(fixture[:-1])
        with self.assertRaises(ValueError):
            import_cache(fixture+fixture)

    def test_atlas_column_order_edges_and_cross_rectangle_state(self):
        self.assertEqual(list(atlas_layout([(10,20,3,3),(30,40,1,1)],2,3)),[
            (10,20,2,2,0,0), (10,22,2,1,0,2),
            (12,20,1,2,2,0), (12,22,1,1,2,2),
            (30,40,1,1,4,0)])

    def test_spatial_score_ignores_third_channel(self):
        image = bytes(v for i in range(35) for v in (10,20,i))
        self.assertEqual(tile_sample_score(image,7,5,21),(0,6))
        image = bytes(v for i in range(35) for v in (i,0,0))
        self.assertEqual(tile_sample_score(image,7,5,21),(6,6))
        self.assertEqual(tile_sample_score(b'',2,5,6),(0,0))

    def test_spatial_score_row_step_and_neighbor_or(self):
        image = bytearray(7*5*3)
        # Samples in y=0,1 only; changes in row4 must not affect the score.
        for x in (1,3,5):
            image[x*3] = 1
            image[4*21+x*3] = 9
        self.assertEqual(tile_sample_score(image,7,5,21),(3,6))
        # Matching below is sufficient even when the left neighbor differs.
        for x in (1,3,5):
            image[21+x*3] = 1
        self.assertEqual(tile_sample_score(image,7,5,21),(3,6))

    def test_http_service_preface_wire_bytes(self):
        expected = (b'POST /UVService/ HTTP/1.1\r\n'
                    b'User-Agent: Mozilla/4.0 (compatible; MSIE5.01; Windows NT)\r\n'
                    b'Content-Type: application/octet-stream\r\n'
                    b'Connection: Keep-Alive\r\n'
                    b'Content-length: 8589934590\r\n'
                    b'Host: example.test\r\n\r\n')
        self.assertEqual(http_service_preface('example.test'),expected)
        self.assertEqual(http_service_preface('example.test',False),
                         expected.replace(b'POST ',b'GET ',1))

    def test_fragmented_http_and_multiple_length_frames(self):
        stream = FrameStream(True)
        self.assertEqual(stream.feed(b'HTTP/1.1 200 OK\r\nX: y\r\n\r'),[])
        self.assertEqual(stream.feed(b'\n\x03\x00'),[])
        self.assertEqual(stream.feed(b'\x00\x00AB'),[])
        self.assertEqual(stream.feed(b'C\x01\x00\x00\x00Z'),[b'ABC',b'Z'])
        self.assertEqual(stream.buffer,b'')

    def test_native_strict_four_byte_guard(self):
        stream = FrameStream()
        self.assertEqual(stream.feed(bytes(4)),[])
        self.assertEqual(stream.feed(b'X'),[b''])
        self.assertEqual(stream.buffer,b'X')

    def test_transport_header_offsets(self):
        self.assertEqual(decode_transport_body(b'\x00\x02\x78\x56\x34\x12\xd0\x07PAY'),
                         {'kind':'relay','flag':True,'address_value':0x12345678,
                          'port':2000,'data':b'PAY'})
        self.assertEqual(decode_transport_body(b'\x01PAY'),
                         {'kind':'direct','data':b'PAY','flag':False})
        self.assertIsNone(decode_transport_body(b'\x7fPAY'))
        with self.assertRaises(ValueError):
            decode_transport_body(b'\x00')

    def test_invalid_copy_is_atomic(self):
        dst = bytearray(b'unchanged')
        with self.assertRaises(ValueError):
            restore_atlas(b'A',dst,1,3,3,0,0,0,0,3,2,2)
        self.assertEqual(dst,b'unchanged')


if __name__ == '__main__':
    unittest.main()
