"""Workbench package marker and secure local runtime defaults."""

import os

# Workbench has no authentication/authorization boundary. Keep package-mode and
# normal launcher imports localhost-only unless a trusted operator explicitly
# opts into office-LAN sharing with WORKBENCH_HOST=0.0.0.0 (or another address).
os.environ.setdefault("WORKBENCH_HOST", "127.0.0.1")
