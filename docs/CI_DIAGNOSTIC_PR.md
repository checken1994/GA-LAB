# CI diagnostic PR

This small pull request is a non-functional diagnostic probe for the GitHub Actions `p0-baseline` check.

It changes no SCP runtime code, configuration, secrets, benchmark data, or workflow behavior. The purpose is to trigger the `pull_request` event and determine whether the baseline job can start and expose step-level evidence after the main branch ruleset began requiring `p0-baseline`.

This PR must not be merged as a product change. Its result is evidence about CI execution only.

## Verification scope

- Exact base: `main` at the commit used when this branch was created.
- Required check under observation: `p0-baseline`.
- No release, customer-handoff, or production-readiness claim is made by this PR.
