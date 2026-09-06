---
name: "coding_convention"
description: "Enforces enterprise naming conventions, layout formatting, comment standards, and Conventional Commits. Use this rule whenever writing, formatting, or reviewing code and commit messages."
activation: Menual
---

# Universal Enterprise Coding Conventions (Style & Hygiene)

This specification defines mandatory naming, formatting, documentation, and version control conventions. Antigravity MUST enforce these rules across all languages and frameworks.

Prioritize the language's official standard formatter and idioms.

---

## 1. Universal Naming Conventions

Target language official idioms (e.g., PEP 8 for Python, gofmt for Go) take precedence. Otherwise, adhere strictly to the following standards:

| Identifier Type | Casing | Rules & Requirements | Example |
| :--- | :--- | :--- | :--- |
| **Classes / Types / Interfaces** | `PascalCase` | Noun or noun phrase. DO NOT prefix interfaces with `I` (unless idiomatic to the framework). | `OrderService`, `PaymentProcessor` |
| **Methods / Functions** | `camelCase` | Verb or verb phrase describing action. Boolean methods MUST use `is`, `has`, `can`, or `should` prefixes. | `calculateTax()`, `isValid()` |
| **Variables & Parameters** | `camelCase` | Meaningful nouns. 1~2 character abbreviations are **FORBIDDEN** (except loop index `i`, `j` or coordinates `x`, `y`). | `accountBalance`, `retryLimit` |
| **Constants / Static Final** | `UPPER_SNAKE_CASE` | Truly immutable, compile-time/static constants only. | `MAX_RETRY_COUNT`, `DEFAULT_TIMEOUT_MS` |
| **Enums** | `PascalCase` / `UPPER_SNAKE` | Enum type in `PascalCase`; enum members in `UPPER_SNAKE_CASE`. | `OrderStatus.PENDING_PAYMENT` |
| **Namespaces / Packages** | `lowercase` | Dot-delimited single lowercase words. No hyphens or camelCase. | `com.enterprise.billing.settlement` |
| **Files & Components** | `PascalCase` / `kebab-case` | Class/component files MUST match class name (`OrderService.ts`). Scripts and configs MUST use kebab-case. | `auth-guard.middleware.ts` |

---

## 2. Code Layout & Formatting Hygiene

- **Indentation**: Spaces ONLY. Tabs are **FORBIDDEN** (except where mandated by language toolchains like Go).
  - **2 Spaces**: TypeScript, JavaScript, HTML, CSS, JSON, YAML.
  - **4 Spaces**: Java, Python, C#, C++.
- **Line Length**: Hard limit of **120 columns**. Break lines before binary operators or after commas in argument lists.
- **Mandatory Braces**: Omitting curly braces `{}` in single-line control statements (`if`, `for`, `while`) is **STRICTLY FORBIDDEN**.
- **Brace Style**: Use K&R style (opening brace on the same line as declaration).
- **Blank Lines**: Exactly one blank line between method declarations. Max one consecutive blank line within methods.
- **File Termination**: Every source file MUST terminate with a single POSIX newline (`LF`, `\n`). Trailing whitespace is **FORBIDDEN**.

---

## 3. Comments & Documentation Standards

- **The 'Why', Not the 'What'**:
  - Code MUST explain *What* and *How* through clear naming and small functions.
  - Comments MUST exclusively document *Why* (business constraints, non-obvious edge cases, algorithmic rationale).
- **Public API Documentation**:
  - All public classes, interfaces, and exported functions MUST have standard documentation docstrings (`Javadoc`, `TSDoc`, `Docstrings`).
  - MUST specify `@param`, `@return`, and `@throws` (or language equivalents).
- **Zero Dead Code**:
  - Commenting out code blocks to preserve history is **STRICTLY FORBIDDEN**. Delete dead code immediately; rely on VCS (Git) history.
- **Task Tracking Tags**:
  - `TODO` and `FIXME` comments MUST include an issue tracker ticket ID:
    ```
    // TODO(#PROJ-1042): Refactor caching mechanism after Redis migration
    ```

---

## 4. Control Flow & Defensive Idioms

- **Guard Clauses (Early Return)**:
  - Flatten nested conditionals. Check error conditions and return/throw early to keep the happy path unindented.
- **Pure Functions & Immutability**:
  - Prefer immutable data structures (`const`, `final`, `readonly`, frozen objects).
  - Avoid side-effects in functions that return a value.
- **Parameter Discipline**:
  - Avoid boolean flags as method arguments (e.g., `processOrder(order, true)`). Split into two distinct methods or use an Enum/options object.

---

## 5. Version Control & Review Conventions

- **Conventional Commits**: Commit messages MUST adhere to `<type>(<scope>): <subject>`:
  - **Types**: `feat`, `fix`, `refactor`, `perf`, `chore`, `test`, `docs`.
  - **Subject**: Imperative mood, present tense, lowercase, no trailing period (e.g., `feat(auth): implement oauth2 refresh token rotation`).
- **PR Scope**: Single PRs SHOULD NOT exceed **400 effective lines of code (LOC)**.
- **Conventional Comments (Code Review Labels)**:
  - `issue:` (blocking problem, bug, security flaw)
  - `suggestion:` (non-blocking idea for improvement)
  - `question:` (clarification of intent or rationale)
  - `nit:` (trivial clean-up: typo, micro-refactoring)
  - `praise:` (positive feedback on clean architecture)