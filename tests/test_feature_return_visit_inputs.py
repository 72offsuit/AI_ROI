"""#256 ③b: 공개 합성 이벤트로 입력 의미·출처·방문 채널을 대조한다. torch 학습은 하지 않는다."""
from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from uuid import UUID

HAVE_DATA = all(importlib.util.find_spec(name) for name in ("pandas", "numpy"))


@unittest.skipUnless(HAVE_DATA, "BLOCKED: pandas/numpy 미설치 — return_visit 입력 검증 미실행")
class TestReturnVisitInputs(unittest.TestCase):
    t0 = datetime(2026, 7, 1, tzinfo=timezone(timedelta(hours=9)))
    customer = "C00000001"

    def events(self, *, source="simulator", legacy=False):
        import pandas as pd
        from src.decision.data import _coerce

        rows = []
        def emit(kind, at, sid=None, **extra):
            row = {"event_id": str(UUID(int=len(rows)+1, version=4)), "customer_id": self.customer,
                   "event_type": kind, "timestamp": at.isoformat(), "page_type": "home",
                   "service_version": "svc-1.0", "customer_version": "cust-1.0"}
            if source == "simulator":
                row.update(simulator_version="sim-0.8", random_seed=42)
            if sid is not None:
                row["session_id"] = sid
            row.update(extra)
            rows.append(row)

        emit("page_view", self.t0-timedelta(days=200))
        for i in range(5):
            at = self.t0-timedelta(days=10-i)
            sid = f"S-{self.customer}-{int(at.timestamp()*1000):013d}"
            if legacy:
                emit("session_start", at, sid)
                if i:
                    emit("return_visit", at+timedelta(seconds=1), sid)
            else:
                emit("return_visit" if i in (1, 3) else "session_start", at, sid)
            emit("page_view", at+timedelta(minutes=1), sid)
            if i in (0, 2):
                emit("purchase", at+timedelta(minutes=5), sid,
                     order_id=f"O20260601-{i+1:06d}", order_amount=1000)
        return _coerce(pd.DataFrame(rows))

    def test_B_count_and_dl_channel_keep_the_existing_unit(self):
        import numpy as np
        from src.decision.features.sprint_table import build_feature_table
        from src.decision.churn_dl import CHANNELS, build_daily_sequences

        events = self.events()
        table = build_feature_table(events, self.t0)
        self.assertEqual(2, table.loc[self.customer, "return_visit_count_60d"])
        self.assertEqual(5, table.loc[self.customer, "visit_count_60d"])
        seq, meta = build_daily_sequences(events, self.t0, [self.customer], return_metadata=True)
        channel = [name for name, _ in CHANNELS].index("visit")
        self.assertAlmostEqual(5, float(np.expm1(seq[0, :, channel]).sum()), places=5)
        self.assertEqual("purchase_first_session", meta["groups"][0]["definition"])
        self.assertFalse(meta["definition_verified"])

    def test_legacy_observation_is_labeled_without_rewriting_events(self):
        import numpy as np
        import pandas as pd
        from src.decision.features.sprint_table import build_feature_table
        from src.decision.churn_dl import build_daily_sequences
        from src.decision.return_visit import INPUT_METADATA, LEGACY_DEFINITION, label_commerce_definition

        original = self.events(source="commerce", legacy=True)
        saved, attrs = original.copy(deep=True), copy.deepcopy(original.attrs)
        labeled = label_commerce_definition(original, LEGACY_DEFINITION, evidence_ref="export:fixture-before-Ecommerce-54")
        self.assertEqual(LEGACY_DEFINITION, labeled.attrs[INPUT_METADATA]["groups"][0]["definition"])
        table = build_feature_table(labeled, self.t0, purpose="observation")
        seq, metadata = build_daily_sequences(labeled, self.t0, [self.customer],
                                             purpose="observation", return_metadata=True)
        self.assertEqual(4, table.loc[self.customer, "return_visit_count_60d"])
        self.assertEqual(5, table.loc[self.customer, "visit_count_60d"])
        self.assertAlmostEqual(9, float(np.expm1(seq[0, :, 0]).sum()), places=5)
        self.assertEqual(LEGACY_DEFINITION, table.attrs[INPUT_METADATA]["groups"][0]["definition"])
        self.assertEqual(LEGACY_DEFINITION, metadata["groups"][0]["definition"])
        self.assertFalse(metadata["experiment_source_allowed"])
        pd.testing.assert_frame_equal(original, saved)
        self.assertEqual(attrs, original.attrs)
        pd.testing.assert_frame_equal(labeled, original)

    def test_legacy_and_B_are_not_same_meaning_even_with_same_version(self):
        from src.decision.return_visit import (B_DEFINITION, LEGACY_DEFINITION, input_metadata,
                                               label_commerce_definition)
        legacy = label_commerce_definition(self.events(source="commerce", legacy=True),
                                           LEGACY_DEFINITION, evidence_ref="fixture:legacy")
        current = label_commerce_definition(self.events(source="commerce"), B_DEFINITION,
                                            evidence_ref="fixture:proposed-B-not-production")
        a, b = input_metadata(legacy), input_metadata(current)
        self.assertEqual(a["groups"][0]["service_versions"], b["groups"][0]["service_versions"])
        self.assertNotEqual(a["groups"][0]["definition"], b["groups"][0]["definition"])

    def test_unknown_is_not_inferred_from_time_or_version(self):
        from src.decision.return_visit import input_metadata
        events = self.events(source="commerce")
        events["service_version"] = "svc-999.0"
        events["timestamp"] += timedelta(days=10000)
        audit = input_metadata(events)
        self.assertEqual("unknown", audit["groups"][0]["definition"])
        self.assertIsNone(audit["groups"][0]["evidence_ref"])

    def test_all_commerce_definitions_are_observation_only(self):
        from src.decision.features.sprint_table import build_feature_table
        from src.decision.churn_dl import build_daily_sequences
        from src.decision.return_visit import (B_DEFINITION, LEGACY_DEFINITION, label_commerce_definition)
        for definition in (None, B_DEFINITION, LEGACY_DEFINITION):
            with self.subTest(definition=definition):
                events = self.events(source="commerce")
                if definition is not None:
                    events = label_commerce_definition(events, definition, evidence_ref="fixture")
                with self.assertRaisesRegex(ValueError, "observation-only"):
                    build_feature_table(events, self.t0)
                with self.assertRaisesRegex(ValueError, "observation-only"):
                    build_daily_sequences(events, self.t0, [self.customer])

    def test_mixed_sources_with_same_customer_are_rejected_before_aggregation(self):
        import pandas as pd
        from src.decision.features.sprint_table import build_feature_table
        from src.decision.churn_dl import build_daily_sequences
        events = pd.concat([self.events(), self.events(source="commerce")], ignore_index=True)
        for purpose in ("experiment", "observation"):
            with self.subTest(purpose=purpose):
                with self.assertRaisesRegex(ValueError, "mixed event sources"):
                    build_feature_table(events, self.t0, purpose=purpose)
                with self.assertRaisesRegex(ValueError, "mixed event sources"):
                    build_daily_sequences(events, self.t0, [self.customer], purpose=purpose)

    def test_future_commerce_does_not_change_past_inputs(self):
        import numpy as np
        import pandas as pd
        from src.decision.features.sprint_table import build_feature_table
        from src.decision.churn_dl import build_daily_sequences
        events = self.events()
        future = self.events(source="commerce").iloc[:1].copy()
        future["timestamp"] = pd.Timestamp(self.t0).tz_convert(events["timestamp"].dt.tz)
        mixed = pd.concat([events, future], ignore_index=True)
        a, b = build_feature_table(events, self.t0), build_feature_table(mixed, self.t0)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(a.attrs, b.attrs)
        np.testing.assert_array_equal(build_daily_sequences(events, self.t0, [self.customer]),
                                      build_daily_sequences(mixed, self.t0, [self.customer]))

    def test_UTC_and_KST_inputs_have_same_values_and_metadata(self):
        import numpy as np
        import pandas as pd
        from src.decision.features.sprint_table import build_feature_table
        from src.decision.churn_dl import build_daily_sequences
        events = self.events()
        utc = events.copy(); utc["timestamp"] = utc["timestamp"].dt.tz_convert("UTC")
        pd.testing.assert_frame_equal(build_feature_table(events, self.t0), build_feature_table(utc, self.t0))
        np.testing.assert_array_equal(build_daily_sequences(events, self.t0, [self.customer]),
                                      build_daily_sequences(utc, self.t0, [self.customer]))

    def test_source_rule_is_reused_even_with_partial_simulator_metadata(self):
        from src.decision.return_visit import input_metadata
        events = self.events(source="commerce")
        events["random_seed"] = 0
        self.assertEqual("simulator", input_metadata(events)["groups"][0]["source"])
        events["random_seed"] = None; events["simulator_version"] = ""
        self.assertEqual("simulator", input_metadata(events)["groups"][0]["source"])

    def test_bad_declaration_or_purpose_is_rejected(self):
        from src.decision.features.sprint_table import build_feature_table
        from src.decision.return_visit import (DECLARATION, LEGACY_DEFINITION, input_metadata,
                                               label_commerce_definition)
        events = self.events(source="commerce")
        for definition, ref in (("B", "ref"), ("unknown", "ref"), (LEGACY_DEFINITION, " ")):
            with self.subTest(definition=definition, evidence=ref), self.assertRaises(ValueError):
                label_commerce_definition(events, definition, evidence_ref=ref)
        events.attrs[DECLARATION] = {"definition": LEGACY_DEFINITION}
        with self.assertRaises(ValueError):
            input_metadata(events)
        with self.assertRaisesRegex(ValueError, "purpose"):
            build_feature_table(self.events(), self.t0, purpose="training-ish")

    def test_lost_or_mixed_declarations_return_to_unknown(self):
        import pandas as pd
        from src.decision.return_visit import (B_DEFINITION, LEGACY_DEFINITION, input_metadata,
                                               label_commerce_definition)
        events = self.events(source="commerce")
        a = label_commerce_definition(events, LEGACY_DEFINITION, evidence_ref="fixture:legacy")
        b = label_commerce_definition(events, B_DEFINITION, evidence_ref="fixture:B")
        combined = pd.concat([a, b], ignore_index=True)
        self.assertEqual("unknown", input_metadata(combined)["groups"][0]["definition"])
        self.assertFalse(input_metadata(combined)["experiment_source_allowed"])

    def test_observation_table_cannot_be_reused_by_model_column_selection(self):
        from src.decision.features.sprint_table import (FEATURE_NAMES, build_feature_table,
                                                        model_columns, observation_columns)
        from src.decision.return_visit import INPUT_METADATA
        commerce = build_feature_table(self.events(source="commerce"), self.t0, purpose="observation")
        with self.assertRaisesRegex(ValueError, "observation-only"):
            model_columns(commerce)
        self.assertEqual(list(FEATURE_NAMES), observation_columns(commerce))
        simulator = build_feature_table(self.events(), self.t0)
        self.assertEqual(list(FEATURE_NAMES), model_columns(simulator))
        self.assertNotIn(INPUT_METADATA, simulator.columns)

    def test_model_selection_rejects_sprint_table_with_lost_metadata(self):
        from src.decision.features.sprint_table import build_feature_table, model_columns
        table = build_feature_table(self.events(), self.t0)
        table.attrs.clear()
        with self.assertRaisesRegex(ValueError, "metadata missing"):
            model_columns(table)

    def test_sink_loader_retains_unknown_commerce_and_public_versions(self):
        from src.decision.data import load_events
        from src.decision.return_visit import INPUT_METADATA
        from src.measurement.sink import EventSink
        with tempfile.TemporaryDirectory() as temp:
            with EventSink(temp, fmt="jsonl.gz", run_id="fixture-256") as sink:
                sink.write_events(self.events(source="commerce").to_dict("records"))
            loaded = load_events(temp)
            group = loaded.attrs[INPUT_METADATA]["groups"][0]
            self.assertEqual("commerce", group["source"])
            self.assertEqual("unknown", group["definition"])
            self.assertEqual(["svc-1.0"], group["service_versions"])
            self.assertEqual(["cust-1.0"], group["customer_versions"])

    def test_empty_scope_does_not_prove_experiment_source(self):
        import numpy as np
        from src.decision.features.sprint_table import FEATURE_NAMES, build_feature_table, model_columns
        from src.decision.churn_dl import build_daily_sequences
        from src.decision.return_visit import INPUT_METADATA, input_metadata
        empty = self.events().iloc[:0]
        self.assertIsNone(input_metadata(empty)["experiment_source_allowed"])
        table = build_feature_table(empty, self.t0)
        self.assertEqual(0, len(table))
        self.assertEqual(list(FEATURE_NAMES), model_columns(table))
        self.assertEqual([], table.attrs[INPUT_METADATA]["groups"])
        seq, metadata = build_daily_sequences(empty, self.t0, [self.customer], return_metadata=True)
        self.assertEqual((1, 56, 10), seq.shape)
        np.testing.assert_array_equal(seq, np.zeros_like(seq))
        self.assertIsNone(metadata["experiment_source_allowed"])

    def test_inactive_customer_values_do_not_depend_on_active_peers(self):
        import numpy as np
        import pandas as pd
        from src.decision.churn_dl import build_daily_sequences
        events = self.events()
        inactive = events.iloc[:1].copy()
        inactive["customer_id"] = "C00000003"
        inactive["timestamp"] = pd.Timestamp(self.t0-timedelta(days=100)).tz_convert(events["timestamp"].dt.tz)
        events = pd.concat([events, inactive], ignore_index=True)
        alone = build_daily_sequences(events, self.t0, ["C00000003"])
        together = build_daily_sequences(events, self.t0, ["C00000003", self.customer])
        np.testing.assert_array_equal(alone[0], together[0])
        np.testing.assert_array_equal(alone, np.zeros_like(alone))
        self.assertGreater(float(together[1].sum()), 0)

    def test_empty_scope_metadata_cannot_authorize_nonempty_feature_rows(self):
        from src.decision.features.sprint_table import build_feature_table, model_columns
        table = build_feature_table(self.events().iloc[:0], self.t0)
        table.loc[self.customer] = 0
        with self.assertRaisesRegex(ValueError, "unconfirmed"):
            model_columns(table)


if __name__ == "__main__":
    unittest.main()
