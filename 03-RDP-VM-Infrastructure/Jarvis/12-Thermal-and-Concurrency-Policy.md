# SKYNET-CORE Thermal and AI Concurrency Policy

## Purpose

This document records measured SKYNET-CORE AI thermal behavior and defines
the direction for Jarvis resource scheduling.

Thermal observations are evidence. Untested workload combinations are not
automatically considered safe.

## AI CPU Group

Current AI CPU affinity:

CPUs 4-7

CPU affinity and CPU quota are separate controls. Four available logical
CPUs does not mean Jarvis should continuously consume four full CPUs.

## Current Sustained Operating Point

The Local Events Gemma workload was tested at approximately:

- CPU affinity: CPUs 4-7
- Aggregate CPU quota: 200%
- Restart temperature: approximately 60 C

Observed temperatures after restart included:

- 82.0 C
- 83.6 C
- 84.6 C
- 79.4 C
- 84.8 C
- 80.0 C
- 86.0 C
- 86.0 C

During the observed period, the classification queue continued progressing
without reaching the previous 90 C thermal cutoff.

The practical observed sustained range was approximately 80-86 C.

## Interpretation

For the tested Gemma workload, SKYNET-CORE should currently be viewed as:

4 logical AI CPUs available
+
approximately 200% sustained aggregate AI CPU budget

This behaved substantially better than more aggressive 250-400% execution,
which produced faster temperature rise and repeated cooldown behavior.

The design goal is not maximum instantaneous inference speed.

The goal is maximum useful completed work per hour without destabilizing
SKYNET-CORE.

## Harness Implication

Jarvis should not permanently encode a rigid assumption that only one AI
operation may ever exist at once.

Instead, the future resource governor should manage a shared thermal and CPU
budget.

Conceptual flow:

BACKGROUND SMALL AGENT
        |
        v
~200% SUSTAINED AI BUDGET
        |
        v
THERMAL / RESOURCE GOVERNOR
        |
        +-- thermal headroom available
        |        |
        |        v
        |   short router operation
        |        |
        |        v
        |   classify / route work
        |        |
        |        v
        |   wake specialist
        |
        +-- insufficient headroom
                 |
                 v
              queue work

## Router Concurrency Goal

The intended Jarvis behavior is:

incoming work
    ->
semantic + deterministic routing
    ->
select domain and capability
    ->
wake appropriate specialist
    ->
specialist processes bounded work
    ->
small result returned
    ->
evidence / router / Chief layer

A background worker should not automatically need to stop merely because a
short routing operation is required.

## Proven So Far

The following behavior has been observed:

- Gemma sustained workload
- CPUs 4-7
- approximately 200% aggregate CPU
- continuous queue progress
- approximately 80-86 C during the observed sustained window
- no 90 C cutoff during that observation window

## Strong Candidate Policy

Approximately 200% aggregate CPU is the current candidate sustained AI
operating point for this class of workload.

## Not Yet Proven

The following combination still requires controlled testing:

sustained Gemma worker
+
short EmbeddingGemma/router operation
=
no meaningful additional thermal penalty

Do not promote that assumption into production policy until measured.

## Governor Inputs

The future Jarvis governor should consider:

- current temperature
- temperature rate of change
- CPU quota
- CPU affinity
- active workload class
- requested workload class
- active model
- requested model
- expected duration
- job priority
- deadline
- available thermal headroom
- cooldown state

Possible decisions should include:

- ALLOW
- ALLOW BURST
- QUEUE
- THROTTLE
- COOLDOWN
- EMERGENCY STOP

## Safety Fallback

Single-inference serialization remains the safe fallback whenever thermal
state or workload behavior is uncertain.

## Next Controlled Test

The next useful experiment is:

1. Run Gemma at the 200% sustained baseline.
2. Measure stable temperature and rate of rise.
3. Introduce a short semantic/router workload.
4. Measure peak temperature.
5. Measure worker completion time.
6. Measure router latency.
7. Observe SSH responsiveness.
8. Determine whether cooldown is triggered.

If this produces no meaningful thermal excursion, short router concurrency
can be promoted from experimental behavior into normal Jarvis governor
policy.
