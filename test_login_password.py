"""Offline compatibility fixtures; no endpoint or real credentials used."""
import unittest
from uv_reference import login_password_fields, build_login_with_password


class LoginPasswordTests(unittest.TestCase):
    def test_type0_against_openssl_digest_fixtures_and_wire_positions(self):
        # Independently generated with OpenSSL MD5 on the two ASCII preimages.
        primary = "63867665cb0fd85445db63a1b2bae1a3"
        secondary = "8d9b56d443454f7f8b2b31912d142693"
        auth = login_password_fields("test-password", 0, salt="12345678",
                                     ansi_codec="cp1252")
        self.assertEqual((auth.salt, auth.primary, auth.secondary),
                         ("12345678", primary, secondary))
        fields = ["metadata" + str(i) for i in range(22)]
        wire = build_login_with_password(fields, password="test-password",
                                        password_type=0, salt="12345678",
                                        ansi_codec="cp1252")
        decoded = wire.decode("utf-16le").split(":")
        self.assertEqual(len(decoded), 23)
        self.assertEqual(decoded[0], "login")
        self.assertEqual([decoded[i + 1] for i in (0, 1, 12)],
                         ["12345678", primary, secondary])
        for i in set(range(22)) - {0, 1, 12}:
            self.assertEqual(decoded[i + 1], fields[i])
        self.assertEqual(fields[0], "metadata0")

    def test_nonzero_type_uses_unhashed_string_and_space_salt(self):
        for kind in (1, -1, 2147483647):
            auth = login_password_fields("alternate-value", kind, salt=None,
                                         ansi_codec="cp1252")
            self.assertEqual((auth.salt, auth.primary, auth.secondary),
                             (" " * 32, "alternate-value", "alternate-value"))

    def test_type0_rejects_missing_non_ascii_and_wrong_length_salts(self):
        for salt in (None, "1234567", "123456789", "abcdefgh", "１２３４５６７８"):
            with self.assertRaises(ValueError):
                login_password_fields("test-password", 0, salt=salt,
                                      ansi_codec="cp1252")


if __name__ == "__main__":
    unittest.main()
