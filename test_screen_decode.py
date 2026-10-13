"""Known RGB555 colors and rectangle placement; no real screen fixture."""
import struct
import unittest
from PIL import Image
from screen_decode import apply_rgb555_update


class FixedPixels:
    def decompress(self, payload, size):
        # Win32 RGB555: red=0x7c00, green=0x03e0, blue=0x001f.
        data = struct.pack('<HHH',0x7c00,0x03e0,0x001f)
        if size != len(data):
            raise ValueError('unexpected pixel count')
        return data


class ScreenDecodeTests(unittest.TestCase):
    def test_known_colors_top_down_and_multiple_rectangles(self):
        canvas = Image.new('RGB',(4,2),'white')
        rects=struct.pack('<HHHHHHHH',1,0,2,1,0,1,1,1)
        fields=[b'\x01\0',rects,b'\x28\xb5\x2f\xfd',b'\0',b'\0'*4]
        self.assertEqual(apply_rgb555_update(canvas,fields,FixedPixels()),2)
        self.assertEqual(canvas.getpixel((1,0)),(255,0,0))
        self.assertEqual(canvas.getpixel((2,0)),(0,255,0))
        self.assertEqual(canvas.getpixel((0,1)),(0,0,255))
        self.assertEqual(canvas.getpixel((3,1)),(255,255,255))

    def test_invalid_later_rectangle_does_not_modify_canvas(self):
        canvas=Image.new('RGB',(2,2),'white');before=canvas.tobytes()
        rects=struct.pack('<HHHHHHHH',0,0,1,1,2,2,1,1)
        fields=[b'\x01',rects,b'\x28\xb5\x2f\xfd',b'\0',b'\0'*4]
        with self.assertRaises(ValueError):
            apply_rgb555_update(canvas,fields,FixedPixels())
        self.assertEqual(canvas.tobytes(),before)


if __name__=='__main__':
    unittest.main()


class ScreenCacheTests(unittest.TestCase):
    def test_cache_reuse_and_missing_reference_is_atomic(self):
        from screen_decode import RGB555Screen
        import struct
        screen=RGB555Screen((4,2),None)
        screen.canvas.putpixel((0,0),(255,0,0))
        fields=[b'\x01',b'',b'',b'\0',b'\0'*4,b'',b'',b'',b'',b'',
                struct.pack('<hhhhi',0,0,1,1,123)]
        screen.apply(fields)
        fields[10]=b''
        fields[9]=struct.pack('<hhi',3,1,123)
        screen.apply(fields)
        self.assertEqual(screen.canvas.getpixel((3,1)),(255,0,0))
        before=screen.canvas.tobytes()
        fields[9]+=struct.pack('<hhi',1,1,999)
        with self.assertRaises(ValueError):screen.apply(fields)
        self.assertEqual(screen.canvas.tobytes(),before)
        self.assertEqual(list(screen.cache),[123])

    def test_jpeg_bottom_up_atlas_precedes_pixel_path(self):
        import io,struct
        from PIL import Image
        from screen_decode import RGB555Screen
        atlas=Image.new('RGB',(16,4),(255,0,0))
        for y in range(2,4):
            for x in range(16):atlas.putpixel((x,y),(0,0,255))
        data=io.BytesIO();atlas.save(data,format='JPEG',quality=100,subsampling=0)
        fields=[b'\x01',b'',b'',b'\0',b'\0'*4,b'',b'',data.getvalue(),
                struct.pack('<hhhh',0,0,2,4),b'',b'']
        screen=RGB555Screen((2,4),None);screen.apply(fields)
        self.assertGreater(screen.canvas.getpixel((0,0))[2],240)
        self.assertGreater(screen.canvas.getpixel((0,3))[0],240)

    def test_scroll_copy_uses_original_pixels_before_cache(self):
        import struct
        from screen_decode import RGB555Screen
        screen=RGB555Screen((2,4),None)
        for y in range(4):
            for x in range(2):screen.canvas.putpixel((x,y),(y*60,0,0))
        fields=[b'\1',b'',b'',b'\0',b'\0'*4,b'',
                struct.pack('<hhhhh',1,0,0,2,4)+struct.pack('<hhhh',0,0,2,3),
                b'',b'',b'',b'']
        screen.apply(fields)
        self.assertEqual([screen.canvas.getpixel((0,y))[0] for y in range(4)],
                         [60,120,180,180])
        before=screen.canvas.tobytes()
        fields[6]=struct.pack('<hhhhh',1,0,0,2,4)+struct.pack('<hhhh',0,3,2,1)
        with self.assertRaises(ValueError):screen.apply(fields)
        self.assertEqual(screen.canvas.tobytes(),before)

    def test_32_pixel_atlas_regression(self):
        import io,struct
        from PIL import Image
        from screen_decode import RGB555Screen
        atlas=Image.new('RGB',(32,79),(0,180,0))
        data=io.BytesIO();atlas.save(data,format='JPEG',quality=100,subsampling=0)
        rectangles=b''.join(struct.pack('<hhhh',*r) for r in
                           [(0,0,32,32),(32,0,32,32),(64,0,32,15)])
        fields=[b'\1',b'',b'',b'\0',b'\0'*4,b'',b'',data.getvalue(),rectangles,b'',b'']
        screen=RGB555Screen((96,32),None,block_size=32)
        self.assertEqual(screen.apply(fields),3)
        self.assertGreater(screen.canvas.getpixel((95,14))[1],170)
        wrong=RGB555Screen((96,32),None,block_size=16)
        with self.assertRaises(ValueError):wrong.apply(fields)

class DesktopSizeTests(unittest.TestCase):
    def test_login_dimensions_support_larger_partner(self):
        import struct
        from screen_decode import desktop_size_from_login,RGB555Screen
        fields=[b'\0\0',struct.pack('<i',1920),struct.pack('<i',1080)]
        size=desktop_size_from_login(fields)
        self.assertEqual(size,(1920,1080))
        screen=RGB555Screen(size,None)
        update=[b'\1',b'',b'',b'\0',b'\0'*4,b'',b'',b'',b'',b'',struct.pack('<hhhhi',1800,1000,32,32,7)]
        screen.apply(update)
        self.assertEqual(len(screen.cache),1)
        with self.assertRaises(ValueError):RGB555Screen((1024,768),None).apply(update)

    def test_bad_login_dimensions_rejected(self):
        import struct
        from screen_decode import desktop_size_from_login
        for w,h in [(0,1080),(-1,768),(100000,100000),(8192,8192)]:
            with self.assertRaises(ValueError):desktop_size_from_login([b'\0',struct.pack('<i',w),struct.pack('<i',h)])
        with self.assertRaises(ValueError):desktop_size_from_login([b'\0',b'1',b'2'])
