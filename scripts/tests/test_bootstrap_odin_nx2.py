"""Offline safety and path checks for the Odin NX2 one-command bootstrap."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "bootstrap-odin-nx2.py"
SPEC = importlib.util.spec_from_file_location("bootstrap_odin_nx2", SCRIPT)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def test_toolbox_names_are_exact(self):
        self.assertNotIn("lichii-debug", bootstrap.toolbox_names("123 lichii-debug-old"))
        self.assertIn("lichii-debug", bootstrap.toolbox_names("CONTAINER ID NAME\n123 lichii-debug"))

    def test_existing_executable_preserved_without_provision_or_network(self):
        with tempfile.TemporaryDirectory() as d:
            binary = Path(d) / "working"
            binary.write_bytes(b"working executable")
            binary.chmod(0o700)
            active = Path(d) / "lichii-odin"
            active.symlink_to(binary)
            with mock.patch.object(bootstrap, "ACTIVE", active), \
                 mock.patch.object(bootstrap.platform, "machine", return_value="aarch64"), \
                 mock.patch.object(bootstrap, "ensure_box") as provision, \
                 mock.patch.object(bootstrap, "fetch_installer") as download:
                bootstrap.install()
                provision.assert_not_called()
                download.assert_not_called()
                self.assertEqual(active.resolve(), binary)

    def test_existing_regular_file_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            active = Path(d) / "lichii-odin"
            active.write_bytes(b"user data")
            with mock.patch.object(bootstrap, "ACTIVE", active):
                with self.assertRaises(SystemExit):
                    bootstrap.working_installation()
            self.assertEqual(active.read_bytes(), b"user data")

    def test_broken_symlink_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as d:
            active = Path(d) / "lichii-odin"
            active.symlink_to(Path(d) / "missing")
            with mock.patch.object(bootstrap, "ACTIVE", active):
                with self.assertRaises(SystemExit):
                    bootstrap.working_installation()
            self.assertTrue(active.is_symlink())

    def test_reject_wrong_existing_toolbox(self):
        with mock.patch.object(bootstrap.shutil, "which", return_value="/usr/bin/toolbox"), \
             mock.patch.object(bootstrap, "has_box", return_value=True), \
             mock.patch.object(bootstrap, "box_version", return_value="fedora:43"), \
             mock.patch.object(bootstrap, "run") as runner:
            with self.assertRaises(SystemExit):
                bootstrap.ensure_box()
            runner.assert_not_called()

    def test_creates_missing_fedora44_toolbox_only(self):
        with mock.patch.object(bootstrap.shutil, "which", return_value="/usr/bin/toolbox"), \
             mock.patch.object(bootstrap, "has_box", side_effect=[False, True]), \
             mock.patch.object(bootstrap, "box_version", return_value="fedora:44"), \
             mock.patch.object(bootstrap, "run") as runner:
            bootstrap.ensure_box()
            self.assertEqual(runner.call_count, 1)
            self.assertEqual(runner.call_args.args[:3], ("toolbox", "--assumeyes", "create"))
            self.assertEqual(runner.call_args.args[-2:], ("--image", bootstrap.IMAGE))

    def test_install_packages_uses_container_only(self):
        with mock.patch.object(bootstrap, "run") as runner:
            bootstrap.install_dependencies()
            args = runner.call_args.args
            self.assertEqual(args[:7], ("toolbox", "run", "--container", "lichii-debug",
                                        "sudo", "dnf", "install"))
            self.assertIn("qt6-qtwayland", args)
            self.assertIn("mesa-vulkan-drivers", args)

    def test_rejects_release_asset_with_bad_checksum(self):
        payload = b"tampered release installer"
        release_json = ('{"tag_name":"' + bootstrap.TAG + '","draft":false,"assets":[' +
                        '{"name":"' + bootstrap.ASSET + '","browser_download_url":"' +
                        'https://github.com/' + bootstrap.REPO + '/releases/download/' +
                        bootstrap.TAG + '/' + bootstrap.ASSET + '"}]}').encode()
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "installer.py"
            with mock.patch.object(bootstrap.urllib.request, "urlopen",
                                   side_effect=[io.BytesIO(release_json), io.BytesIO(payload)]):
                with self.assertRaises(SystemExit):
                    bootstrap.fetch_installer(target)

    def test_lsfg_repair_is_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            own = Path(d) / "steam/Lossless.dll"
            own.parent.mkdir()
            own.write_bytes(b"MZ" + b"testing" * 25)
            dll = Path(d) / "lichii/lossless/Lossless.dll"
            with mock.patch.object(bootstrap, "STEAM_DLL", own), \
                 mock.patch.object(bootstrap, "DLL", dll):
                bootstrap.repair_lossless()
                self.assertEqual(dll.read_bytes(), own.read_bytes())
                own.write_bytes(b"MZnew content")
                bootstrap.repair_lossless()
                self.assertNotEqual(dll.read_bytes(), own.read_bytes())

    def test_repair_does_not_follow_destination_folder_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            own = Path(d) / "steam/Lossless.dll"
            own.parent.mkdir()
            own.write_bytes(b"MZcontent")
            safe = Path(d) / "secure"
            safe.mkdir()
            redirect = Path(d) / "redirect"
            redirect.symlink_to(safe, target_is_directory=True)
            with mock.patch.object(bootstrap, "STEAM_DLL", own), \
                 mock.patch.object(bootstrap, "DLL", redirect / "Lossless.dll"):
                with self.assertRaises(SystemExit):
                    bootstrap.repair_lossless()
            self.assertFalse((safe / "Lossless.dll").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
