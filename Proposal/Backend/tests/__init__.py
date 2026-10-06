"""Marks the backend test suite as a regular package.

Without this file `tests` is a namespace package, and Python resolves a *regular*
package of the same name ahead of it no matter where it sits on sys.path. An
unrelated `tests` package installed in site-packages therefore shadowed this one,
so every module doing `from tests.conftest import ...` failed to import and the
suite could not be collected at all. Declaring the package here makes the repo's
own `tests` win, in the main process and in xdist worker processes alike.
"""
