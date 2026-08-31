# SCP API surface profiles

`SCP_API_PROFILE` controls which optional router groups are registered in the
single FastAPI process. This reduces the reachable API surface without deleting
legacy implementations or changing their paths.

| Profile | Registered surface |
|---|---|
| `core` | Built-in health/readiness, metrics, auth, `/ask`, dashboard and root routes |
| `standard` | `core` plus chat, OpenAI compatibility, control, Hands and Agent routes |
| `full` | `standard` plus versioned admin/import, analysis, browser/PC, webhook, benchmark and call routes |

Resolution is fail-closed:

- production (`SCP_PRODUCTION_MODE=1`) defaults to `core`;
- development/test defaults to `full` for compatibility;
- an explicit invalid value aborts import/startup instead of falling back to
  `full`;
- operators must explicitly set `SCP_API_PROFILE=full` if a production
  deployment still needs all legacy/admin routes.

This is route-registration reduction, not authorization. Every enabled route
must retain its own authentication, capability and policy checks.
