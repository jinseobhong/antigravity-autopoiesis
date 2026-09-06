---
name: "coding_convention"
description: "Enforces language-idiomatic naming conventions, native toolchain formatting, documentation hygiene, and Conventional Commits. Use this rule whenever writing, formatting, or reviewing code and commit messages."
globs:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "**/*.java"
  - "**/*.go"
  - "**/*.cpp"
  - "**/*.cs"
---

# Universal Enterprise Coding Conventions (Style, Idioms & Hygiene v2.0)

This specification defines mandatory naming, formatting, documentation, and version control conventions for multi-language enterprise and pair-programming repositories.

Antigravity and human contributors MUST adhere to these standards. Toolchain formatters and language-native idioms take precedence over manual micro-styling.

---

## 1. Naming Conventions & Language Matrices

### 1.1 Universal Semantic Invariants (All Languages)
1. **Intention-Revealing**: Names MUST clearly communicate intent, scope, and domain semantics (`userAuthenticationToken`, not `tok` or `data`).
2. **Pronounceable & Searchable**: Avoid cryptic contractions (`custAddress`, not `cst_addr`).
3. **No Hungarian Notation or Redundant Suffixes**: Do not encode data types or metadata into identifiers (`customerList` -> `customers`; `OrderServiceClass` -> `OrderService`).
4. **No Interface `I` Prefix**: Do NOT prefix interfaces with `I` (e.g., use `PaymentProcessor`, not `IPaymentProcessor`), unless explicitly mandated by ecosystem frameworks (e.g., idiomatic C# / .NET).

### 1.2 Polyglot Language Casing Matrix

To prevent syntax errors and ecosystem collisions, casing MUST conform to each language's compiler and community standard:

| Language | Classes / Types | Functions / Methods | Variables & Parameters | Constants | Module / File Names |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Python** (`.py`) | `PascalCase` | `lower_snake_case` | `lower_snake_case` | `SCREAMING_SNAKE_CASE` | `lower_snake_case.py` *(Hyphens strictly forbidden)* |
| **TypeScript / JS** (`.ts`, `.js`) | `PascalCase` | `camelCase` | `camelCase` | `SCREAMING_SNAKE_CASE` | `kebab-case.ts` (Files), `PascalCase.tsx` (Components) |
| **Go** (`.go`) | `PascalCase` | `PascalCase` (Exported)<br>`camelCase` (Unexported) | `camelCase` / Short Idioms | `PascalCase` (Exported)<br>`camelCase` (Unexported) | `lower_snake_case.go` |
| **Java** (`.java`) | `PascalCase` | `camelCase` | `camelCase` | `SCREAMING_SNAKE_CASE` | `PascalCase.java` (Matches Class) |
| **C#** (`.cs`) | `PascalCase` *(Interfaces: `I` prefix)* | `PascalCase` (Methods/Props)<br>`camelCase` (Local) | `camelCase` *(Private fields: `_camelCase`)* | `PascalCase` or `SCREAMING_SNAKE` | `PascalCase.cs` (Matches Class) |
| **C++** (`.cpp`, `.hpp`) | `PascalCase` | `camelCase` or `snake_case` | `camelCase` or `snake_case` | `SCREAMING_SNAKE_CASE` | `lower_snake_case.cpp` |

### 1.3 Short Identifier Rules & Ecosystem Whitelists
- **General Rule**: Single-letter and two-letter identifiers are FORBIDDEN in application logic.
- **Universal Whitelist**:
  - Loop counters: `i`, `j`, `k`.
  - Mathematical coordinates & dimensions: `x`, `y`, `z`, `w`, `h`.
- **Language-Specific Whitelists**:
  - **Go (`.go`)**: Single-letter method receivers (`func (s *OrderService) Process()`) and canonical idioms (`ctx`, `err`, `tx`, `db`, `w`, `r`, `ok`, `id`) are EXPLICITLY PERMITTED and encouraged per *Effective Go*.
  - **Python (`.py`)**: Context manager handles (`with open(...) as f:`) and caught exceptions (`except Exception as e:`) are permitted.

---

## 2. Layout, Formatting & Toolchain Delegation

### 2.1 Native Toolchain Authority
Layout formatting (indentation, line wrapping, imports, whitespace) MUST be delegated to official native formatters rather than debated manually. All code MUST pass its respective language formatter:

| Language | Authoritative Formatter | Verification Command | Formatting Command |
| :--- | :--- | :--- | :--- |
| **Python** | `ruff` (or `black`) | `ruff format --check .` | `ruff format . && ruff check --fix .` |
| **TypeScript / JS** | `prettier` / `biome` | `npx prettier --check .` | `npx prettier --write .` |
| **Go** | `gofmt` / `goimports` | `gofmt -l .` | `gofmt -w .` *(Tabs are mandatory per Go spec)* |
| **Java** | `spotless` / `google-java-format` | `mvn spotless:check` | `mvn spotless:apply` |
| **C#** | `dotnet format` | `dotnet format --verify-no-changes` | `dotnet format` |
| **C++** | `clang-format` | `clang-format --dry-run --Werror src/*` | `clang-format -i src/*` |

### 2.2 Structural Layout Invariants
1. **Block Delimiters**:
   - **Bracket-Delimited Languages (`.ts`, `.java`, `.go`, `.cs`, `.cpp`)**: Control statements (`if`, `for`, `while`) MUST use curly braces `{}`. Single-line body omission (e.g., `if (err != null) return err;`) is FORBIDDEN.
   - **Indentation-Delimited Languages (`.py`)**: Blocks MUST use standard 4-space indentation without brackets.
   - **Brace Styles**: C-family / Go / Java use K&R style (`{` on same line). C# / C++ permit Allman style (`{` on new line) if consistent with project standards.
2. **Line Length**:
   - Target line length is **88 to 120 columns**, determined by the native formatter configuration. Code that exceeds the limit MUST be broken across lines following standard language continuation rules.
3. **Cross-Platform Line Endings**:
   - All source files MUST use POSIX `LF` (`\n`) newlines.
   - Every repository root MUST contain a `.gitattributes` file enforcing LF normalization:
     ```gitattributes
     * text=auto eol=lf
     ```

---

## 3. Documentation & Comment Standards

### 3.1 Commenting Philosophy
- **Explain "Why", Not "What"**: Code explains the mechanics; comments explain the intent, non-obvious constraints, architectural rationale, and mathematical or concurrency invariants.
- **Self-Documenting Code**: Rename ambiguous variables or extract helper functions before writing explanatory comments.

### 3.2 Public Interface Documentation
Every exported public class, interface, method, and function MUST have standard structured documentation:
- **Python**: PEP 257 docstrings (Google or Sphinx style):
  ```python
  def calculate_discount(amount: float, rate: float) -> float:
      """Calculate the applied discount on an invoice amount.

      Args:
          amount: Total invoice amount before discount.
          rate: Discount rate between 0.0 and 1.0.

      Returns:
          Net discount value.

      Raises:
          ValueError: If rate is outside [0.0, 1.0].
      """
  ```
- **TypeScript / JavaScript**: TSDoc / JSDoc with `@param`, `@returns`, and `@throws`.
- **Go**: Canonical Godoc comments starting with the exported identifier name:
  ```go
  // CalculateDiscount computes the net discount value for a given invoice amount.
  func CalculateDiscount(amount float64, rate float64) (float64, error) {
  ```
- **C# / Java**: XML documentation comments (`/// <summary>`) or Javadoc (`/** ... */`).

### 3.3 Zero Dead Code Invariant
- Leaving commented-out code blocks in production files is **STRICTLY FORBIDDEN**.
- Dead or obsolete code MUST be deleted immediately. Contributors and AI agents MUST rely on Git version history for code retrieval.

### 3.4 Task Tracking Tags (TODO / FIXME)
To accommodate both enterprise issue trackers and rapid solo-developer/pair-programming workflows, task tags MUST use one of two standardized schemas:

1. **Issue-Tracked Schema (Enterprise / Team)**:
   ```text
   // TODO(#PROJ-1042): Refactor caching mechanism after Redis cluster migration
   // FIXME(#PROJ-1088): Address race condition in concurrent checkout worker
   ```
2. **Author-Date Fallback Schema (Solo / Rapid Prototyping)**:
   ```text
   // TODO(@developer, 2026-09-06): Extract duplicated validation logic into standalone DTO
   // FIXME(@developer, 2026-09-06): Handle edge case when upstream payload contains empty string
   ```
   *Untagged or anonymous `// TODO: fix this` comments are FORBIDDEN.*

---

## 4. Control Flow & Defensive Idioms

1. **Guard Clauses (Early Return)**:
   - Flatten nested conditionals. Verify error states, preconditions, and invalid arguments upfront; return or throw early to maintain a zero-indentation happy path:
     ```typescript
     // GOOD: Flat guard clauses
     function processOrder(order: Order): Result {
       if (!order.isValid) throw new InvalidOrderError();
       if (order.isExpired) return Result.Expired;

       return executePayment(order);
     }
     ```
2. **Immutability by Default**:
   - Prefer immutable structures and declarations (`const` in TS/JS/C++, `readonly` in C#/TS, `final` in Java, `frozen=True` dataclasses in Python).
   - Functions returning values SHOULD NOT mutate input parameters (pure functions).
3. **Boolean Argument Discipline**:
   - Avoid boolean flags as method arguments (e.g., `updateUser(user, true)`). Split into dedicated methods (`activateUser(user)` vs `deactivateUser(user)`) or pass an explicit options/enum object.

---

## 5. Version Control & PR Hygiene

### 5.1 Conventional Commits
All commit messages MUST adhere strictly to the Conventional Commits specification:
```text
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```
- **Allowed Types**:
  - `feat`: New user-facing feature.
  - `fix`: Bug fix.
  - `refactor`: Code change that neither fixes a bug nor adds a feature.
  - `perf`: Performance improvement.
  - `test`: Adding or correcting tests.
  - `docs`: Documentation changes only.
  - `chore`: Toolchain, dependency, or build configuration updates.
- **Subject**: Imperative mood, present tense, lowercase, no trailing period (e.g., `feat(auth): implement refresh token rotation`).
- **Emergency Break-Glass Protocol**: During critical P0/SEV-1 outage mitigation, commits MAY use `fix(hotfix): <description> [skip ci]` to bypass non-blocking checks, followed by mandatory post-incident remediation.

### 5.2 Pull Request Scope & Exemption Boundaries
- **Target Ceiling**: Single PRs SHOULD NOT exceed **400 effective lines of code (LOC)** to ensure review quality and cognitive clarity.
- **Mandatory PR Size Exemptions**: The following file categories are EXEMPT from the 400 LOC ceiling:
  1. Package lockfiles (`package-lock.json`, `yarn.lock`, `go.sum`, `poetry.lock`).
  2. Autogenerated code stubs (Protobuf, gRPC, OpenAPI clients, GraphQL schemas).
  3. Database schema migration snapshots.
  4. Test mock data, binary fixtures, and snapshot files.

### 5.3 Conventional Comments for Code Review
Review comments and AI critique findings MUST prefix comments with standardized intent labels:
- `issue:` Blocking defect, bug, logic error, or security vulnerability.
- `suggestion:` Non-blocking proposal for cleaner design or performance optimization.
- `question:` Request for clarification on intent, design rationale, or trade-offs.
- `nit:` Trivial cosmetic or typo cleanup.
- `praise:` Recognition of exceptionally elegant or clean architecture.