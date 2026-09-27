"""Platform-deterministic maths for the Study 2 engine (v2).

Maths libraries differ between platforms in the last bit of `exp`, `erfc`
and `hypot` (Apple's libm vs glibc, NEON vs AVX code paths). Those bits reach
the planner's comparisons, so the same mission could take a different route
on another computer (NUMERICAL_REPRODUCIBILITY.md). IEEE-754 guarantees that
+, -, *, / and sqrt are correctly rounded, so functions built only from them,
evaluated in a fixed order, give the same bits everywhere. This module
provides such implementations and a switch:

    with deterministic(True):      # run_mission turns it on for engine v2
        ... numerics.exp / erfc / hypot are the deterministic versions ...

Outside the switch (engine v1) they are the library functions, exactly as
before, so Study 1 still reproduces bit for bit.

Accuracy against the library versions is tested (tests/test_numerics.py):
a few units in the last place for exp, hypot; relative error < 1e-13 for erfc
over the range the planner uses. Mathematically the functions are the same;
only the last bits differ, identically on every platform.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from contextvars import ContextVar

import numpy as np

_DETERMINISTIC: ContextVar[bool] = ContextVar("exonaut_deterministic_math", default=False)

# ln 2 split so that k * _LN2_HI is exact for the k used here (Cody-Waite)
_LN2_HI = 6.93147180369123816490e-01
_LN2_LO = 1.90821492927058770002e-10
_INV_LN2 = 1.44269504088896338700e00
_SQRT_PI = 1.7724538509055160273
_TWO_OVER_SQRT_PI = 1.1283791670955125739


@contextmanager
def deterministic(enabled: bool):
    token = _DETERMINISTIC.set(bool(enabled))
    try:
        yield
    finally:
        _DETERMINISTIC.reset(token)


def is_deterministic() -> bool:
    return _DETERMINISTIC.get()


def det_exp(x: float) -> float:
    """exp(x) from +, -, *, / and exact scaling by powers of two."""
    x = float(x)
    if x != x:
        return x
    if x > 709.78:
        return math.inf
    if x < -745.2:
        return 0.0
    k = int(round(x * _INV_LN2))
    r = (x - k * _LN2_HI) - k * _LN2_LO  # |r| <= ~0.35
    p = 1.0
    for n in range(14, 0, -1):  # Taylor series in Horner form; error < 1e-18
        p = 1.0 + r * p / n
    return math.ldexp(p, k)


def det_erfc(x: float) -> float:
    """Complementary error function from det_exp and basic arithmetic.

    x < 2: erfc = 1 - erf with erf(x) = (2/sqrt(pi)) e^{-x^2} sum 2^n x^{2n+1}/(2n+1)!!,
    a series of positive terms (no cancellation). x >= 2: the continued fraction
    erfc(x) = e^{-x^2} / (sqrt(pi) (x + 1/2/(x + 1/(x + 3/2/(x + ...))))),
    evaluated with the modified Lentz method.
    """
    x = float(x)
    if x < 0.0:
        return 2.0 - det_erfc(-x)
    if x < 2.0:
        term = x
        total = x
        x2 = x * x
        n = 0
        while True:
            n += 1
            term = term * 2.0 * x2 / (2 * n + 1)
            total += term
            if term <= 1e-17 * total:
                break
        return 1.0 - _TWO_OVER_SQRT_PI * det_exp(-x2) * total
    if x > 27.3:  # e^{-x^2} underflows
        return 0.0
    tiny = 1e-300
    f = x
    c = f
    d = 0.0
    for j in range(1, 500):
        a = 0.5 * j
        d = x + a * d
        d = tiny if d == 0.0 else d
        c = x + a / c
        c = tiny if c == 0.0 else c
        d = 1.0 / d
        delta = c * d
        f *= delta
        if abs(delta - 1.0) < 1e-16:
            break
    return det_exp(-x * x) / (_SQRT_PI * f)


def det_hypot(a: float, b: float) -> float:
    """sqrt(a^2 + b^2); sqrt is correctly rounded under IEEE-754."""
    a, b = float(a), float(b)
    return math.sqrt(a * a + b * b)


# --- dispatching versions used by the engine -------------------------------


def exp(x):
    """Scalar or array exp: deterministic under the v2 switch, else numpy's."""
    if _DETERMINISTIC.get():
        if np.ndim(x):
            return np.array([det_exp(v) for v in np.asarray(x, dtype=float).ravel()]).reshape(
                np.shape(x)
            )
        return det_exp(x)
    return np.exp(x)


_ERFC_CACHE: dict[float, float] = {}


def erfc(x: float) -> float:
    """Scalar erfc: deterministic under the v2 switch, else math.erfc."""
    if _DETERMINISTIC.get():
        cached = _ERFC_CACHE.get(x)
        if cached is None:
            if len(_ERFC_CACHE) > 500_000:
                _ERFC_CACHE.clear()
            cached = _ERFC_CACHE[x] = det_erfc(x)
        return cached
    return math.erfc(x)


def hypot(a, b):
    """Scalar or array hypot: deterministic under the v2 switch, else numpy's."""
    if _DETERMINISTIC.get():
        if np.ndim(a) or np.ndim(b):
            a_arr, b_arr = np.broadcast_arrays(np.asarray(a, float), np.asarray(b, float))
            return np.sqrt(a_arr * a_arr + b_arr * b_arr)
        return det_hypot(a, b)
    return np.hypot(a, b)
