# SPDX-License-Identifier: Apache-2.0
"""Fail closed for the retired raw-file CLI; no input is read or output written."""
import sys
from .dol_5500_ingestor import RETIRED_MESSAGE


def main(argv=None) -> int:
    print(RETIRED_MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
