---
name: implement
description:
  Implements, refactors, and writes production-ready code.
  Use this skill whenever the user asks to write code, implement a feature, 
  create functions/classes, or refactor existing code.
---

# Production Code Implementation Protocol

A deterministic, high-velocity engineering runbook for implementing robust, production-grade code.

## 1. Tool Action Binding & Authoritative Rules Cascade

### 1.1 Tool Action Binding Matrix
All implementation tasks MUST strictly adhere to the designated tool APIs and execution boundaries:

| Operational Phase | Tool API | Parameter Constraints & Bounded Invariants |
| :--- | :--- | :--- |
| **Rule & Context Ingestion** | `view_file` | `AbsolutePath`, `StartLine=1, EndLine=800` (Bounded slices; no recursive directory dumps). |
| **Symbol & Call-Site Discovery** | `grep_search` / `find_by_name` | Locate existing types, base classes, and consumers before writing new code. |
| **Surgical Code Modification** | `replace_file_content` | Target exact, unique chunks. Overwriting entire existing files is strictly FORBIDDEN. |
| **Dynamic Verification & Gates**| `run_command` | Execute test runners and linters deterministically; assert `exit code 0`. |

### 1.2 Hierarchical Rules Discovery Cascade
Before writing or modifying code, inspect repository rules following this strict priority cascade:
1. **Workspace Project Rules**: Primary authority (`.agents/rules/CODING_CONVENTION.md`, `.agents/rules/CODING_STANDARD.md`, or `GEMINI.md`).
2. **Native Repository Configurations**: If proprietary rules are absent, enforce workspace configs (`pyproject.toml`, `ruff.toml`, `tsconfig.json`, `.eslintrc.*`, `biome.json`).
3. **Official Language Idioms**: Fall back to language standards (PEP 8 for Python, Effective Go, TypeScript Strict).

--------------------------------------------------------------------------------

## 2. Bifurcated Production Implementation Methodology

Choose the appropriate execution track based on the task type:

---

### Track A: Greenfield Feature & Function Writing

#### Step 0: Context Discovery & Call-Site Reconnaissance
1. **Inspect Existing Types**: Search for existing interfaces, base classes, and domain models via `grep_search` and `view_file` to prevent redundant type bloat.
2. **Harmonize Patterns**: Mirror the target module's existing naming, error hierarchy, and import styles.

#### Step 1: Contract Definition & Minimal Surface Area (YAGNI)
1. **Explicit Contracts**: Define static type annotations, input preconditions, and return/error signatures.
2. **Parameter Discipline**: Target $\le 4$ parameters; hard maximum 7. Encapsulate into a dedicated DTO if $> 7$.
3. **Control Flow**: Enforce early-return guard clauses (`if (!valid) return;`) to keep business logic at root indentation (nesting depth $\le 3$).
4. **YAGNI Invariant**: Prohibit speculative abstractions, generic factories, or single-use wrapper classes unless explicitly requested.

#### Step 2: Invariant-Guarded Implementation
> [!CAUTION]
> **Blast Radius & Diff Hygiene Guardrail**:
> - **Surgical Edits Only**: Use `replace_file_content`. Overwriting entire existing files is strictly FORBIDDEN.
> - **Preservation Invariant**: Preserve all unrelated code, comments, docstrings, and license headers.

1. **Complexity Threshold**: Maintain Cyclomatic Complexity (CC) $\le 10$ and Cognitive Complexity $\le 15$ per function.
2. **Deterministic Resource Safety**: Ensure deterministic disposal along all paths (`with`, `try-with-resources`, `defer`).
3. **Concurrency & Thread Safety**: Protect mutable shared state with synchronization primitives or immutability; avoid blocking asynchronous event loops.
4. **Error Propagation & Causal Chaining**: Catch-all swallowing (`except: pass`) is strictly banned. Exceptions re-thrown across layers MUST preserve root causes (`raise CustomError(...) from err`).
5. **Semantic Anti-Cheat Invariant**: Zero placeholder stubs (`pass`, `...`, `NotImplementedError`). Furthermore, dummy return bypasses (`return True`, `return {}` with unconsumed parameters) are forbidden. Every non-ignored parameter MUST be functionally utilized.

#### Step 3: Dynamic Verification & CLI Execution Gates
> [!IMPORTANT]
> **Zero Mental Simulation**: "Mental verification" without dynamic execution is strictly FORBIDDEN. The agent MUST execute CLI test and linter commands via `run_command` and verify exit code `0`.

1. **Dynamic Test Runner Execution**:
   - Python: `pytest -v -k "<test_target>"` (Assert: `exit code 0`, 0 failed)
   - Node/TypeScript: `npm test -- <test_path>` (Assert: `exit code 0`, PASS)
   - Go: `go test -v -run <TestName> ./...` (Assert: `exit code 0`, PASS)
2. **Risk-Stratified Test Coverage**:
   - Enforce $\ge 80\%$ branch coverage on newly introduced logic.
   - Mandate negative path & boundary tests (null inputs, type mismatch, timeout/exceptions, malformed payloads).
   - Zero tautological assertions (`assert True`, `expect(true).toBe(true)`).
3. **Static Linter & Type-Checker Gates**:
   - Python: `ruff check <path> && mypy <path>` (Assert: `exit code 0`)
   - Node/TypeScript: `npm run lint && npx tsc --noEmit` (Assert: `exit code 0`)

---

### Track B: Refactoring & Modification of Existing Code

#### Step 0: Green Baseline Verification
- Prior to altering any code, execute the existing test suite covering the target module via `run_command`.
- If baseline tests fail, **STOP immediately and report the pre-existing defect** to the user; NEVER refactor on top of a broken baseline.

#### Step 1: Characterization / Pinning Tests
- If the legacy code lacks sufficient test coverage, write characterization tests pinning existing behavioral invariants before refactoring.

#### Step 2: Invariant-Preserving Refactoring
- Apply surgical modifications via `replace_file_content`.
- Strictly preserve public API signatures, existing type annotations, and edge-case handlings unless explicitly tasked with a breaking change.

#### Step 3: Regression Verification & State Restoration
1. **Full Regression Execution**: Re-run all baseline and characterization tests. All tests MUST pass with zero regressions.
2. **Diff Audit**: Inspect modified files to guarantee zero accidental side-effects or deleted comments.
3. **Rollback Threshold**: If verification fails and cannot be resolved within 2 remediation attempts, execute `git restore <target_file>` to return the repository to a pristine state.