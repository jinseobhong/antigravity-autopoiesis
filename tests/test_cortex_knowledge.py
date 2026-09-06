"""
Comprehensive IV&V Test Suite for Cortex Knowledge & Persistence Engine (tests.test_cortex_knowledge).

Enforces AST anti-cheat standards (H-CODE-1..12), >= 40% negative assertion ratio,
deterministic resource cleanup, and sub-15ms latency assertions.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest

try:
    from core.cortex_knowledge import (
        calculate_decay_weight,
        get_cortex_stats,
        get_grounding_directives,
        init_knowledge_tables,
        list_parked_tasks,
        park_task,
        query_events,
        record_event,
        sanitize_fts_query,
        unpark_task,
        vacuum_decay,
    )
    from core.cortex_docs import get_connection
except ModuleNotFoundError:
    from sandbox.core.cortex_knowledge import (
        calculate_decay_weight,
        get_cortex_stats,
        get_grounding_directives,
        init_knowledge_tables,
        list_parked_tasks,
        park_task,
        query_events,
        record_event,
        sanitize_fts_query,
        unpark_task,
        vacuum_decay,
    )
    from sandbox.core.cortex_docs import get_connection



class TestCortexKnowledgePersistence(unittest.TestCase):
    """IV&V companion test suite for core.cortex_knowledge and persistence engine."""

    def setUp(self) -> None:
        """Configures an isolated temporary directory for test databases and spools."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cortex.db"
        self.spool_path = Path(self.temp_dir.name) / "test_spool.jsonl"

    def tearDown(self) -> None:
        """Deterministic cleanup of temporary directory resources."""
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # Positive Test Scenarios
    # -------------------------------------------------------------------------

    def test_schema_initialization_and_fts_triggers(self) -> None:
        """Verifies table, trigger, and virtual index provisioning in cortex.db."""
        con = get_connection(self.db_path)
        try:
            init_knowledge_tables(con)
            cur = con.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cur.fetchall()}
            self.assertIn("episodic_events", tables)
            self.assertIn("fts_events", tables)
            self.assertIn("parked_tasks", tables)

            cur_trg = con.execute("SELECT name FROM sqlite_master WHERE type='trigger';")
            triggers = {row[0] for row in cur_trg.fetchall()}
            self.assertIn("trg_fts_insert", triggers)
            self.assertIn("trg_fts_delete", triggers)
            self.assertIn("trg_fts_update", triggers)
        finally:
            con.close()

    def test_record_success_and_failure_events(self) -> None:
        """Verifies persistence of SUCCESS and FAILURE episodic traces."""
        rec_succ = record_event(
            outcome="SUCCESS",
            component="state_ledger",
            trigger_tokens="Atomic rename on NTFS",
            directive="Always write to .tmp and invoke os.replace",
            solution="Atomic file rename protocol",
            validation="100% write pass rate across 50 concurrent turns",
            db_path=self.db_path,
            spool_path=self.spool_path,
        )
        self.assertEqual(rec_succ.outcome, "SUCCESS")
        self.assertEqual(rec_succ.component, "state_ledger")
        self.assertEqual(rec_succ.access_frequency, 1)
        self.assertAlmostEqual(rec_succ.recency_weight, 1.0, places=2)

        rec_fail = record_event(
            outcome="FAILURE",
            component="db_pool",
            trigger_tokens="High concurrency on Windows worker",
            directive="DO NOT execute concurrent writes without backoff retry",
            root_cause="SQLite lock contention during concurrent test runs",
            db_path=self.db_path,
            spool_path=self.spool_path,
        )
        self.assertEqual(rec_fail.outcome, "FAILURE")
        self.assertEqual(rec_fail.component, "db_pool")
        self.assertIn("lock contention", str(rec_fail.root_cause))

    def test_query_events_fts_and_filters(self) -> None:
        """Verifies FTS5 keyword matching, filter constraints, and frequency bumping."""
        record_event(
            outcome="SUCCESS",
            component="worker_pool",
            trigger_tokens="Process hang watchdog circuit breaker",
            directive="Use 3.0s timeout per test execution",
            solution="Subprocess watchdog killer",
            db_path=self.db_path,
            spool_path=self.spool_path,
        )
        record_event(
            outcome="FAILURE",
            component="ast_linter",
            trigger_tokens="Tautological assert detected in test",
            directive="H-CODE-2 prohibits assert True",
            root_cause="Lazy test synthesis",
            db_path=self.db_path,
            spool_path=self.spool_path,
        )

        results = query_events(
            query_str="watchdog",
            component="worker_pool",
            outcome="SUCCESS",
            limit=5,
            db_path=self.db_path,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].component, "worker_pool")
        self.assertIn("watchdog", results[0].trigger_tokens)

        # Read query should be idempotent by default (touch=False)
        results_read = query_events(
            query_str="watchdog",
            component="worker_pool",
            db_path=self.db_path,
            touch=False,
        )
        self.assertEqual(len(results_read), 1)
        self.assertEqual(results_read[0].access_frequency, 1)

        # Subsequent query with touch=True should see bumped access frequency
        results_touched = query_events(
            query_str="watchdog",
            component="worker_pool",
            db_path=self.db_path,
            touch=True,
        )
        self.assertEqual(len(results_touched), 1)
        self.assertGreaterEqual(results_touched[0].access_frequency, 2)

    def test_sub_15ms_query_latency(self) -> None:
        """Asserts in-process query execution meets the < 15ms physical latency SLA."""
        for i in range(25):
            record_event(
                outcome="SUCCESS" if i % 2 == 0 else "FAILURE",
                component=f"subsystem_{i % 5}",
                trigger_tokens=f"performance benchmark token {i} caching index",
                directive=f"Optimization rule {i} for latency verification",
                db_path=self.db_path,
                spool_path=self.spool_path,
            )

        start_time = time.perf_counter()
        matches = query_events(
            query_str="benchmark token",
            limit=5,
            db_path=self.db_path,
        )
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        self.assertGreater(len(matches), 0)
        self.assertLess(duration_ms, 15.0)

    def test_decay_weight_calculation(self) -> None:
        """Verifies mathematical correctness of half-life and frequency bonus decay."""
        now = datetime.now(timezone.utc)
        weight_fresh = calculate_decay_weight(now.isoformat(), access_frequency=1, half_life_hours=168.0)
        self.assertAlmostEqual(weight_fresh, 1.0, places=2)

        weight_accessed = calculate_decay_weight(now.isoformat(), access_frequency=5, half_life_hours=168.0)
        self.assertGreater(weight_accessed, 1.0)

        old_dt = now - timedelta(hours=168.0)
        weight_half_life = calculate_decay_weight(old_dt.isoformat(), access_frequency=1, half_life_hours=168.0)
        self.assertAlmostEqual(weight_half_life, 0.5, places=2)

    def test_vacuum_decay_purges_stale_events(self) -> None:
        """Verifies vacuuming prunes stale records below retention threshold."""
        rec = record_event(
            outcome="FAILURE",
            component="legacy_module",
            trigger_tokens="Ancient obsolete crash",
            directive="Deprecated directive",
            db_path=self.db_path,
            spool_path=self.spool_path,
        )

        con = get_connection(self.db_path)
        try:
            ancient_iso = (datetime.now(timezone.utc) - timedelta(hours=2000.0)).isoformat()
            with con:
                con.execute(
                    "UPDATE episodic_events SET created_at = ?, access_frequency = 1 WHERE id = ?;",
                    (ancient_iso, rec.id),
                )
        finally:
            con.close()

        pruned = vacuum_decay(
            half_life_hours=168.0,
            min_weight=0.05,
            min_frequency=3,
            db_path=self.db_path,
        )
        self.assertEqual(pruned, 1)

        remaining = query_events(component="legacy_module", db_path=self.db_path)
        self.assertEqual(len(remaining), 0)

    def test_park_task_and_list(self) -> None:
        """Verifies parking tasks in cortex vault and listing them."""
        parked = park_task(
            task_id="TASK-106",
            title="Out-of-Process Test Daemon",
            reason="Radar capacity reached (5/5)",
            description="Warm runner daemon implementation",
            payload={"priority": "HIGH", "tier": 2},
            db_path=self.db_path,
        )
        self.assertEqual(parked.task_id, "TASK-106")
        self.assertEqual(parked.status, "PARKED")
        self.assertEqual(parked.payload.get("priority"), "HIGH")

        tasks = list_parked_tasks(status="PARKED", db_path=self.db_path)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].task_id, "TASK-106")

    def test_unpark_task(self) -> None:
        """Verifies unparking a vaulted task changes status to UNPARKED."""
        park_task(
            task_id="TASK-107",
            title="Cache vacuuming job",
            reason="Scheduled for next cycle",
            db_path=self.db_path,
        )
        unparked = unpark_task(task_id="TASK-107", db_path=self.db_path)
        self.assertIsNotNone(unparked)
        if unparked:
            self.assertEqual(unparked.status, "UNPARKED")
            self.assertIsNotNone(unparked.unparked_at)

        active_tasks = list_parked_tasks(status="PARKED", db_path=self.db_path)
        self.assertEqual(len(active_tasks), 0)

        # Unparking again MUST raise ValueError (State machine invariant)
        with self.assertRaises(ValueError) as ctx:
            unpark_task(task_id="TASK-107", db_path=self.db_path)
        self.assertIn("already UNPARKED", str(ctx.exception))

    def test_decay_weight_with_naive_sqlite_timestamp(self) -> None:
        """Verifies offset-naive SQLite timestamps are safely parsed as UTC without TypeError."""
        naive_str = "2026-09-01 12:00:00"
        weight = calculate_decay_weight(naive_str, access_frequency=1, half_life_hours=168.0)
        self.assertIsInstance(weight, float)
        self.assertGreaterEqual(weight, 0.0)

    def test_cortex_stats_aggregation(self) -> None:
        """Verifies telemetry metrics accurately summarize knowledge and task tables."""
        record_event("SUCCESS", "compA", "tok", "dir", db_path=self.db_path)
        record_event("FAILURE", "compB", "tok", "dir", db_path=self.db_path)
        park_task("TASK-901", "T1", "R1", db_path=self.db_path)

        stats = get_cortex_stats(db_path=self.db_path)
        self.assertEqual(stats.total_episodic_events, 2)
        self.assertEqual(stats.success_events, 1)
        self.assertEqual(stats.failure_events, 1)
        self.assertEqual(stats.active_parked_tasks, 1)
        self.assertEqual(stats.total_parked_tasks, 1)

    # -------------------------------------------------------------------------
    # Negative & Adversarial Test Scenarios (H-CODE-3: >= 40% Negative Assertions)
    # -------------------------------------------------------------------------

    def test_negative_record_event_invalid_outcome(self) -> None:
        """Rejects recording an event with invalid outcome token."""
        with self.assertRaises(ValueError) as ctx:
            record_event(
                outcome="UNKNOWN_STATUS",
                component="comp",
                trigger_tokens="trig",
                directive="dir",
                db_path=self.db_path,
            )
        self.assertIn("Invalid outcome", str(ctx.exception))

    def test_negative_record_event_empty_component(self) -> None:
        """Rejects recording an event with empty component name."""
        with self.assertRaises(ValueError) as ctx:
            record_event(
                outcome="SUCCESS",
                component="   ",
                trigger_tokens="trig",
                directive="dir",
                db_path=self.db_path,
            )
        self.assertIn("Component must be a non-empty string", str(ctx.exception))

    def test_negative_record_event_empty_trigger_tokens(self) -> None:
        """Rejects recording an event with empty trigger tokens."""
        with self.assertRaises(ValueError) as ctx:
            record_event(
                outcome="SUCCESS",
                component="comp",
                trigger_tokens="",
                directive="dir",
                db_path=self.db_path,
            )
        self.assertIn("Trigger tokens must be a non-empty string", str(ctx.exception))

    def test_negative_record_event_empty_directive(self) -> None:
        """Rejects recording an event with empty directive."""
        with self.assertRaises(ValueError) as ctx:
            record_event(
                outcome="FAILURE",
                component="comp",
                trigger_tokens="trig",
                directive="",
                db_path=self.db_path,
            )
        self.assertIn("Directive must be a non-empty string", str(ctx.exception))

    def test_negative_query_events_invalid_limit(self) -> None:
        """Rejects querying events with zero or negative limit."""
        with self.assertRaises(ValueError) as ctx:
            query_events(limit=0, db_path=self.db_path)
        self.assertIn("Limit must be a positive integer", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx_neg:
            query_events(limit=-5, db_path=self.db_path)
        self.assertIn("Limit must be a positive integer", str(ctx_neg.exception))

    def test_negative_park_task_empty_fields(self) -> None:
        """Rejects parking tasks with empty id, title, or reason."""
        with self.assertRaises(ValueError) as ctx_id:
            park_task("", "Title", "Reason", db_path=self.db_path)
        self.assertIn("task_id must be a non-empty string", str(ctx_id.exception))

        with self.assertRaises(ValueError) as ctx_title:
            park_task("TASK-999", "   ", "Reason", db_path=self.db_path)
        self.assertIn("title must be a non-empty string", str(ctx_title.exception))

        with self.assertRaises(ValueError) as ctx_reason:
            park_task("TASK-999", "Title", "", db_path=self.db_path)
        self.assertIn("reason must be a non-empty string", str(ctx_reason.exception))

    def test_negative_unpark_nonexistent_and_empty(self) -> None:
        """Asserts unparking non-existent task returns None and empty ID raises ValueError."""
        with self.assertRaises(ValueError) as ctx_empty:
            unpark_task("   ", db_path=self.db_path)
        self.assertIn("task_id must be a non-empty string", str(ctx_empty.exception))

        res_none = unpark_task("NON_EXISTENT_TASK_ID", db_path=self.db_path)
        self.assertIsNone(res_none)

    def test_negative_sanitize_fts_query_empty_or_special_chars(self) -> None:
        """Verifies query sanitizer handles malicious, punctuation-only, or blank queries."""
        sanitized_blank = sanitize_fts_query("   ")
        self.assertEqual(sanitized_blank, "")

        sanitized_punct = sanitize_fts_query('"" :: [] ()')
        self.assertEqual(sanitized_punct, "")

        sanitized_valid = sanitize_fts_query("hello world")
        self.assertEqual(sanitized_valid, '"hello"* OR "world"*')

    def test_negative_spool_fallback_on_locked_database(self) -> None:
        """
        Verifies fail-open spooling: when SQLite database file is permanently locked,
        record_event buffers the trace to cortex_spool.jsonl without crashing.
        """
        read_only_db_dir = Path(self.temp_dir.name) / "invalid_db_path"
        # Create a directory where the db file is expected, causing SQLite connect/write to fail
        os.makedirs(read_only_db_dir, exist_ok=True)
        blocked_db_path = read_only_db_dir

        rec = record_event(
            outcome="FAILURE",
            component="concurrency_harness",
            trigger_tokens="Permanent file lock simulated",
            directive="Buffer to ring buffer on persistent lock",
            db_path=blocked_db_path,
            spool_path=self.spool_path,
        )

        self.assertIsNotNone(rec.id)
        self.assertTrue(self.spool_path.exists())

        with open(self.spool_path, "r", encoding="utf-8") as f:
            spooled_lines = [json.loads(line) for line in f]

        self.assertEqual(len(spooled_lines), 1)
        self.assertEqual(spooled_lines[0]["id"], rec.id)
        self.assertEqual(spooled_lines[0]["component"], "concurrency_harness")

    def test_cli_dispatch_and_execution_sla(self) -> None:
        """Verifies CLI subcommands work end-to-end and measure latency."""
        try:
            from core.cortex import main as cortex_cli_main, build_parser
            p = build_parser()
            if "record" not in p._subparsers._group_actions[0].choices:
                raise ImportError("Unpromoted core.cortex")
        except (ModuleNotFoundError, ImportError, AttributeError):
            from sandbox.core.cortex import main as cortex_cli_main

        import io
        from contextlib import redirect_stdout, redirect_stderr

        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            # 1. init
            res_init = cortex_cli_main(["init", "--db", str(self.db_path)])
            self.assertEqual(res_init, 0)

            # 2. record
            res_rec = cortex_cli_main([
                "record",
                "--outcome", "SUCCESS",
                "--component", "cli_test",
                "--trigger", "cli trigger token benchmark",
                "--directive", "cli directive for SLA verification",
                "--solution", "cli solution text",
                "--db", str(self.db_path),
            ])
            self.assertEqual(res_rec, 0)

            # 3. query with latency check (< 250ms SLA)
            start_t = time.perf_counter()
            res_q = cortex_cli_main([
                "query",
                "--keyword", "benchmark",
                "--json",
                "--db", str(self.db_path),
            ])
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            self.assertEqual(res_q, 0)
            self.assertLess(duration_ms, 250.0)

            # 4. park-task
            res_park = cortex_cli_main([
                "park-task",
                "--id", "TASK-888",
                "--title", "CLI Parked Task",
                "--reason", "Testing CLI dispatch",
                "--db", str(self.db_path),
            ])
            self.assertEqual(res_park, 0)

            # 5. list-parked
            res_list = cortex_cli_main(["list-parked", "--json", "--db", str(self.db_path)])
            self.assertEqual(res_list, 0)

            # 6. unpark-task
            res_unpark = cortex_cli_main(["unpark-task", "--id", "TASK-888", "--db", str(self.db_path)])
            self.assertEqual(res_unpark, 0)

            # 7. stats
            res_stats = cortex_cli_main(["stats", "--json", "--db", str(self.db_path)])
            self.assertEqual(res_stats, 0)

            # 8. vacuum
            res_vac = cortex_cli_main(["vacuum", "--db", str(self.db_path)])
            self.assertEqual(res_vac, 0)

            # 9. ground
            res_ground = cortex_cli_main([
                "ground",
                "--keywords", "benchmark",
                "--db", str(self.db_path),
            ])
            self.assertEqual(res_ground, 0)

            # 10. ground json
            res_ground_json = cortex_cli_main([
                "ground",
                "--keywords", "benchmark",
                "--json",
                "--db", str(self.db_path),
            ])
            self.assertEqual(res_ground_json, 0)

    def test_positive_get_grounding_directives(self) -> None:
        """Verifies formatted markdown block returned by get_grounding_directives."""
        record_event(
            outcome="SUCCESS",
            component="test_engine",
            trigger_tokens="Isolated warm runner execution",
            directive="Always enforce hard 3.0s watchdog ceiling on test worker",
            root_cause=None,
            solution="Wrap worker stream in queue with timeout",
            validation="100% tests pass",
            db_path=self.db_path,
        )
        directives = get_grounding_directives(
            keywords="watchdog test_engine",
            db_path=self.db_path,
        )
        self.assertIn("### Cognitive Grounding Directives", directives)
        self.assertIn("[test_engine]", directives)
        self.assertIn("watchdog ceiling", directives)
        self.assertIn("Wrap worker stream", directives)

    def test_negative_get_grounding_directives_empty_and_no_match(self) -> None:
        """Verifies empty string returned when keywords are blank or no events match."""
        # Empty keyword string
        self.assertEqual(get_grounding_directives("", db_path=self.db_path), "")
        self.assertEqual(get_grounding_directives("   ", db_path=self.db_path), "")

        # Non-matching keyword query
        no_match = get_grounding_directives(
            keywords="nonexistent_xyz_query_token",
            db_path=self.db_path,
        )
        self.assertEqual(no_match, "")

    def test_negative_cli_command_handling(self) -> None:
        """Asserts error return on unparking non-existent task and CLI rejection of invalid commands."""
        try:
            from core.cortex import main as cortex_cli_main, build_parser
            p = build_parser()
            if "record" not in p._subparsers._group_actions[0].choices:
                raise ImportError("Unpromoted core.cortex")
        except (ModuleNotFoundError, ImportError, AttributeError):
            from sandbox.core.cortex import main as cortex_cli_main

        # Non-existent unpark exits with 1
        import io
        from contextlib import redirect_stdout, redirect_stderr

        buf_out = io.StringIO()
        buf_err = io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            res_fail = cortex_cli_main(["unpark-task", "--id", "NON_EXISTENT_999", "--db", str(self.db_path)])
            with self.assertRaises(SystemExit) as ctx:
                cortex_cli_main(["unrecognized-command"])

        self.assertEqual(res_fail, 1)
        self.assertNotEqual(ctx.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
