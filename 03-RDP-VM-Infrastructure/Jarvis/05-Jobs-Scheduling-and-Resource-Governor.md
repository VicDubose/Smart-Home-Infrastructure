# Jobs, Scheduling, and Resource Governor

Jarvis should behave like a small operating system for infrastructure work.

## Job state

```text
PENDING
   ↓
READY
   ↓
RUNNING
  ↙   ↘
DONE  FAILED
       ↓
   retry allowed?
    ↙       ↘
 PENDING   BLOCKED
```

Typical job records include:

- run ID;
- job ID;
- domain;
- agent;
- required capability;
- priority;
- status;
- created / started / completed timestamps;
- input evidence path;
- output path;
- confidence;
- retry count;
- error state.

## Independent pipelines, shared AI governor

Media, Local Events, HVAC review, energy review, CCNA testing, and other systems should maintain their own state machines.

They should not all embed independent assumptions about AI concurrency.

Instead:

```text
PIPELINE A ─┐
PIPELINE B ─┼──► GLOBAL AI JOB QUEUE ─► RESOURCE / THERMAL GOVERNOR
PIPELINE C ─┘
```

Non-AI stages continue whenever safe. AI stages may queue.

Example:

```text
media rip/copy/ffprobe continues
while
AI validation waits
```

## Current Core constraint

SKYNET-CORE is thermally constrained during sustained local inference. Generative workloads therefore require resource governance rather than being launched freely.

The current architecture assumes conservative inference concurrency on Core and allows future SKYNET-AI hardware to increase parallelism without changing the job interfaces.

## Priority

Important scheduled reviews such as HVAC health may preempt lower-priority background classification or media analysis.

Resource policy should be deterministic and auditable.
