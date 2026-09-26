"""Where Study 1's exact reproduction is guaranteed.

Study 1 was generated on macOS arm64 (its metadata records the platform). The
same code and pinned library versions on Linux x86-64 reproduce most but not
all missions exactly: floating-point results differ in the last bits between
platforms, and in some missions that flips a route choice
(docs/RESEARCH_LOG.md, 2026-09-26). Tests that demand bit-exact reproduction
of committed rows therefore run on the reference platform and are skipped,
with this reason, elsewhere.
"""

import platform

import pytest

ON_REFERENCE_PLATFORM = platform.system() == "Darwin" and platform.machine() == "arm64"

reference_platform_only = pytest.mark.skipif(
    not ON_REFERENCE_PLATFORM,
    reason="bit-exact Study 1 reproduction is guaranteed only on the generating platform "
    "(macOS arm64); see RESEARCH_LOG 2026-09-26",
)
