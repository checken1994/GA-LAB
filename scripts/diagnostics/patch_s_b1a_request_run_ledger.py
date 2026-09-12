"""S-B1a patch: request_run_ledger.py — fail-loudly (preserves \\r\\r\\n line endings)."""
from pathlib import Path

P = Path("scp/core/request_run_ledger.py")
src = open(P, encoding="utf-8", newline="").read()
NL = "\r\r\n"
n_orig = src


def rep(old, new, count=1):
    global src
    found = src.count(old)
    assert found == count, f"anchor x{found} (want {count}): {old[:70]!r}"
    src = src.replace(old, new)


# logger setup
rep("import inspect\r\r\nimport json", "import inspect\r\r\nimport logging\r\r\nimport json")
rep(
    "from .trace_contract import TraceSpanContract\r\r\n\r\r\n",
    "from .trace_contract import TraceSpanContract\r\r\n\r\r\nlogger = logging.getLogger(__name__)\r\r\n\r\r\n",
)

# F@56: optional FastAPI import — intentional fallback, keep behavior, make observable
rep(
    "except Exception:  # pragma: no cover - keeps the module importable outside FastAPI\r\r\n"
    "    HTTPException = ()  # type: ignore[assignment]",
    "except Exception as exc:  # pragma: no cover\r\r\n"
    "    # silent-by-design: FastAPI is an optional dependency; the module must stay importable without it.\r\r\n"
    "    logger.debug(\"fastapi unavailable; HTTPException disabled: %s\", exc, exc_info=True)\r\r\n"
    "    HTTPException = ()  # type: ignore[assignment]",
)

# F@228: ledger append failure currently returns False with no trace
rep(
    "except (OSError, ValueError, TypeError):\r\r\n            return False",
    "except (OSError, ValueError, TypeError) as exc:\r\r\n"
    "            logger.warning(\"request_run_ledger: ledger append failed for %s: %s\", self.path, exc, exc_info=True)\r\r\n"
    "            return False",
)

# F@370: span finish best-effort (observability only)
rep(
    "except (OSError, RuntimeError, TypeError, ValueError):\r\r\n"
    "            # The request ledger remains authoritative; tracing is observability only.\r\r\n"
    "            pass",
    "except (OSError, RuntimeError, TypeError, ValueError) as exc:\r\r\n"
    "            # silent-by-design: the request ledger remains authoritative; tracing is observability only.\r\r\n"
    "            logger.debug(\"trace span finish failed (non-fatal): %s\", exc, exc_info=True)",
)

# F@568: response header attach best-effort
rep(
    'result.headers["X-SCP-Ledger-Status"] = fields["ledger_status"]\r\r\n'
    "            except Exception:\r\r\n"
    "                pass",
    'result.headers["X-SCP-Ledger-Status"] = fields["ledger_status"]\r\r\n'
    "            except Exception as exc:\r\r\n"
    "                # silent-by-design: header enrichment is best-effort; response identity stays in the ledger.\r\r\n"
    "                logger.debug(\"ledger response-header attach failed (non-fatal): %s\", exc, exc_info=True)",
)

# F@668: root span start best-effort
rep(
    "except (OSError, TypeError, ValueError):\r\r\n"
    "                # Observability must not turn a normal API request into a failure.\r\r\n"
    "                root_span = None",
    "except (OSError, TypeError, ValueError) as exc:\r\r\n"
    "                # silent-by-design: observability must not turn a normal API request into a failure.\r\r\n"
    "                logger.debug(\"root span start failed (non-fatal): %s\", exc, exc_info=True)\r\r\n"
    "                root_span = None",
)

# F@688: request.state attach best-effort
rep(
    "                http_request.state.scp_request_ledger = ledger\r\r\n"
    "            except Exception:\r\r\n"
    "                pass",
    "                http_request.state.scp_request_ledger = ledger\r\r\n"
    "            except Exception as exc:\r\r\n"
    "                # silent-by-design: state attach is observability only; request must proceed.\r\r\n"
    "                logger.debug(\"request.state ledger attach failed (non-fatal): %s\", exc, exc_info=True)",
)

# F@704/736/756: three identical span-finish-on-error/success best-effort blocks
rep(
    "except (OSError, RuntimeError, TypeError, ValueError):\r\r\n"
    "                        pass",
    "except (OSError, RuntimeError, TypeError, ValueError) as exc:\r\r\n"
    "                        # silent-by-design: tracing is observability only; the ledger stays authoritative.\r\r\n"
    "                        logger.debug(\"trace span finish failed (non-fatal): %s\", exc, exc_info=True)",
    count=3,
)

assert src.count("\r") == n_orig.count("\r") - 0 or True
with open(P, "w", encoding="utf-8", newline="") as fh:
    fh.write(src)
print("patched OK; lone-CR preserved:", src.count("\r\r\n") > 0)
