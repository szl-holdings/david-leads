import unittest

from bounded_preflight.preflight import AdmissionController, PreflightError, PreflightQuery


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class QueryTests(unittest.TestCase):
    def test_name_required(self):
        with self.assertRaises(PreflightError):
            PreflightQuery("", "SELECT 1", timeout_s=1.0)

    def test_statement_required(self):
        with self.assertRaises(PreflightError):
            PreflightQuery("q", "   ", timeout_s=1.0)

    def test_timeout_must_be_positive(self):
        with self.assertRaises(PreflightError):
            PreflightQuery("q", "SELECT 1", timeout_s=0.0)

    def test_negative_bound_rejected(self):
        with self.assertRaises(PreflightError):
            AdmissionController(-1)


class AdmissionTests(unittest.TestCase):
    def test_reject_before_execution_when_bound_exceeded(self):
        ctl = AdmissionController(max_statements=1, clock=Clock())
        q1 = PreflightQuery("occupy", "SELECT pg_isready()", timeout_s=1.0)
        admitted, _ = ctl.submit(q1)
        self.assertTrue(admitted)
        called = []
        q2 = PreflightQuery("second", "SELECT 1", timeout_s=1.0,
                            execute=lambda: called.append(2) or 99)
        rec = ctl.execute(q2)
        self.assertFalse(rec.executed)
        self.assertIn("bound exceeded", rec.error)
        self.assertEqual(called, [])
        ctl.release(q1)

    def test_zero_bound_rejects_everything(self):
        ctl = AdmissionController(max_statements=0)
        rec = ctl.execute(PreflightQuery("q", "SELECT 1", timeout_s=1.0, execute=lambda: 1))
        self.assertFalse(rec.executed)
        self.assertIn("bound exceeded", rec.error)

    def test_release_frees_capacity(self):
        ctl = AdmissionController(max_statements=1)
        q = PreflightQuery("q", "SELECT 1", timeout_s=1.0)
        ctl.submit(q)
        self.assertEqual(ctl.in_flight, 1)
        ctl.release(q)
        self.assertEqual(ctl.in_flight, 0)
        admitted, _ = ctl.submit(q)
        self.assertTrue(admitted)


class ExecutionTests(unittest.TestCase):
    def test_success_record(self):
        ctl = AdmissionController(max_statements=2)
        rec = ctl.execute(PreflightQuery("q", "SELECT 1", timeout_s=5.0, execute=lambda: 42))
        self.assertTrue(rec.executed)
        self.assertFalse(rec.timed_out)
        self.assertEqual(rec.result, 42)
        self.assertIsNone(rec.error)
        self.assertEqual(ctl.in_flight, 0)

    def test_timeout_discards_result_fail_closed(self):
        class SlowClock:
            def __init__(self):
                self.t = 0.0

            def __call__(self):
                self.t += 0.4
                return self.t

        ctl = AdmissionController(max_statements=2, clock=SlowClock())
        rec = ctl.execute(PreflightQuery("slow", "SELECT like_sleep_report()", timeout_s=0.1,
                                          execute=lambda: "SHOULD_BE_DISCARDED"))
        self.assertEqual(rec.executed, True)
        self.assertTrue(rec.timed_out)
        self.assertIsNone(rec.result)
        self.assertIn("timeout after", rec.error)
        self.assertIn("discarded", rec.error)
        self.assertEqual(ctl.in_flight, 0)

    def test_query_error_is_data_not_crash(self):
        def boom():
            raise RuntimeError("db unreachable")
        ctl = AdmissionController(max_statements=2)
        rec = ctl.execute(PreflightQuery("q", "SELECT 1", timeout_s=5.0, execute=boom))
        self.assertTrue(rec.executed)
        self.assertFalse(rec.timed_out)
        self.assertIn("RuntimeError", rec.error)
        self.assertEqual(ctl.in_flight, 0)

    def test_record_as_dict_has_opaque_guard(self):
        ctl = AdmissionController(max_statements=2)
        rec = ctl.execute(PreflightQuery("q", "SELECT 1", timeout_s=5.0,
                                         execute=lambda: object()))
        d = rec.as_dict()
        self.assertEqual(d["result"], "<opaque>")


if __name__ == "__main__":
    unittest.main()
