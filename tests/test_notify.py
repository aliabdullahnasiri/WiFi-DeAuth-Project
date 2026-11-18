"""Regression coverage for MQTT configuration without network or wireless I/O."""

import os
import unittest
from unittest.mock import patch

from func import notify


class NotifyTests(unittest.TestCase):
    """Exercise anonymous, authenticated, and incomplete notification settings."""

    def setUp(self):
        """Isolate broker settings from the developer's environment."""
        self.enterContext(
            patch.dict(
                os.environ,
                {"BROKER_IP": "broker.example.invalid", "TOPIC": "lab/status"},
                clear=True,
            )
        )

    def test_missing_or_empty_credentials_work_with_paho(self):
        """Use the real Paho publisher with its network client replaced."""
        for credentials in ({}, {"USERNAME": "", "PASSWORD": ""}):
            with self.subTest(credentials=credentials):
                with patch.dict(os.environ, credentials):
                    with patch("paho.mqtt.publish.paho.Client") as client:
                        self.assertEqual(notify("observed"), 0)
                        client.return_value.username_pw_set.assert_not_called()
                        client.return_value.connect.assert_called_once()
                        client.return_value.loop_forever.assert_called_once()

    def test_configured_credentials_are_forwarded(self):
        """Preserve authenticated publishing, including optional passwords."""
        for password in (None, "", "test-password"):
            with self.subTest(password=password):
                credentials = {"USERNAME": "test-user"}
                if password is not None:
                    credentials["PASSWORD"] = password
                with patch.dict(os.environ, credentials):
                    with patch("func.publish.single") as publish:
                        self.assertEqual(notify("observed"), 0)
                        publish.assert_called_once_with(
                            topic="lab/status",
                            payload="observed",
                            hostname="broker.example.invalid",
                            auth={"username": "test-user", "password": password},
                        )

    def test_incomplete_broker_settings_skip_publishing(self):
        """Missing or empty required settings must not reach the publisher."""
        for settings in (
            {},
            {"BROKER_IP": "broker.example.invalid"},
            {"TOPIC": "lab/status"},
            {"BROKER_IP": "", "TOPIC": "lab/status"},
            {"BROKER_IP": "broker.example.invalid", "TOPIC": ""},
        ):
            with self.subTest(settings=settings):
                with patch.dict(os.environ, settings, clear=True):
                    with patch("func.publish.single") as publish:
                        with patch("func.logger.warning") as warning:
                            self.assertEqual(notify("observed"), 1)
                            publish.assert_not_called()
                            warning.assert_called_once_with(
                                "Skipping MQTT notification: set BROKER_IP and TOPIC."
                            )

    def test_password_without_username_skips_publishing(self):
        """Do not silently use anonymous access for incomplete credentials."""
        with patch.dict(os.environ, {"PASSWORD": "test-password"}):
            with patch("func.publish.single") as publish:
                with patch("func.logger.warning") as warning:
                    self.assertEqual(notify("observed"), 1)
                    publish.assert_not_called()
                    warning.assert_called_once_with(
                        "Skipping MQTT notification: PASSWORD requires USERNAME."
                    )

    def test_connection_refusal_returns_failure(self):
        """Retain the existing nonfatal handling of a refused connection."""
        with patch("func.publish.single", side_effect=ConnectionRefusedError):
            with patch("func.console.print"):
                self.assertEqual(notify("observed"), 1)


if __name__ == "__main__":
    unittest.main()
