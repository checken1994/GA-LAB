# SCP public naming policy

SCP now presents its deterministic domain dispatchers publicly as **Domain Experts**. The historical **SLM** term remains only at explicit compatibility or historical boundaries.

SCP's legacy SLM classes are **deterministic dispatchers** that route questions to DataSources and verify answers; they are not neural-network model identifiers. The name "SLM" was chosen early in development and is kept because existing callers and stored traces depend on it.

## Canonical names for new code

Use **Domain Expert** for one deterministic domain dispatcher, **BaseDomainExpert** for the base class alias, **DomainExpertResponse** for the response type alias, and **Domain Expert Ensemble** for the coordinated runtime registry.

## Compatibility boundary

The following old runtime symbols remain intentionally import-compatible:

```python
from scp.runtime.slm_base import BaseSLM, SLMResponse
from scp.runtime.slms import MathSLM
```

They are aliases/legacy exports, not the preferred public vocabulary. New code should import the canonical aliases where available:

```python
from scp.runtime.slm_base import BaseDomainExpert, DomainExpertResponse
```

Some domain modules also provide a concrete `*Expert` alias. If a concrete alias is not exported for a domain, callers may use a local import alias without changing the compatibility module:

```python
from scp.runtime.slms import MathSLM as MathExpert
```

## Why not physically rename every module now?

Renaming the 33 legacy classes, `slm_base.py`, `slms.py`, and implementation imports would touch many files and risk breaking stored traces and external imports. The staged alias approach makes the current public terminology canonical while preserving the old API contract. A future physical module rename must add shims and its own migration tests before it is accepted.
