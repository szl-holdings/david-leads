# SPDX-License-Identifier: Apache-2.0
"""Retired prototype entry points cannot publish arbitrary raw records."""
import pytest
from tools.ingestor.usaspending_ingestor import parse_usaspending, run_usaspending
from tools.ingestor.usaspending_ingestor_cli import main


@pytest.mark.parametrize("payload", [b"", b"DOT_NUMBER,LEGAL_NAME,EMAIL\n123,Fixture LLC,private@example.test\n"])
def test_raw_legacy_ingestion_is_explicitly_retired(payload):
    for operation in (parse_usaspending, run_usaspending):
        with pytest.raises(ValueError, match="retired.*frontier_refresh_cli"):
            operation(payload)


def test_retired_cli_does_not_read_or_create_files(tmp_path, capsys):
    destination = tmp_path / "must-not-exist"
    assert main(["--zip", "nonexistent", "--out", str(destination)]) == 2
    assert not destination.exists()
    assert "--lane usaspending" in capsys.readouterr().err
