# Contributing to SCP DNA

Thank you for your interest in contributing to SCP DNA. This project contains both protected core components and separately licensed extension components. The contribution process is designed to protect contributors, the project, users, and the copyright holder.

> **Legal notice:** This document is a project policy and not a substitute for a separately executed Contributor License Agreement or legal advice. The copyright holder may update this policy before accepting contributions.

## 1. Before you contribute

Please read:

- [`LICENSE`](LICENSE)
- [`LICENSES.md`](docs/legal/LICENSES.md)
- [`docs/legal/THIRD_PARTY_NOTICES.md`](docs/legal/THIRD_PARTY_NOTICES.md)
- [`TRADEMARKS.md`](docs/legal/TRADEMARKS.md)
- [`SECURITY.md`](SECURITY.md), if the repository contains one

Do not submit secrets, private keys, API tokens, customer data, proprietary employer code, unlicensed datasets, copied source code, or files whose license you do not understand.

## 2. Contribution channels

| Contribution type | Required path |
|---|---|
| Bug report | GitHub issue, without secrets or exploit details that could create immediate risk |
| Security vulnerability | Private security channel described in `SECURITY.md`; do not open a public issue |
| Documentation | Pull request with license-compatible content |
| Apache extension/connector | Pull request to the relevant extension directory, with SPDX header and dependency review |
| AGPL core/runtime | Pull request only after the contributor-rights requirement below is satisfied |
| Commercial-only feature | Do not submit proprietary code to the public repository; contact the copyright holder first |

## 3. Contributor rights requirement

SCP DNA may be offered under more than one license for eligible components. To preserve that option, contributions to protected core components may require a separate written **Contributor License Agreement (CLA)** or another written rights instrument approved by the copyright holder.

A pull request, issue, comment, or chat message is **not automatically accepted as a commercial dual-licensing grant**. The project must have a reliable record showing that the contributor had the right to submit the material and granted the rights required for the intended component.

### Core contribution rule

Before a contribution to any of the following paths is merged, the project may require the contributor to complete the project CLA:

```text
scp/runtime/
scp/autofix/
scp/meta/
scp/security/
scp/task_kernel/
desktop/ when it contains SCP core logic
```

The CLA should grant the project copyright holder sufficient rights to reproduce, modify, distribute, sublicense, and offer the contribution under the applicable open-source license and, where expressly covered by the signed CLA, a separate commercial license. The exact CLA must be reviewed by a qualified attorney before use.

Until the CLA process is operational, the maintainer must not promise that every contribution can be included in a commercial edition.

## 4. Extension contributions

An extension may be accepted under Apache-2.0 only when all of the following are true:

1. The contributor owns the submitted code or has permission to submit it.
2. The code does not copy AGPL core into an Apache directory.
3. Third-party dependencies are disclosed and compatible.
4. The required Apache copyright, patent, attribution, and `NOTICE` information is preserved.
5. The pull request contains the correct SPDX identifier.
6. The component remains independently separable according to the project's architecture review.

Required Python header:

```python
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 [CONTRIBUTOR OR PROJECT COPYRIGHT HOLDER]
```

Required TypeScript/JavaScript header:

```ts
// SPDX-License-Identifier: Apache-2.0
// Copyright (c) 2026 [CONTRIBUTOR OR PROJECT COPYRIGHT HOLDER]
```

## 5. Copyright and originality statement

Every pull request must state:

```text
I have the right to submit this contribution, it is not knowingly copied
from incompatible or undisclosed third-party material, and I have disclosed
any third-party code, data, model, asset, or generated content included in it.
```

If the contribution was created as part of employment, contract work, school work, or another organization, obtain permission before submitting it. The project may request written confirmation.

## 6. Third-party and AI-assisted code

You must disclose code or content generated or substantially assisted by an AI system, code generator, vendor SDK, template, or external repository when it may affect copyright, license compatibility, security, or provenance.

AI assistance does not prove that the output is original or license-compatible. The contributor remains responsible for review, testing, attribution, and disclosure.

Do not paste confidential source code, credentials, personal data, or private customer information into an external AI service.

## 7. License headers and file placement

New source files must use the SPDX identifier assigned by [`LICENSES.md`](docs/legal/LICENSES.md). Do not invent a new license identifier or write a shortened replacement for AGPL or Apache.

If a file is generated, vendored, copied, or supplied by a third party, do not add a project SPDX header that falsely claims ownership. Mark the file for review and add the appropriate notice instead.

## 8. Pull request review

A maintainer may reject or request changes to a contribution for any of the following reasons:

- The license or copyright owner is unclear.
- A dependency has an incompatible or undisclosed license.
- The change copies core code into an extension boundary.
- The change adds a secret, private data, generated credential, or unsafe default.
- The change weakens security policy, sandboxing, audit, recovery, or kill-switch behavior.
- The contribution cannot be supported under the component's intended license.
- The contributor-rights record is incomplete.

Passing tests does not guarantee acceptance. License, security, provenance, and architecture review are separate gates.

## 9. No automatic trademark permission

Contributing code does not grant permission to use SCP DNA, SCP, GA-LAB, logos, or other project marks. See [`TRADEMARKS.md`](docs/legal/TRADEMARKS.md).

## 10. Developer Certificate of Origin option

If the project uses a DCO for a component that is **not** intended for commercial dual licensing, contributors may be required to sign off each commit:

```text
Signed-off-by: Full Name <email@example.com>
```

A DCO is not automatically equivalent to a CLA for commercial dual licensing. The maintainer must document which component uses which rights process.

## 11. Maintainer authority

The copyright holder and authorized maintainers may:

- Require a CLA before accepting protected-core contributions.
- Keep a contribution in the open-source edition but exclude it from a commercial edition if the rights record does not permit commercial relicensing.
- Reclassify a component after dependency and architecture review.
- Reject or remove code with unclear provenance.
- Publish releases under the component license map in effect at the release tag.

## 12. Contact

For contributor-rights, commercial licensing, or provenance questions:

```text
Contact: checken1994@gmail.com
Copyright holder: Nguyễn Văn Minh
Project: GA-LAB / SCP DNA
```

Before publication, confirm that the contact address is controlled by the copyright holder and that the legal name is correct.
