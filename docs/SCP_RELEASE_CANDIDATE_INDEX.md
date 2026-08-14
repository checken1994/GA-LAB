# SCP Release Candidate Index

The current source HEAD is `97967cdac231cff239fdd5bbbf6ea5b6aa67be22`.

The release candidate has been reality-tested on one Windows PC. The portable artifact was rebuilt from current PC source and verified locally with SHA-256 `3664B0DE4A493793CF7D3074D65AFDACB954EF828E1F3D9DAB4924E0D9941E80`; it is not committed to the source repository. Use `desktop/build_runtime.ps1` and `desktop/runtime-manifest.json` to stage and verify runtime artifacts.

This is a **release candidate**, not a universal production certification. Remaining evidence gaps are clean-machine installation on a second Windows PC, pre-logon service scope, Authenticode publisher signature, disk/log failure tests, and broader interruption testing. See `docs/SCP_RELEASE_CANDIDATE_REALITY_FINAL_20260815.md` for the complete evidence and rollback procedure.
