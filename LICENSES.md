# SCP DNA — Component License Map

This document is the authoritative human-readable map for the repository's multi-license layout. If a source file has a more specific SPDX header or third-party notice, that notice must be reviewed together with this map.

## 1. License identifiers

| Identifier | Full name | Full text |
|---|---|---|
| `AGPL-3.0-only` | GNU Affero General Public License v3.0 only | [`licenses/AGPL-3.0-only.txt`](licenses/AGPL-3.0-only.txt) |
| `Apache-2.0` | Apache License 2.0 | [`licenses/Apache-2.0.txt`](licenses/Apache-2.0.txt) |
| `NOASSERTION` | Not yet classified or not solely owned by this project | Must be reviewed before redistribution |

## 2. Core components — AGPL-3.0-only

The following paths are intended to be part of the SCP core and must use the exact SPDX identifier `AGPL-3.0-only` after copyright and dependency review:

```text
scp/runtime/
scp/autofix/
scp/meta/
scp/security/
scp/task_kernel/
```

If `desktop/` contains or distributes SCP core runtime, privileged control logic, or code that is not separable from the core, it must remain under `AGPL-3.0-only` unless a separate written decision says otherwise.

Required source header for a Python file:

```python
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Nguyễn Văn Minh
```

Required source header for TypeScript/JavaScript:

```ts
// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (c) 2026 Nguyễn Văn Minh
```

## 3. Separately distributed extensions — Apache-2.0

The following paths may use `Apache-2.0` only after the dependency graph confirms that the component is independently usable and does not silently include or copy AGPL core code:

```text
mini-services/llm-bridge/
mini-services/loop-scheduler/
scp/data_sources/
sdk/
client-cli/
```

Required source header for a Python file:

```python
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Nguyễn Văn Minh
```

Required source header for TypeScript/JavaScript:

```ts
// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 Nguyễn Văn Minh
```

Apache-licensed components must preserve applicable copyright, patent, attribution, and `NOTICE` information when redistributed. The Apache License does not grant permission to use project trademarks as an endorsement.

## 4. Paths that require an explicit review

Do not automatically label the following paths until their imports, build outputs, and distribution boundaries have been reviewed:

```text
dashboard/
desktop/
scp/api/
scp/llm_gateway/
scp/integrations/
tests/
benchmark/
data/
tools/
```

A directory name does not decide a license by itself. Review the actual source, generated output, dependency graph, and third-party terms.

## 5. Third-party and generated material

The following are not automatically owned or relicensed by GA-LAB:

- Python, Node, Bun, Electron, browser, model, SDK, and operating-system dependencies.
- Files copied from other repositories.
- Model weights, datasets, fonts, images, icons, and benchmark data.
- Generated files whose generator or source has separate terms.
- User-submitted contributions for which the project has not obtained the required rights.

Every such item must be listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) or marked `NOASSERTION` until reviewed.

## 6. Rules for combining components

This map is not a legal opinion about whether two components form one combined work. Before distributing a bundle containing both AGPL core and Apache extensions, review the actual architecture and applicable license obligations. Prefer clean process/API boundaries and document them.

Do not copy AGPL core source into an Apache-2.0 directory. Do not remove third-party notices. Do not add a commercial-only restriction to files already granted under AGPL or Apache in a public release.

## 7. Release gate

A release must not be published until:

1. Every distributed source file has a valid SPDX identifier or a documented third-party license.
2. `THIRD_PARTY_NOTICES.md` is complete for the release.
3. No `.env`, token, private key, password, customer data, or private artifact is present in the repository or Git history intended for publication.
4. The copyright holder has confirmed contributor rights.
5. The release tag contains the exact license texts and this map.
6. A qualified attorney has reviewed any commercial dual-licensing claim.
