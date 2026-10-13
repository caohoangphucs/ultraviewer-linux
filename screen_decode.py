"""Decode observed RGB555 Zstandard rectangle updates on Linux.

Scope: kind1, UInt16 x/y/w/h rectangles, Zstandard pixel stream, RGB555.
JPEG, cache references and other color depths require separate handling.
"""
import ctypes
import ctypes.util
import struct
from PIL import Image


class ZstdDictionaryDecoder:
    def __init__(self, dictionary, max_output=64 * 1024 * 1024):
        self.dictionary = bytes(dictionary)
        self.max_output = max_output
        name = ctypes.util.find_library('zstd')
        if not name:
            raise RuntimeError('libzstd is required')
        self.lib = ctypes.CDLL(name)
        self.lib.ZSTD_createDCtx.restype = ctypes.c_void_p
        self.lib.ZSTD_freeDCtx.argtypes = [ctypes.c_void_p]
        self.lib.ZSTD_decompress_usingDict.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
        self.lib.ZSTD_decompress_usingDict.restype = ctypes.c_size_t
        self.lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
        self.lib.ZSTD_isError.restype = ctypes.c_uint

    def decompress(self, payload, expected_size):
        if not 0 < expected_size <= self.max_output:
            raise ValueError('decoded image exceeds allocation policy')
        payload = bytes(payload)
        output = ctypes.create_string_buffer(expected_size)
        context = self.lib.ZSTD_createDCtx()
        if not context:
            raise MemoryError('cannot create Zstandard context')
        try:
            count = self.lib.ZSTD_decompress_usingDict(context, output, expected_size,
                payload, len(payload), self.dictionary, len(self.dictionary))
            if self.lib.ZSTD_isError(count) or count != expected_size:
                raise ValueError('Zstandard decoding failed or image size differs')
            return output.raw
        finally:
            self.lib.ZSTD_freeDCtx(context)


def apply_rgb555_update(canvas, fields, decoder):
    """Validate every rectangle and decode before modifying the destination."""
    if len(fields) < 5 or not fields[0] or fields[0][0] != 1:
        raise ValueError('expected kind1 screen update')
    if not fields[1] or len(fields[1]) % 8:
        raise ValueError('expected UInt16 x/y/w/h rectangle records')
    if not fields[2].startswith(b'\x28\xb5\x2f\xfd'):
        raise ValueError('screen codec is outside supported Zstandard subset')
    if any(fields[5:]):
        raise ValueError('additional screen operations are not supported yet')
    rectangles = list(struct.iter_unpack('<HHHH', fields[1]))
    for x, y, width, height in rectangles:
        if not width or not height or x + width > canvas.width or y + height > canvas.height:
            raise ValueError('screen rectangle outside canvas')
    raw = decoder.decompress(fields[2], sum(w*h*2 for x,y,w,h in rectangles))
    tiles = []
    offset = 0
    for x, y, width, height in rectangles:
        length = width * height * 2
        tile = Image.frombytes('RGB', (width,height), raw[offset:offset+length],
                               'raw', 'BGR;15', 0, 1)
        tiles.append((tile,(x,y)))
        offset += length
    for tile, position in tiles:
        canvas.paste(tile, position)
    return len(rectangles)


