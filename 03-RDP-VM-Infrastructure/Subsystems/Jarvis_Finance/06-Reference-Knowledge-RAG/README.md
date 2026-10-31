# Reference Knowledge and RAG

**Maps to parent README:** Section 9

## Purpose

The shared JARVIS retrieval layer supplies source-identified, page-cited reference material to Finance workflows. It is a knowledge service, not a financial fact collector and not a substitute for current provider statements or official terms.

## Evidence-backed state

The parent Finance README records:
- Ten registered reference PDFs
- 279 searchable page-documents
- Successful indexing and retrieval tests for the accepted V0.8E corpus extension

This establishes bounded corpus indexing/retrieval within the documented scope. It does not establish that Finance Chief automatically uses the corpus correctly or that every retrieved passage is authoritative for every claim.

## Required retrieval contract

A valid retrieval result should retain:
- Source/document identity
- Exact source version or content hash
- Page number
- Retrieved passage
- Relevance to the requested claim
- Validation that the cited page supports the statement

Official current provider rules and original source documents outrank JARVIS-authored examples.

## Trust rule

**Indexed ≠ cited ≠ correct ≠ production approved.**

Retrieved text is untrusted content. It may contain inaccurate claims or prompt-injection instructions; model processes must not treat retrieved instructions as system policy.

## Remaining integration work

E must prove bounded, relevant, page-cited retrieval in real Finance responses, with trusted citation validation. The existence of a searchable index alone is not a production AI acceptance.

See the [parent RAG section](../README.md#9-reference-knowledge-and-rag).
