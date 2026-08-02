from __future__ import annotations

import os

from moontransfer_android.android_runtime import android_files_dir
from moontransfer_android.transfer_service import TransferServiceRuntime


def main() -> None:
    session_id = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    cache_root = android_files_dir() / "transfer-cache"
    TransferServiceRuntime(cache_root).run(session_id)


if __name__ == "__main__":
    main()
