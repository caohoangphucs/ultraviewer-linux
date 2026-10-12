import unittest
from input_control import mouse_move,mouse_button,mouse_wheel,keyboard,held_key


class InputControlTests(unittest.TestCase):
    def test_observed_notepad_commands(self):
        self.assertEqual(mouse_move(250,200), b'8|||512|||0|||250|||200')
        self.assertEqual(mouse_button('left',True), b'8|||513')
        self.assertEqual(mouse_button('left',False), b'8|||514')
        self.assertEqual(keyboard(85,True), b'8|||256|||85')
        self.assertEqual(keyboard(85,False), b'8|||257|||85')

    def test_wheel_signed_high_word(self):
        self.assertEqual(mouse_wheel(120), b'8|||522|||7864320')
        self.assertEqual(mouse_wheel(-120), b'8|||522|||-7864320')
        for value in (-32769,32768,True):
            with self.assertRaises(ValueError):mouse_wheel(value)

    def test_modifier_release_on_failure(self):
        sent=[]
        with self.assertRaises(RuntimeError):
            with held_key(sent.append,91):raise RuntimeError('action failed')
        self.assertEqual(sent,[b'8|||256|||91',b'8|||257|||91'])


if __name__ == '__main__':unittest.main()
