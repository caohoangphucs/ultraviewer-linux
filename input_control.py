"""ASCII input commands recovered from RC40 e3a and b66 (E56–E59).

Call send(payload) with a session relay sender configured unicode_bytes=False.
Coordinates are remote desktop pixels. Keys are Windows virtual-key codes.
"""
from contextlib import contextmanager


def _integer(value, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError('input value outside supported range')
    return str(value)


def mouse_move(x, y):
    return ('8|||512|||0|||' + _integer(x, -32768, 32767) + '|||' +
            _integer(y, -32768, 32767)).encode('ascii')


def mouse_button(button, down):
    events = {'left': (513, 514), 'right': (516, 517), 'middle': (519, 520)}
    if button not in events or not isinstance(down, bool):
        raise ValueError('unsupported mouse button or state')
    return ('8|||' + str(events[button][0 if down else 1])).encode('ascii')


def mouse_wheel(delta):
    # b6a extracts the signed high word of the original packed wParam.
    number = int(_integer(delta, -32768, 32767)) << 16
    return ('8|||522|||' + str(number)).encode('ascii')


def keyboard(vk, down, *, system=False):
    if not isinstance(down, bool) or not isinstance(system, bool):
        raise ValueError('key state must be boolean')
    event = (260 if down else 261) if system else (256 if down else 257)
    return ('8|||' + str(event) + '|||' + _integer(vk, 0, 255)).encode('ascii')


@contextmanager
def held_key(send, vk, *, system=False):
    """Release a successfully pressed modifier even when an action fails."""
    send(keyboard(vk, True, system=system))
    try:
        yield
    finally:
        send(keyboard(vk, False, system=system))
