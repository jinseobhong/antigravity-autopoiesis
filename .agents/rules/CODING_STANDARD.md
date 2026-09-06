---
name: "coding_standard"
description: "Enforces ISO/IEC 5055 structural quality, language-idiomatic safety, and modern concurrency standards across Python, TypeScript, Go, Java, C++, and C#."
globs:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.js"
  - "**/*.go"
  - "**/*.java"
  - "**/*.cpp"
  - "**/*.cs"
  - "!**/.venv/**"
  - "!**/node_modules/**"
  - "!**/dist/**"
  - "!**/vendor/**"
  - "!**/__pycache__/**"
---

# Enterprise Source Code Quality Specification (Idiomatic v2.0)

> [!NOTE]
> ### Language-Idiomatic Enforcement & Automated Tooling
> This specification enforces ISO/IEC 5055 code quality and secure programming invariants.
> - **Python**: Enforced via `ruff check .` (Complexity <= 20, Max Args <= 7)
> - **TypeScript / JS**: Enforced via `eslint .`
> - **Go**: Enforced via `golangci-lint run ./...`
> - **Core Rule**: Quality constraints MUST be implemented using native language idioms rather than transposing foreign runtime conventions.

---

## 1. Code Scale & Structural Complexity (Maintainability)

- **File Length**: Maximum **1,000 effective lines of code (LOC)** per file (`CWE-1080`).
- **Cyclomatic Complexity (CC)**: Single function/method McCabe complexity MUST NOT exceed **20** (target $\le 10$ for new code) (`CWE-1121`, `CWE-407`).
- **Parameter Count**: Method signatures MUST NOT exceed **7 parameters**. If $\gt 7$, wrap into a dedicated Parameter Object, Dataclass, or struct DTO (`CWE-1064`).
- **Inheritance & Hierarchy (Composition over Inheritance)**:
  - Inheritance depth MUST NOT exceed **3 levels** (`CWE-1074`). Prefer composition and interfaces/protocols.
  - Multiple inheritance of concrete classes is **FORBIDDEN** (`CWE-1055`).
- **Dead & Duplicated Code**:
  - Commented-out legacy code MUST be deleted; rely on Git history (`CWE-1085`).
  - Copy-paste duplicate blocks MUST NOT exceed **10%** of module volume (`CWE-1041`).

---

## 2. Language-Idiomatic Equality & Operators

Blanket cross-language transposition of `.equals()` is strictly prohibited. Semantic equality MUST follow native language specifications:

| Language | Value / Semantic Equality | Identity / Reference Equality | Prohibited Patterns |
| :--- | :--- | :--- | :--- |
| **Python** | `a == b` (invokes `__eq__`) | `a is b` (singletons: `None`, `True`, `False`) | NEVER invoke `.equals()` (`AttributeError`) |
| **TypeScript / JS** | `a === b` (primitives) | `Object.is(a, b)` | NEVER use loose equality `==` (`CWE-595`); NEVER use `.equals()` |
| **Go** | `a == b` (primitives, structs) | Pointer comparison `p1 == p2` | NEVER invent `.equals()` methods on standard types |
| **Java / C#** | `a.equals(b)` / `Objects.equals(a,b)`| `a == b` (references only) | NEVER use `==` for String or Object value comparison (`CWE-597`) |
| **C++** | `a == b` (via `operator==`) | Pointer address `&a == &b` | Avoid raw pointer identity checks without null verification |

- **Floating-Point Comparison**: NEVER compare floating-point types (`float`, `double`) directly with `==` or `!=`. MUST use epsilon/tolerance margins: `math.isclose(a, b)` or `abs(a - b) < 1e-9` (`CWE-1077`).

---

## 3. Resource & Memory Lifecycle (Reliability)

- **Deterministic Disposal**: OS resources (sockets, file descriptors, database sessions) MUST be released along all execution paths (`CWE-404`, `CWE-772`):
  - **Python**: Enforce `with` context managers.
  - **Go**: Enforce `defer resource.Close()` immediately following successful acquisition error check.
  - **TypeScript/Node**: Enforce `try ... finally` or `using` explicit resource management (TS 5.2+).
  - **Java / C#**: Enforce `try-with-resources` / `using` blocks.
- **Pointer Safety (C / C++)**:
  - Double-free (`CWE-415`) and Use-after-free (`CWE-416`) are strictly forbidden.
  - Raw pointers MUST be validated against `NULL`/`nullptr` before dereferencing (`CWE-476`).
  - Base classes in polymorphic hierarchies MUST declare a virtual destructor (`virtual ~ClassName()`) (`CWE-1087`).
  - Prefer modern smart pointers (`std::unique_ptr`, `std::shared_ptr`) over raw `new`/`delete`.

---

## 4. Modern Concurrency & Asynchronous Safety (Reliability)

### 4.1 Event-Loop & Async/Await Safety (Python `asyncio`, Node.js / TS)
- **Zero Event-Loop Blocking**: NEVER execute long-running CPU loops, synchronous network calls, or blocking file I/O (`time.sleep()`, `fs.readFileSync`) inside async functions. Offload to background worker threads / thread pools (`asyncio.to_thread`, Node worker threads).
- **No Floating Promises**: All async calls in TypeScript MUST be awaited or handled with `.catch()` (`@typescript-eslint/no-floating-promises`).
- **No Sync-over-Async in C#**: NEVER block on tasks using `.Result` or `.Wait()`; use `await` exclusively to prevent deadlocks.

