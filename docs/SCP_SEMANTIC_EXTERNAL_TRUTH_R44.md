# Semantic external-truth evidence for R44 BareExceptPass

## Claim under test

The candidate transformation `except: pass` -> `except Exception: pass` is not universally semantic-equivalent. It can agree for ordinary `Exception` subclasses while changing behavior for system-level exceptions derived directly from `BaseException`.

## Independent sources

The Python Language Reference states that an expression-less `except` clause, when present, must be last and **matches any exception**. Source: [Python Language Reference — except clause](https://docs.python.org/3/reference/compound_stmts.html#the-except-clause).

The Python built-in exceptions documentation states that `BaseException` is the base class for all built-in exceptions, while `Exception` contains built-in non-system-exiting exceptions. The same documentation states that `KeyboardInterrupt` and `SystemExit` inherit directly from `BaseException` so they are not accidentally caught by code catching `Exception`. Source: [Python Built-in Exceptions](https://docs.python.org/3/library/exceptions.html).

Ruff rule E722 independently describes the same risk: a bare `except` catches `BaseException`, including `KeyboardInterrupt`, `SystemExit` and `Exception`, and recommends `except Exception` when regular program errors are intended. Source: [Ruff E722 bare-except](https://docs.astral.sh/ruff/rules/bare-except/).

## Runtime evidence

The R44 semantic reality test was run on the real PC and in the sandbox. It found:

| Check | Result |
|---|---|
| `speculative_prefixer.py:559` classification | Typed `except Exception: pass`; not bare-except-pass |
| `type_flow_verifier.py:717` classification | Typed `except Exception: pass`; not bare-except-pass |
| Candidate on a true bare-except-pass fixture | Generated patch parses |
| `ValueError` behavior | Bare and typed handlers both catch |
| `KeyboardInterrupt` behavior | Bare catches; typed propagates |
| `SystemExit` behavior | Bare catches; typed propagates |
| `GeneratorExit` behavior | Bare catches; typed propagates |

This provides a counterexample to universal semantic equivalence and a bounded positive result for ordinary `Exception` behavior. It does not prove that a particular historical SCP patch was correct, because the six persisted lessons do not contain the original source snapshot or patched source.

## Adjudication outcome

The external sources validate the semantic distinction. The current PC source validates that the six persisted records are misclassified at their recorded lines: all six records say `BareExceptPass`, while their two unique file/line locations are typed `except Exception: pass`. The six records have `fix_verified=1` and `success_rate=1.0`, but those fields are internal metadata, not an independent outcome.

Therefore the six records remain **REJECTED for promotion**. The missing evidence is exact pre-fix source, exact patch output, call-site intent, and an independent test for the affected behavior. The correct result is not “the patch is wrong in every context”; it is “the persisted record is not sufficient to prove the patch, and its classification is contradicted by the current source at the recorded locations.”

## References

[1]: https://docs.python.org/3/reference/compound_stmts.html#the-except-clause "Python Language Reference: except clause"
[2]: https://docs.python.org/3/library/exceptions.html "Python Built-in Exceptions"
[3]: https://docs.astral.sh/ruff/rules/bare-except/ "Ruff E722 bare-except"
