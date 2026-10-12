"""Boundary fixtures derived from R198's recovered CIL branches."""
import unittest
from uv_reference import version_equal_or_greater


class VersionTests(unittest.TestCase):
    def test_component_precedence_and_thresholds(self):
        for current, minimum, expected in [
            ('6.6.133', '6.6.0', True),
            ('6.4.24', '6.4.24', True),
            ('6.4.23', '6.4.24', False),
            ('6.5.999', '6.6.0', False),
            ('7.0.0', '6.999.999', True),
            ('5.999.999', '6.0.0', False),
            ('6.10.0', '6.9.999', True),
        ]:
            with self.subTest(current=current, minimum=minimum):
                self.assertEqual(version_equal_or_greater(current, minimum), expected)

    def test_original_ignores_fourth_component(self):
        self.assertTrue(version_equal_or_greater('6.6.0.0', '6.6.0.999'))
        self.assertTrue(version_equal_or_greater('6.6.0.ignored', '6.6.0'))
        self.assertFalse(version_equal_or_greater('6.6', '6.6.0'))

    def test_supported_domain_and_short_circuit(self):
        for current in ['6.x.0', '6.6.-1', '6.6.9223372036854775808']:
            with self.assertRaises(ValueError):
                version_equal_or_greater(current, '6.6.0')
        # Later components are never parsed after an earlier decisive branch.
        self.assertTrue(version_equal_or_greater('7.unused.unused', '6.6.0'))


if __name__ == '__main__':
    unittest.main()
