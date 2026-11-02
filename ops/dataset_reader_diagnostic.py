# SPDX-License-Identifier: Apache-2.0
"""Read-only, aggregate-only preflight for the protected dataset reader.

This qualifies the GitHub environment credential, not the credential installed
in a Space. It never reads organization records or invokes a Space mutation.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable

from app.hf_dataset_transport import (
    READ_TOKEN_ENV,
    dataset_read_token,
    open_dataset_url,
)
from ops.dataset_reader_rotation import (
    DATASET_ID,
    MAX_POINTER_BYTES,
    POINTER_FILES,
    RotationContractError,
    load_pointer_expectations,
    require_dataset_revision,
    require_fine_grained_role,
    require_pointer_sizes,
)


def _reader_api(token: str) -> Any:
    from huggingface_hub import HfApi

    return HfApi(endpoint="https://huggingface.co", token=token)


def diagnose_reader(
    *,
    api_factory: Callable[[str], Any] = _reader_api,
    pointer_opener: Callable[..., Any] = open_dataset_url,
) -> dict[str, Any]:
    """Return fixed booleans only; never relay remote metadata or exceptions."""
    report = {
        "schema": "szl.david-dataset-reader-diagnostic/v1",
        "reader_present": bool(os.environ.get(READ_TOKEN_ENV)),
        "reader_format_valid": False,
        "fine_grained_token": False,
        "dataset_access": False,
        "immutable_revision_valid": False,
        "pointer_metadata_valid": False,
        "pointer_bindings_valid": False,
        "complete": False,
        "runtime_reader_verified": False,
        "credential_values_recorded": False,
        "records_exported": False,
        "space_mutations_performed": False,
    }
    try:
        token = dataset_read_token()
        if token is None:
            return report
        report["reader_format_valid"] = True
        reader = api_factory(token)
        require_fine_grained_role(reader.whoami(token=token))
        report["fine_grained_token"] = True
        info = reader.dataset_info(DATASET_ID, token=token)
        report["dataset_access"] = True
        revision = require_dataset_revision(info.sha)
        report["immutable_revision_valid"] = True
        metadata = reader.get_paths_info(
            DATASET_ID,
            list(POINTER_FILES.values()),
            repo_type="dataset",
            revision=revision,
            token=token,
        )
        sizes = {}
        for entry in metadata:
            if entry.path in sizes:
                raise RotationContractError("duplicate pointer metadata")
            sizes[entry.path] = entry.size
        require_pointer_sizes(sizes)
        report["pointer_metadata_valid"] = True

        with tempfile.TemporaryDirectory(prefix="david-reader-diagnostic-") as tmp:
            paths = {}
            for index, (source_id, filename) in enumerate(POINTER_FILES.items()):
                url = f"https://huggingface.co/datasets/{DATASET_ID}/resolve/{revision}/{filename}"
                with pointer_opener(
                    url,
                    timeout=15,
                    user_agent="SZL-David-Dataset-Reader-Diagnostic/1.0",
                    accept="application/json",
                ) as response:
                    payload = response.read(MAX_POINTER_BYTES + 1)
                if len(payload) != sizes[filename] or len(payload) > MAX_POINTER_BYTES:
                    raise RotationContractError("pointer size mismatch")
                path = Path(tmp) / f"pointer-{index}.json"
                path.write_bytes(payload)
                paths[source_id] = path
            load_pointer_expectations(paths)
        report["pointer_bindings_valid"] = True
        report["complete"] = True
    except Exception:
        # Even an HTTP exception can contain credentials, URLs or records.
        # The last successful boolean is sufficient diagnostic evidence.
        pass
    return report


def main() -> int:
    # SDK diagnostics may contain headers or response bodies. Do not retain or
    # print them even when a caller accidentally enables verbose logging.
    previous_disable = logging.root.manager.disable
    try:
        logging.disable(logging.CRITICAL)
        with open(os.devnull, "w", encoding="utf-8") as sink:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                report = diagnose_reader()
    finally:
        logging.disable(previous_disable)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
