# SPDX-License-Identifier: Apache-2.0
"""Retired prototype entry points cannot publish arbitrary raw records."""
import pytest
from tools.ingestor.motus_ingestor import parse_motus_carrier, run_motus
from tools.ingestor.motus_ingestor_cli import main


@pytest.mark.parametrize("payload", [b"", b"DOT_NUMBER,LEGAL_NAME,EMAIL\n123,Fixture LLC,private@example.test\n"])
def test_raw_legacy_ingestion_is_explicitly_retired(payload):
    for operation in (parse_motus_carrier, run_motus):
        with pytest.raises(ValueError, match="retired.*frontier_refresh_cli"):
            operation(payload)


def test_retired_cli_does_not_read_or_create_files(tmp_path, capsys):
    destination = tmp_path / "must-not-exist"
    assert main(["--zip", "nonexistent", "--out", str(destination)]) == 2
    assert not destination.exists()
    assert "--lane fmcsa" in capsys.readouterr().err
