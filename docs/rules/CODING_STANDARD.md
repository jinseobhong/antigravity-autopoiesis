---
name: "coding_standard"
description: "Enforces ISO/IEC 5055 structural quality, secure coding, and clean architecture standards. Use this rule whenever writing, modifying, refactoring, or reviewing source code."
activation: Manual
---

# Enterprise Source Code Quality Specification (ISO/IEC 5055 / OMG ASCQM)

This specification defines mandatory structural, security, and reliability constraints for all generated, refactored, and reviewed code.

---

## 1. Code Scale & Structural Complexity (Maintainability)

- **File Length**: Maximum **1,000 effective lines of code (LOC)** per file (`CWE-1080`).
- **Cyclomatic Complexity (CC)**: Single function/method McCabe complexity MUST NOT exceed **20** (target $\le 10$ for new code) (`CWE-1121`, `CWE-407`).
- **Parameter Count**: Method signatures MUST NOT exceed **7 parameters**. If $\gt 7$, wrap into a dedicated Parameter Object / DTO (`CWE-1064`).
- **Fan-Out (Coupling)**: Functions MUST NOT directly call more than **5 external classes/modules** (`CWE-1048`).
- **Inheritance & Hierarchy**:
  - Inheritance depth MUST NOT exceed **7 levels** (`CWE-1074`).
  - Single classes MUST NOT have more than **10 direct subclasses** (`CWE-1086`).
  - Multiple inheritance of concrete classes is **FORBIDDEN** (`CWE-1055`).
- **Dead & Duplicated Code**:
  - Commented-out legacy code MUST be permanently deleted; rely on VCS (Git) history (`CWE-1085`).
  - Copy-paste duplicate blocks MUST NOT exceed **10%** of the module; extract to shared utilities (`CWE-1041`).

---

## 2. Resource & Memory Lifecycle (Reliability)

