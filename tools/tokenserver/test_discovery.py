import logging
import socket
import sys
import types
import unittest
from unittest import mock

from . import discovery


class _FakeZeroconf:
    instances = []

    def __init__(self):
        self.registered = []
        self.unregistered = []
        self.closed = False
        self.instances.append(self)

    def register_service(self, info, allow_name_change=False):
        self.registered.append((info, allow_name_change))

    def unregister_service(self, info):
        self.unregistered.append(info)

    def close(self):
        self.closed = True


class _FakeServiceInfo:
    def __init__(self, type_, name, **kwargs):
        self.type = type_
        self.name = name
        self.kwargs = kwargs


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        _FakeZeroconf.instances.clear()
        self.logger = logging.getLogger("test-discovery")

    def test_safe_label_is_bounded_and_dns_compatible(self):
        self.assertEqual(discovery._safe_dns_label("PC å Ä / Test"),
                         "pc-test")
        self.assertLessEqual(len(discovery._safe_dns_label("x" * 100)), 48)
        self.assertEqual(discovery._safe_dns_label("---"), "host")

    def test_addresses_exclude_loopback_and_link_local(self):
        rows = [
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("127.0.0.1", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("169.254.1.2", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("192.168.1.8", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("192.168.1.8", 0)),
        ]
        with mock.patch.object(socket, "getaddrinfo", return_value=rows):
            self.assertEqual(discovery._local_ipv4_addresses(),
                             (socket.inet_aton("192.168.1.8"),))

    def test_missing_dependency_is_nonfatal(self):
        advertiser = discovery.DiscoveryAdvertiser(self.logger)
        with mock.patch.dict(sys.modules, {"zeroconf": None}):
            self.assertFalse(advertiser.start(8737))
        self.assertEqual(advertiser.status, "unavailable")
        self.assertEqual(advertiser.reason, "dependency-missing")

    def test_registers_only_protocol_and_port_then_closes(self):
        fake_module = types.SimpleNamespace(
            Zeroconf=_FakeZeroconf, ServiceInfo=_FakeServiceInfo)
        advertiser = discovery.DiscoveryAdvertiser(self.logger)
        with mock.patch.dict(sys.modules, {"zeroconf": fake_module}), \
                mock.patch.object(discovery, "_local_ipv4_addresses",
                                  return_value=(socket.inet_aton("10.0.0.2"),)), \
                mock.patch.object(socket, "gethostname", return_value="My PC"):
            self.assertTrue(advertiser.start(8737))
        self.assertEqual(advertiser.status, "ready")
        zc = _FakeZeroconf.instances[-1]
        info, allow_change = zc.registered[0]
        self.assertTrue(allow_change)
        self.assertEqual(info.type, discovery.SERVICE_TYPE)
        self.assertEqual(info.kwargs["port"], 8737)
        self.assertEqual(info.kwargs["properties"], {b"v": b"1"})
        self.assertNotIn("rev", info.kwargs["properties"])
        advertiser.stop()
        self.assertEqual(zc.unregistered, [info])
        self.assertTrue(zc.closed)

    def test_invalid_port_fails_closed(self):
        advertiser = discovery.DiscoveryAdvertiser(self.logger)
        self.assertFalse(advertiser.start(0))
        self.assertEqual(advertiser.status, "error")


if __name__ == "__main__":
    unittest.main()