class RGB555Screen:
    """Stateful observed RGB555 path, including tile-cache references/additions.

    Field mapping follows VRecordReader.ManipulatePacket (13a2) and drawer
    constructor c8b; worker c65 consumes references before pixel updates and
    saves cache additions afterwards. BitBlt remains an explicit
    unsupported operation rather than being silently dropped.
    """
    def __init__(self, size, decoder, *, cache_limit=1000, block_size=32):
        from collections import OrderedDict
        if not isinstance(cache_limit, int) or cache_limit < 1:
            raise ValueError('cache limit must be positive')
        self.canvas = Image.new('RGB', size)
        self.decoder = decoder
        self.cache = OrderedDict()
        if not isinstance(block_size,int) or block_size <= 0:
            raise ValueError('JPEG block size must be positive')
        self.block_size = block_size
        self.cache_limit = cache_limit

    def apply(self, fields):
        if len(fields) != 11 or not fields[0] or fields[0][0] != 1:
            raise ValueError('expected eleven-field kind1 update')
        if fields[5]:
            raise ValueError('BitBlt screen operations are not supported yet')
        if len(fields[9]) % 8 or len(fields[10]) % 12:
            raise ValueError('invalid screen cache record length')
        canvas = self.canvas.copy()
        cache = self.cache.copy()
        def bounds(x,y,w,h):
            if w<=0 or h<=0 or x<0 or y<0 or x+w>canvas.width or y+h>canvas.height:
                raise ValueError('cache rectangle outside canvas')
        count = 0
        if fields[6]:
            if len(fields[6]) < 10 or (len(fields[6])-10) % 8:
                raise ValueError('invalid scroll-copy record length')
            delta,x,y,w,h = struct.unpack_from('<hhhhh',fields[6])
            bounds(x,y,w,h)
            # c65 IL024e..0278 copies old screen into an intermediate bitmap
            # at (x,y-delta), then IL0293..0302 restores listed subrectangles.
            shifted = Image.new('RGB',canvas.size)
            shifted.paste(canvas.crop((x,y,x+w,y+h)),(x,y-delta))
            for rx,ry,rw,rh in struct.iter_unpack('<hhhh',fields[6][10:]):
                bounds(rx,ry,rw,rh)
                if rx<x or rx+rw>x+w or ry<y-delta or ry+rh>y-delta+h:
                    raise ValueError('scroll-copy references uncopied intermediate pixels')
                canvas.paste(shifted.crop((rx,ry,rx+rw,ry+rh)),(rx,ry))
                count += 1
        for x,y,key in struct.iter_unpack('<hhi', fields[9]):
            if key not in cache:
                raise ValueError('screen cache reference is missing')
            tile = cache[key]
            bounds(x,y,tile.width,tile.height)
            canvas.paste(tile,(x,y))
            cache.move_to_end(key)
            count += 1
        if fields[7] or fields[8]:
            import io
            from PIL import ImageOps
            from uv_reference import atlas_layout
            if not fields[7].startswith(b'\xff\xd8') or not fields[8] or len(fields[8]) % 8:
                raise ValueError('invalid JPEG atlas fields')
            with Image.open(io.BytesIO(fields[7])) as source:
                if source.format != 'JPEG' or source.width*source.height > 32*1024*1024:
                    raise ValueError('JPEG atlas outside allocation policy')
                # Native TJFLAG_BOTTOMUP then ordinal60 reads increasing rows.
                atlas = ImageOps.flip(source.convert('RGB'))
            rectangles = list(struct.iter_unpack('<hhhh',fields[8]))
            for x,y,w,h in rectangles:bounds(x,y,w,h)
            for x,y,w,h,sx,sy in atlas_layout(rectangles,self.block_size,atlas.height):
                if sx+w>atlas.width or sy+h>atlas.height:
                    raise ValueError('JPEG tile outside atlas')
                canvas.paste(atlas.crop((sx,sy,sx+w,sy+h)),(x,y))
                count += 1
        if fields[1] and fields[2]:
            pixels = list(fields)
            pixels[5:] = [b''] * 6
            count += apply_rgb555_update(canvas,pixels,self.decoder)
        for x,y,w,h,key in struct.iter_unpack('<hhhhi', fields[10]):
            bounds(x,y,w,h)
            if key not in cache:
                cache[key] = canvas.crop((x,y,x+w,y+h))
        while len(cache)>self.cache_limit:
            cache.popitem(last=False)
        self.canvas = canvas
        self.cache = cache
        return count


def desktop_size_from_login(fields):
    """Read partner desktop width/height from kind0 Int32LE fields1/2."""
    if len(fields)<3 or not fields[0] or fields[0][0]!=0 or len(fields[1])!=4 or len(fields[2])!=4:
        raise ValueError('invalid login desktop dimensions')
    width,height=(int.from_bytes(v,'little',signed=True) for v in fields[1:3])
    if not 0<width<=8192 or not 0<height<=8192 or width*height>32*1024*1024:
        raise ValueError('partner desktop dimensions outside allocation limit')
    return width,height
