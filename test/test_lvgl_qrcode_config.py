#!/usr/bin/env python3
"""Regression tests for target/simulator LVGL QR configuration parity."""

from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "cmake" / "torget_lvgl_qrcode_guard.cmake"
ROOT_CMAKE = ROOT / "CMakeLists.txt"
SDKCONFIG_DEFAULTS = ROOT / "sdkconfig.defaults"
SIM_CONFIG = ROOT / "sim" / "lv_conf.h"
COMPONENT_CMAKE = ROOT / "components" / "torget_wifi" / "CMakeLists.txt"
SIM_CMAKE = ROOT / "sim" / "CMakeLists.txt"
RUNNER = ROOT / "test" / "run.sh"


def run_guard(enabled: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "check.cmake"
        script.write_text(
            f'include("{GUARD.as_posix()}")\n'
            f'torget_require_lvgl_qrcode("{enabled}")\n',
            encoding="utf-8",
        )
        return subprocess.run(
            ["cmake", "-P", str(script)],
            capture_output=True,
            check=False,
            text=True,
        )


class LvglQrcodeConfigTests(unittest.TestCase):
    def test_disabled_or_missing_generated_config_is_rejected(self) -> None:
        for value in ("n", ""):
            with self.subTest(value=value):
                result = run_guard(value)
                self.assertNotEqual(result.returncode, 0)
                diagnostic = " ".join(
                    (result.stdout + result.stderr).split())
                self.assertIn("LVGL QR support is disabled", diagnostic)
                self.assertIn("sdkconfig is stale", diagnostic)
                self.assertIn("CONFIG_LV_USE_QRCODE=y", diagnostic)
                self.assertIn("idf.py reconfigure && idf.py build",
                              diagnostic)

    def test_enabled_generated_config_is_accepted(self) -> None:
        result = run_guard("y")
        self.assertEqual(result.returncode, 0,
                         result.stdout + result.stderr)

    def test_target_default_and_simulator_config_are_aligned(self) -> None:
        defaults = SDKCONFIG_DEFAULTS.read_text(encoding="utf-8").splitlines()
        simulator = SIM_CONFIG.read_text(encoding="utf-8")
        self.assertIn("CONFIG_LV_USE_QRCODE=y", defaults)
        self.assertIn("#define LV_USE_QRCODE 1", simulator)

    def test_guard_and_payload_are_wired_into_every_build(self) -> None:
        root_cmake = ROOT_CMAKE.read_text(encoding="utf-8")
        component = COMPONENT_CMAKE.read_text(encoding="utf-8")
        simulator = SIM_CMAKE.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")

        self.assertIn(
            'include("${CMAKE_CURRENT_SOURCE_DIR}/cmake/'
            'torget_lvgl_qrcode_guard.cmake")',
            root_cmake,
        )
        self.assertIn(
            'torget_require_lvgl_qrcode("${CONFIG_LV_USE_QRCODE}")',
            root_cmake,
        )
        self.assertIn('"wifi_qr_payload.c"', component)
        self.assertIn("../components/torget_wifi/wifi_qr_payload.c",
                      simulator)
        self.assertEqual(runner.count("test_wifi_qr_payload.c"), 1)
        self.assertEqual(runner.count("test_lvgl_qrcode_config.py"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
