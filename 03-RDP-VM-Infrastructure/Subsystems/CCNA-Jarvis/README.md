# CCNA Jarvis

CCNA Jarvis is a testing and performance-tracking subsystem rather than a general conversational memory feature.

## Goal

Use a parsed CCNA question bank to generate repeatable, trackable tests while storing performance in SQLite.

The system should not rely on conversational memory to remember scores.

## Question pool design

The source importer should:

- parse question blocks;
- permanently exclude drag-and-drop questions;
- keep text-only questions for direct bank mode;
- allow exhibit-dependent questions to act as concept seeds for generated text-only questions;
- classify usable questions into CCNA domains and topics.

## Modes

### BANK

Original eligible question-bank items.

### GENERATED

A local model creates an original text-only question from source concepts.

### MIXED

Default blend of bank and generated questions.

## Result tracking

SQLite records:

- question identity;
- domain;
- topic;
- times seen;
- times correct;
- last seen;
- test session;
- user answer;
- correctness.

This enables commands such as:

```text
test Network Access and IP Connectivity, 30 questions
test my weak topics, 15 questions
do not reuse questions from my last three tests
```

## Architecture

```text
SOURCE PDF
    ↓
PARSER
    ↓
FILTER
    ↓
DOMAIN / TOPIC CLASSIFIER
    ↓
SQLITE
    ↓
QUIZ ENGINE
  ↙   ↓   ↘
BANK GENERATED MIXED
    ↓
RESULTS + WEAK-TOPIC WEIGHTING
```

The deterministic database owns history and selection logic. AI is used for classification and generated-question creation where appropriate.