- **Deterministic Disposal**: OS resources (sockets, file descriptors, DB connections) MUST be released along all execution paths, including exceptions and early returns (`CWE-404`, `CWE-772`, `CWE-775`).
  - MUST enforce `try-with-resources` (Java), `using` (C#), `with` context managers (Python), or `defer` (Go).
- **Constructor/Destructor Symmetry**: Resources allocated in constructors MUST be released in destructors/finalizers.
- **C++ Virtual Destructors**:
  - Any class with virtual methods MUST declare a virtual destructor (`virtual ~ClassName()`) (`CWE-1087`).
  - Base and derived classes in an inheritance hierarchy MUST have virtual destructors (`CWE-1045`, `CWE-1079`).
- **Pointer Safety**:
  - Double-free (`CWE-415`) and Use-after-free (`CWE-416`, `CWE-825`) are **FORBIDDEN**.
  - All pointer/reference types MUST be validated against `NULL`/`nil` prior to dereferencing (`CWE-476`).

---

## 3. Concurrency & Multithreading (Reliability)

- **Shared State**: Mutable, non-final static variables are **STRICTLY FORBIDDEN** in multithreaded environments (`CWE-1058`, `CWE-567`).
- **Thread-Safe Singleton**: Singleton instantiation MUST use safe synchronization (e.g., double-checked locking with `volatile`, static initialization, or language-level thread-safe containers) (`CWE-543`, `CWE-1096`).
- **Lock Object Integrity**:
  - MUST NOT synchronize on mutable (non-final) objects.
  - MUST NOT synchronize on interned/cached instances (`String` literals, boxed primitives like `Integer`, `Long`).
  - MUST NOT use instance-level locks to protect `static` shared data.
- **Deadlock Prevention**:
  - Lock acquisition order MUST be globally uniform across the system (`CWE-833`).
  - NEVER call `Thread.sleep()` or blocking I/O while holding a lock.
  - Sequential acquisition of non-reentrant locks is **FORBIDDEN** (`CWE-764`).
  - Hazardous thread APIs (`Thread.suspend()`, `Thread.resume()`) are **STRICTLY PROHIBITED**.

---

## 4. Performance & Data Access (Performance Efficiency)

- **Loop Optimization**: NEVER allocate objects, invoke reflection, acquire locks, or perform network/file I/O inside loop bodies (`CWE-1050`).
- **String Concatenation**: NEVER use `+=` on immutable strings inside loops. MUST use `StringBuilder`, `StringBuffer`, or buffered streams (`CWE-1046`).
- **Database & Pooling**:
  - Database access MUST use connection pooling (`CWE-1072`).
  - Single non-SQL business methods SHOULD NOT execute more than **2 distinct ad-hoc database queries**; batch or join where appropriate (`CWE-1073`).
  - High-volume tables ($\ge 1,000,000$ rows): Limit joins to $\le 5$ and subqueries to $\le 3$ (`CWE-1049`).
  - Tables with $\ge 500$ rows MUST use indexed columns in `WHERE` clauses to prevent Full Table Scans (`CWE-1067`).

---

## 5. Secure Coding & Input/Output (Security)

- **Injection Prevention**:
  - SQL/NoSQL queries MUST use parameterized queries / Prepared Statements. String concatenation in queries is **FORBIDDEN** (`CWE-89`, `CWE-564`).
  - File paths MUST be sanitized and canonicalized to prevent directory traversal (`..`) (`CWE-22`, `CWE-23`, `CWE-36`).
  - Web outputs MUST be contextually escaped/sanitized to prevent Cross-Site Scripting (`CWE-79`).
  - Untrusted data MUST NEVER be passed directly to OS shell or runtime command execution (`CWE-78`, `CWE-88`).
- **XXE Defense**: XML parsers MUST explicitly disable DTD processing and external entity resolution (`CWE-611`).
- **Hardcoded Secrets**: Plaintext passwords, private keys, tokens, and sensitive network endpoints are **STRICTLY FORBIDDEN** in source files (`CWE-798`, `CWE-259`, `CWE-321`, `CWE-1051`).
- **Remote Timeouts**: Synchronous network/RPC calls MUST enforce explicit, finite timeouts (`CWE-1088`).
- **Audit Logging**: Security-relevant exceptions (authentication/authorization failures, crypto errors) MUST be recorded in audit logs (`CWE-778`).

---

## 6. Syntax, Operators & Anti-Pattern Prevention

- **No Swallowed Exceptions**: `catch` blocks MUST NOT be empty. Exceptions must be logged, handled, or rethrown with preserved root cause (`CWE-390`, `CWE-391`).
- **Return Value Verification**: Return values indicating status or resource mutations MUST be checked (`CWE-252`).
- **Equality Comparison**:
  - MUST use semantic value equality methods (e.g., `.equals()`), NEVER reference equality (`==`, `!=`), when comparing objects and strings (`CWE-595`, `CWE-597`).
  - NEVER compare floating-point types (`float`, `double`) directly using `==` or `!=`. MUST use epsilon/tolerance margins (`CWE-1077`).
- **Control Flow & Switch Statements**:
  - Every `switch` case branch MUST end with an explicit `break`, `return`, or `throw` (`CWE-484`).
  - Every `switch` construct MUST contain a `default` branch for edge-case handling (`CWE-478`).
  - Nested `switch` statements are **FORBIDDEN**.
  - Unstructured jumps (e.g., `goto` outside switch blocks) are **FORBIDDEN** (`CWE-1075`).
  - NEVER mutate loop counter variables inside the loop body (`CWE-1095`).
  - Variable assignments inside conditional checks (e.g., `if (a = b)`) are **STRICTLY FORBIDDEN**.
```

---

### Key Benefits of this English Format for Antigravity:
1. **Zero Ambiguity**: The use of formal RFC 2119 keywords (`MUST NOT`, `FORBIDDEN`) provides sharp decision boundaries for the AI.
2. **CWE Anchoring**: The explicit `CWE-xxx` tags anchor the LLM's semantic attention to widely recognized static analysis rules.
3. **Token Density**: English tokenization consumes ~40% fewer tokens than Korean for technical rule sets, leaving maximum context window available for your project's actual source code.