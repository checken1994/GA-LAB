// [Z4] Canonical mandatory entrypoint: `bun index.ts` MUST go through the
// zero-cost bootstrap (config validation + fetch PEP) before the legacy
// server (core.ts) loads. Direct `bun core.ts` is fail-closed by the PEP flag.
import "./zero_cost_bootstrap";
