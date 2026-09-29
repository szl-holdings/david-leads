"""Every Hub-writing workflow holds the lock of the asset it writes and one hub pin.

Plan decisions D3 (lock key ``hf-write/<type>/SZLHOLDINGS/<id>``, never
cancel-in-progress) and D6 (one exact ``huggingface_hub`` version). The
version is read from ``requirements-ingestor.txt``, which the regression suite
installs, so the workflows cannot drift from the tested client.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# workflow file -> the one Hub asset it mutates
WRITERS = {
    "hf-deploy.yml": "space/SZLHOLDINGS/david-leads",
    "rotate-space-credentials.yml": "space/SZLHOLDINGS/david-leads",
    "federal-refresh.yml": "dataset/SZLHOLDINGS/david-leads-data",
}
HUB_SECRET = re.compile(r"secrets\.(?:HF_[A-Z0-9_]*|HUGGING[A-Z0-9_]*)")
HUB_INSTALL = re.compile(r"huggingface[_-]hub(?P<spec>[^\s\"'\]]*)", re.IGNORECASE)


def tested_hub_version() -> str:
    for line in (ROOT / "requirements-ingestor.txt").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"huggingface_hub==([0-9][0-9A-Za-z.+-]*)", line.strip())
        if match:
            return match.group(1)
    raise AssertionError("requirements-ingestor.txt must pin huggingface_hub exactly")


def workflow_lock(text: str) -> tuple[str, str]:
    match = re.search(
        r"(?m)^concurrency:\n  group: (?P<group>[^\n]+)\n  cancel-in-progress: (?P<cancel>\w+)\n",
        text,
    )
    if match is None:
        raise AssertionError("workflow-level concurrency block missing")
    return match.group("group"), match.group("cancel")


class HubWriteLockTests(unittest.TestCase):
    def test_every_hub_secret_reader_is_a_declared_writer(self) -> None:
        readers = sorted(
            path.name
            for path in WORKFLOWS.glob("*.y*ml")
            if HUB_SECRET.search(path.read_text(encoding="utf-8"))
        )
        self.assertEqual(readers, sorted(WRITERS))

    def test_each_writer_holds_its_asset_lock(self) -> None:
        for name, asset in WRITERS.items():
            with self.subTest(workflow=name):
                group, cancel = workflow_lock((WORKFLOWS / name).read_text(encoding="utf-8"))
                self.assertEqual(group, f"hf-write/{asset}")
                self.assertEqual(cancel, "false")

    def test_space_writers_share_one_lock(self) -> None:
        # A credential rotation restarts the Space, so it must not interleave
        # with a deploy of the same Space.
        groups = {
            workflow_lock((WORKFLOWS / name).read_text(encoding="utf-8"))[0]
            for name, asset in WRITERS.items()
            if asset.startswith("space/")
        }
        self.assertEqual(groups, {"hf-write/space/SZLHOLDINGS/david-leads"})

    def test_no_other_workflow_claims_a_hub_write_lock(self) -> None:
        for path in WORKFLOWS.glob("*.y*ml"):
            if path.name in WRITERS:
                continue
            with self.subTest(workflow=path.name):
                self.assertNotIn("hf-write/", path.read_text(encoding="utf-8"))

    def test_every_hub_install_is_the_tested_exact_version(self) -> None:
        expected = f"=={tested_hub_version()}"
        seen = 0
        for path in WORKFLOWS.glob("*.y*ml"):
            for match in HUB_INSTALL.finditer(path.read_text(encoding="utf-8")):
                spec = match.group("spec")
                if not spec or spec.startswith(("import", ".")):
                    continue  # "from huggingface_hub import ..." and module paths
                seen += 1
                with self.subTest(workflow=path.name, spec=spec):
                    self.assertEqual(spec, expected)
        self.assertGreaterEqual(seen, len(WRITERS))


if __name__ == "__main__":
    unittest.main()
