# SCP Cognitive Control Architecture (26-P1)

## Kiến trúc Tổng thể

```text
                         ┌─────────────────────────┐
                         │     HUMAN AUTHORITY     │
                         │ approval / policy / risk│
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │   GOVERNANCE CONTROL    │
                         │ Drift / Privacy / Cost  │
                         │ Capability / Risk / PEP │
                         └────────────┬────────────┘
                                      │
 ┌──────────────┐           ┌────────▼────────┐
 │ EXTERNAL     │           │ COGNITIVE       │
 │ WORLD        │──────────▶│ ORCHESTRATOR    │
 │ Web/API/Git  │           │                 │
 │ Runtime/User │           └────────┬────────┘
 └──────────────┘                    │
                                     ▼
                    ┌────────────────────────────────┐
                    │       EPISTEMIC CONTROL        │
                    │                                │
                    │ Evidence → Identity → Lineage  │
                    │ → Claim → Contradiction        │
                    │ → Verdict → Promotion          │
                    └──────────────┬─────────────────┘
                                   │
               ┌───────────────────┼──────────────────┐
               ▼                   ▼                  ▼
       ┌──────────────┐    ┌──────────────┐   ┌──────────────┐
       │ KNOWLEDGE    │    │ DOUBT /      │   │ CALIBRATION  │
       │ AUTHORITY    │    │ QUESTIONS    │   │ + SELF-MODEL │
       │              │    │              │   │              │
       │ RAW→GOLD     │    │ UNKNOWN      │   │ What can SCP │
       │ validity     │    │ blind spots  │   │ really prove?│
       └──────┬───────┘    └──────┬───────┘   └──────────────┘
              │                   │
              │                   ▼
              │          ┌──────────────────┐
              │          │ HYPOTHESIS &     │
              │          │ EXPERIMENT       │
              │          └────────┬─────────┘
              │                   │
              └─────────┬─────────┘
                        ▼
               ┌──────────────────┐
               │ REASON / PLAN    │
               │ choose strategy  │
               └────────┬─────────┘
                        ▼
               ┌──────────────────┐
               │ ACTION CONTROL   │
               │ TaskKernel       │
               │ Tools / Autofix  │
               │ Gateway          │
               └────────┬─────────┘
                        ▼
               ┌──────────────────┐
               │     REALITY      │
               │ actual poststate │
               └────────┬─────────┘
                        │
                        └──────────↺
```

(Bản thiết kế chi tiết 14 phần đã được tích hợp vào hệ thống theo thiết kế của user ngày 2026-09-02).