### 4.2 Go Concurrency & Channel Lifecycles (CSP)
- **Context Propagation**: Blocking and I/O operations MUST accept `ctx context.Context` as their first parameter.
- **Goroutine Leak Prevention**: Goroutines MUST NOT block indefinitely on unbuffered channel operations; MUST select on `ctx.Done()`.
- **Channel Ownership**: Only the creating/sending goroutine may close a channel. NEVER send to or close an already closed channel.

### 4.3 Multi-Threaded Locking & Shared State (Java, C#, C++)
- **Immutable Shared State**: Mutable static variables are strictly forbidden in multi-threaded contexts (`CWE-1058`).
- **Lock Object Integrity**: NEVER synchronize on interned strings or boxed primitives (`Integer`). Use private, `final` dedicated lock objects.
- **Deadlock Prevention**: Lock acquisition order MUST be globally uniform across the system (`CWE-833`). NEVER perform blocking I/O while holding a mutex.

---

## 5. Performance & Resource Allocation Invariants

### 5.1 Loop Optimization & Object Allocation Boundaries (`CWE-1050`)
- **Heavy Resource Ban**: NEVER allocate heavy OS resources (database connection pools, network sockets, thread instances, unbuffered file handles) or invoke reflection inside loop bodies.
- **Ephemeral Object Exemption**: Creating short-lived, immutable domain models, dataclasses, tuples, records, or closures inside loops is **explicitly permitted**. Runtimes optimize ephemeral allocations via escape analysis and generational nursery GC.

### 5.2 Idiomatic String Accumulation in Loops (`CWE-1046`)
- **Python**: Append string chunks to a list and join: `''.join(chunks)` or use `io.StringIO`.
- **Go**: Use `var b strings.Builder` with `b.WriteString(chunk)`.
- **TypeScript / JavaScript**: Push chunks into an array and join: `chunks.join('')`.
- **Java / C#**: Use `StringBuilder` (avoid synchronized `StringBuffer`).
- **C++**: Use `std::string::append` or `std::ostringstream`.

---

## 6. Secure Coding & Input/Output Invariants (Security)

- **SQL / NoSQL Injection**: All database queries MUST use parameterized inputs or Prepared Statements. String concatenation or template interpolation in query strings is **STRICTLY FORBIDDEN** (`CWE-89`, `CWE-564`).
- **Path Traversal**: File paths derived from external input MUST be validated and canonicalized against an allowed base directory (`CWE-22`, `CWE-23`).
- **Command Injection**: Untrusted data MUST NEVER be passed directly to OS shell execution (`os.system`, `subprocess.call(..., shell=True)`, `child_process.exec`) (`CWE-78`). Use parameterized argument vectors with `shell=False`.
- **Secret Protection**: Plaintext API keys, passwords, private keys, and tokens MUST NOT reside in source code (`CWE-798`). Inject via environment variables or secret managers.
- **Finite Timeouts**: All synchronous network, RPC, and database calls MUST specify explicit, finite timeouts (`CWE-1088`).
- **Sanitized Audit Logging (`CWE-778`, `CWE-532`)**: Security-relevant events MUST be logged, but passwords, session tokens, authorization headers, and PII MUST be masked/redacted prior to emission.

---

## 7. Syntax, Error Handling & Control Flow

- **No Swallowed Exceptions (`CWE-390`, `CWE-391`)**:
  - Python: Bare `except:` is forbidden. Use `except SpecificException:`. Intentional suppressions must use `contextlib.suppress(SpecificException)`.
  - Java/C#/TS: `catch` blocks must log, handle, or re-throw the exception preserving stack traces.
  - Go: Always check `if err != nil`. Discarding errors via blank identifier `_ = fn()` is prohibited without an explicit inline comment explaining why the error is harmless.
- **Switch & Control Flow**:
  - Languages with implicit fallthrough (Java, C, C++, C#): Every `case` branch MUST end with an explicit `break`, `return`, or `throw` (`CWE-484`).
  - Languages without implicit fallthrough (Go, Python 3.10+ `match/case`): Do NOT add redundant `break` statements.
- **Equality in Conditional Assignments**: Variable assignment inside conditional checks (e.g., `if (a = b)`) is strictly forbidden.

---

## 8. Executable CI Linter Configurations

### Python: Ruff (`pyproject.toml`)
```toml
[tool.ruff.lint]
select = ["C901", "PLR0913", "E", "F", "W", "B", "S"]
[tool.ruff.lint.mccabe]
max-complexity = 20
[tool.ruff.lint.pylint]
max-args = 7
```

### TypeScript: ESLint (`eslint.config.mjs`)
```javascript
export default [
  {
    rules: {
      "complexity": ["error", 20],
      "max-params": ["error", 7],
      "max-lines": ["error", { max: 1000, skipComments: true }],
      "eqeqeq": ["error", "always"]
    }
  }
];
```

### Go: golangci-lint (`.golangci.yml`)
```yaml
linters-settings:
  gocyclo:
    min-complexity: 20
  funlen:
    lines: 1000
linters:
  enable:
    - gocyclo
    - funlen
    - errcheck
    - govet
```