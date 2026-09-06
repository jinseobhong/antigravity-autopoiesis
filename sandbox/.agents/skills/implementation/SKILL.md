---
name: implementation
description: >-
  Implements, refactors, and writes production-ready code.
  Use this skill whenever the user asks to write code, implement a feature, 
  create functions/classes, or refactor existing code.
---

# Production Code Implementation Protocol

A deterministic, high-velocity engineering runbook for implementing robust, production-grade code.

## 1. Authoritative Rules Binding (@ Context Injection)

Before writing or editing code, the agent MUST inspect and strictly enforce the repository rules:
- **Style & Hygiene**: `@.agents/rules/CODING_CONVENTION.md`
- **Structural Quality & Security**: `@.agents/rules/CODING_STANDARD.md`

--------------------------------------------------------------------------------

## 2. 3-Step Compact Implementation Methodology

### Step 1: Contract & Boundary Analysis
1. Define explicit input/output contracts, static types, and error/exception signatures.
2. Parameter Discipline: Maximum 7 parameters; encapsulate into a dedicated DTO/Parameter Object if > 7.
3. Control Flow: Apply Guard Clauses (early return) to eliminate deep nesting.

### Step 2: Invariant-Guarded Implementation
1. **Complexity**: Ensure Cyclomatic Complexity (CC) <= 10 per function.
2. **Resource Safety**: Deterministic disposal along all paths (`with`, `try-with-resources`, `defer`).
3. **Security Invariants**: Parameterized queries only (no SQL/command injection), zero plaintext secrets, canonicalized file paths.
4. **Anti-Cheat Enforcement**: Zero placeholder stubs (`pass`, `...`, `NotImplementedError` in final code), zero dead code.

### Step 3: Companion Verification
1. **Companion Test Suite**: Write tests alongside production code.
   - Happy paths: ~50%
   - Negative paths & boundary errors: >= 30% (null inputs, type mismatch, timeout/exceptions).
2. **Zero Defect Gates**: Zero lint/formatting errors, zero tautological assertions (`assert True`).
