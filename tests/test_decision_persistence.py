"""#214 — 모델 저장(ML-008) · Feature Store(FS-001/002) · NFR-01 버전 기록.

완료 조건: **저장한 모델을 다른 seed 데이터에 불러 평가만 할 수 있다**(GATE 4 전제). 그래서 여기서는
  1. 학습한 Churn · Uplift · CLV 모델이 실제로 저장되고, 다른 프로세스에서 불러도 같은 예측을 내는지,
  2. 불러온 모델을 **다른 seed 로 만든 데이터**에 다시 학습 없이 평가할 수 있는지,
  3. 바뀐 파일 · 덮어쓰기 · Feature 정의가 바뀐 모델을 거부하는지,
  4. Feature Store 가 FS-002 메타 열을 붙이고, 다시 읽으면 값 · attrs 가 그대로인지
를 본다. 시뮬레이터를 쓰지 않는다 — 합성 데이터다.
"""

from __future__ import annotations

import importlib.util
import json
import pickle
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_feature_sprint_table import HAVE_ML, SKIP_REASON

REPO_ROOT = Path(__file__).resolve().parents[1]
HAVE_PARQUET = importlib.util.find_spec("pyarrow") is not None
ARMS = ("T0", "T1", "T2", "T3", "T4")


def _data(seed: int, n: int = 600):
    """합성 RCT — seed 가 다르면 다른 고객 · 다른 값이다(다른 seed 데이터 평가용)."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(seed)
    idx = pd.Index([f"C{seed:02d}{i:05d}" for i in range(n)], name="customer_id")
    X = pd.DataFrame({"recency": rng.exponential(30, n), "frequency": rng.poisson(3, n).astype(float),
                      "monetary": rng.gamma(2.0, 20000, n), "noise": rng.normal(size=n)}, index=idx)
    X.loc[X.index[::17], "monetary"] = np.nan  # 결손을 0 으로 채우지 않는 경로도 지나가게
    treatment = pd.Series(rng.choice(ARMS, n, p=[0.5, 0.125, 0.125, 0.125, 0.125]), index=idx, name="treatment")
    logit = -1.0 + 0.04 * X["recency"] - 0.3 * X["frequency"] - 0.6 * (treatment == "T3")
    churn = pd.Series((rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int), index=idx, name="churn")
    revenue = pd.Series(np.where(churn == 1, 0.0, rng.gamma(2.0, 15000, n)), index=idx, name="revenue")
    return X, treatment, churn, revenue


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestModelStoreRoundTrip(unittest.TestCase):
    """학습 → 저장 → (다른 프로세스에서) 불러오기 → 다른 seed 데이터로 평가만."""

    @classmethod
    def setUpClass(cls) -> None:
        from src.decision import churn, clv, model_store, uplift

        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "models" / "SP-test"
        X, t, y, rev = _data(1)
        cls.X, cls.t, cls.y, cls.rev = X, t, y, rev
        control = t == "T0"
        cls.churn = churn.fit_best_churn(X.loc[control], y.loc[control], seed=1)
        cls.uplift = uplift.fit_uplift(X, t, 1 - y, "t_learner", seed=1)
        cls.clv = clv.fit_clv(X, rev, seed=1)
        cls.records = {}
        for kind, model in (("churn", cls.churn), ("uplift", cls.uplift), ("clv", cls.clv)):
            cls.records[kind] = model_store.save_model(
                cls.root, kind, model, model_version=f"{kind}-test-SP-test",
                dataset_version="rct-t1-test", feature_version="features-test", cv_score={"roc_auc": 0.7},
                score_notes={"test_score": "테스트 — 없음"})
        model_store.write_manifest(cls.root, cls.records, {"run_id": "SP-test", "seed": 1})

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_metadata_has_every_ml008_field(self) -> None:
        for kind, record in self.records.items():
            with self.subTest(kind):
                meta = json.loads((self.root / f"{kind}.json").read_text(encoding="utf-8"))
                for key in ("model_version", "dataset_version", "feature_version", "parameters",
                            "cv_score", "test_score", "created_at", "sha256", "libraries"):
                    self.assertIn(key, meta)
                self.assertEqual(record["sha256"], meta["sha256"])
                self.assertIsNone(meta["test_score"])           # 모르는 값은 null — 0 으로 채우지 않는다
                self.assertIn("test_score", meta["score_notes"])  # 대신 사유가 있다

    def test_another_process_loads_the_same_predictions(self) -> None:
        """pickle 이 같은 프로세스의 캐시에 기대지 않는다 — 새 인터프리터에서 불러 같은 값을 내야 한다."""
        from src.decision import churn, clv, uplift

        X2, *_ = _data(2)
        expected = {"churn": churn.predict_churn_proba(self.churn, X2).round(12).tolist(),
                    "uplift": uplift.predict_cate(self.uplift, X2)["T3"].round(12).tolist(),
                    "clv": clv.predict_clv(self.clv, X2).round(6).tolist()}
        data_file = Path(self.tmp.name) / "X2.pkl"
        data_file.write_bytes(pickle.dumps(X2))
        script = (
            "import json, pickle, sys\n"
            "from src.decision import churn, clv, model_store, uplift\n"
            f"X2 = pickle.loads(open({str(data_file)!r}, 'rb').read())\n"
            f"loaded, _ = model_store.load_models({str(self.root)!r}, expected_feature_version='features-test')\n"
            "out = {'churn': churn.predict_churn_proba(loaded['churn'][0], X2).round(12).tolist(),\n"
            "       'uplift': uplift.predict_cate(loaded['uplift'][0], X2)['T3'].round(12).tolist(),\n"
            "       'clv': clv.predict_clv(loaded['clv'][0], X2).round(6).tolist()}\n"
            "print(json.dumps(out))\n"
        )
        done = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, capture_output=True, text=True,
                              check=False)
        self.assertEqual(0, done.returncode, done.stderr[-2000:])
        got = json.loads(done.stdout.strip().splitlines()[-1])
        for kind in expected:
            with self.subTest(kind):
                self.assertEqual(expected[kind], got[kind])

    def test_loaded_models_evaluate_on_another_seed_without_refitting(self) -> None:
        from src.decision import churn, clv, model_store, uplift

        loaded, manifest = model_store.load_models(self.root, expected_feature_version="features-test")
        self.assertEqual("SP-test", manifest["run"]["run_id"])
        X2, t2, y2, rev2 = _data(3)
        control = t2 == "T0"
        c = churn.evaluate_fitted_churn(loaded["churn"][0], X2.loc[control], y2.loc[control])
        self.assertEqual("fitted_model_evaluation", c["scheme"])
        self.assertEqual(self.churn.threshold, c["threshold"])  # 임계도 저장된 그대로
        self.assertTrue(0.0 <= c["roc_auc"] <= 1.0)
        u = uplift.evaluate_fitted_uplift(loaded["uplift"][0], X2, t2, 1 - y2)
        self.assertEqual("t_learner", u["method"])
        self.assertEqual({"T1", "T2", "T3", "T4"}, {row["arm"] for row in u["by_arm"]})
        self.assertIn("T3", u["ate"])
        v = clv.evaluate_fitted_clv(loaded["clv"][0], X2, rev2)
        self.assertEqual(len(X2), v["n"])
        self.assertIn("spearman", v)

    def test_store_refuses_changed_file_overwrite_and_stale_features(self) -> None:
        from src.decision import model_store

        copy = Path(self.tmp.name) / "tampered"
        shutil.copytree(self.root, copy)
        with self.assertRaises(model_store.ModelStoreError):  # 덮어쓰지 않는다
            model_store.save_model(copy, "churn", self.churn, model_version="x", dataset_version=None,
                                   feature_version=None)
        with self.assertRaises(model_store.ModelStoreError):  # Feature 정의가 바뀐 뒤의 모델
            model_store.load_models(copy, expected_feature_version="features-other")
        with (copy / "clv.pkl").open("ab") as handle:
            handle.write(b"\0")
        with self.assertRaisesRegex(model_store.ModelStoreError, "SHA-256"):
            model_store.load_model(copy, "clv")
        with self.assertRaises(model_store.ModelStoreError):  # manifest 없는 폴더
            model_store.load_models(Path(self.tmp.name))

    def test_mixed_pairs_from_another_run_are_refused_before_unpickling(self) -> None:
        """PR #279 리뷰 R1 — 다른 실행의 **정상** clv.pkl · clv.json 쌍이 섞이면(각 쌍의 해시는 맞다) 묶음과 어긋난다.
        manifest 와 개별 메타데이터를 unpickle 전에 대조해 아무것도 불러오지 않고 멈춘다."""
        from unittest import mock

        from src.decision import clv, model_store

        other = Path(self.tmp.name) / "models" / "SP-other"
        X, _, _, rev = _data(9)
        other_meta = model_store.save_model(other, "clv", clv.fit_clv(X, rev * 2, seed=9),
                                            model_version="clv-test-SP-other", dataset_version="rct-t1-other",
                                            feature_version="features-old-definition", extra={"run_id": "SP-other"})
        model_store.write_manifest(other, {"clv": other_meta}, {"run_id": "SP-other"})
        mixed = Path(self.tmp.name) / "mixed"
        shutil.copytree(self.root, mixed)
        for name in ("clv.pkl", "clv.json"):  # B 의 manifest 는 두고 A 의 정상 쌍으로 바꿔 끼운다
            shutil.copyfile(other / name, mixed / name)
        self.assertEqual(other_meta["sha256"], model_store.load_model(other, "clv")[1]["sha256"])  # 쌍 자체는 정상
        with mock.patch.object(model_store.pickle, "loads", side_effect=AssertionError("unpickle 하면 안 된다")):
            with self.assertRaisesRegex(model_store.ModelStoreError, "manifest 와 개별 메타데이터가 다르다"):
                model_store.load_models(mixed, expected_feature_version="features-test")
            with self.assertRaisesRegex(model_store.ModelStoreError, "manifest 와 개별 메타데이터가 다르다"):
                model_store.load_models(mixed)  # 버전 대조를 하지 않아도 연결 대조는 한다

    def test_run_id_lineage_must_match_the_bundle(self) -> None:
        from src.decision import model_store

        copy = Path(self.tmp.name) / "lineage"
        shutil.copytree(self.root, copy)
        manifest = json.loads((copy / model_store.MANIFEST).read_text(encoding="utf-8"))
        manifest["run"]["run_id"] = "SP-someone-else"
        (copy / model_store.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        meta = json.loads((copy / "churn.json").read_text(encoding="utf-8"))
        meta["run_id"] = "SP-test"
        (copy / "churn.json").write_text(json.dumps(meta), encoding="utf-8")
        with self.assertRaisesRegex(model_store.ModelStoreError, "계보"):
            model_store.load_models(copy, kinds=("churn",))

    def test_unpicklable_model_is_an_error_not_a_silent_skip(self) -> None:
        from src.decision import model_store

        with self.assertRaises(model_store.ModelStoreError):
            model_store.save_model(Path(self.tmp.name) / "bad", "clv", lambda x: x, model_version="x",
                                   dataset_version=None, feature_version=None)


@unittest.skipUnless(HAVE_ML, SKIP_REASON)
class TestPreprocessorPickles(unittest.TestCase):
    """#214 에서 찾은 결함 — `make_preprocessor` 안의 지역 클래스라 학습한 파이프라인을 저장할 수 없었다."""

    def test_fitted_preprocessor_round_trips_with_identical_output(self) -> None:
        import numpy as np

        from src.decision.features.sprint_table import make_preprocessor

        X = np.random.default_rng(0).random((40, 3))
        X[2, 1] = np.nan
        fitted = make_preprocessor().fit(X)
        again = pickle.loads(pickle.dumps(fitted))
        self.assertTrue(np.array_equal(fitted.transform(X), again.transform(X), equal_nan=True))
        self.assertEqual(["quantileclipper", "simpleimputer"], [name for name, _ in fitted.steps])


@unittest.skipUnless(HAVE_ML and HAVE_PARQUET, f"{SKIP_REASON} 또는 pyarrow 미설치")
class TestFeatureStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "processed" / "SP-test"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_round_trip_keeps_values_nan_index_and_attrs(self) -> None:
        import pandas as pd

        from src.decision import feature_store

        X, *_ = _data(4, n=50)
        X.attrs["return_visit_input"] = {"version": "v-test", "experiment_source_allowed": True}
        X.attrs["index_time"] = pd.Timestamp("2026-01-01T00:00:00+09:00")
        feature_store.write_table(self.root, "features_t1", X, feature_version="features-test",
                                  cutoff_time="2026-01-01T00:00:00+09:00")
        back = feature_store.read_table(self.root, "features_t1")
        pd.testing.assert_frame_equal(X, back, check_index_type=False, check_column_type=False)
        self.assertEqual(X.attrs["return_visit_input"], back.attrs["return_visit_input"])
        self.assertEqual("2026-01-01T00:00:00+09:00", back.attrs["index_time"])  # 시각은 문자열로 돌아온다

    def test_every_row_carries_fs002_metadata(self) -> None:
        import pandas as pd

        from src.decision import feature_store

        X, *_ = _data(5, n=20)
        record = feature_store.write_table(self.root, "features_t2", X, feature_version="features-test",
                                           cutoff_time="2026-02-01T00:00:00+09:00")
        raw = pd.read_parquet(self.root / record["file"])
        self.assertEqual(list(feature_store.META_COLUMNS), list(raw.columns[:4]))
        self.assertEqual(sorted(X.index), sorted(raw["customer_id"]))
        self.assertEqual({"features-test"}, set(raw["feature_version"]))
        self.assertEqual(1, raw["feature_cutoff_time"].nunique())
        self.assertIn("미만", record["cutoff_semantics"])

    def test_refuses_overwrite_and_changed_file(self) -> None:
        from src.decision import feature_store

        X, *_ = _data(6, n=20)
        record = feature_store.write_table(self.root, "labels_t1", X, feature_version=None,
                                           cutoff_time="2026-01-01", kind="label")
        with self.assertRaises(feature_store.FeatureStoreError):
            feature_store.write_table(self.root, "labels_t1", X, feature_version=None, cutoff_time="2026-01-01")
        with (self.root / record["file"]).open("ab") as handle:
            handle.write(b"\0")
        with self.assertRaisesRegex(feature_store.FeatureStoreError, "SHA-256"):
            feature_store.read_table(self.root, "labels_t1")


class TestVersions(unittest.TestCase):
    """NFR-01 — 8개 키가 다 있고, 정의 소스가 바뀌면 버전이 바뀐다. 표준 라이브러리만 쓴다."""

    def test_record_has_the_eight_nfr01_keys(self) -> None:
        from src.decision import versions

        record = versions.versions_record(service_version="abc", customer_seed=42, random_seed=[42])
        for key in ("service_version", "simulator_version", "customer_seed", "random_seed", "feature_version",
                    "model_version", "strategy_version", "experiment_version"):
            self.assertIn(key, record)
        self.assertTrue(record["feature_version"].startswith("features-"))
        self.assertTrue(record["strategy_version"].startswith("strategies-"))
        self.assertTrue(record["experiment_version"].startswith("experiment-"))
        self.assertIsNone(record["model_version"])  # 모델을 안 넘기면 null — 추측하지 않는다

    def test_version_moves_when_a_source_changes_and_is_null_when_missing(self) -> None:
        from src.decision import versions

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in versions.FEATURE_SOURCES:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, root / rel)
            before = versions.feature_version(root)
            self.assertEqual(versions.feature_version(REPO_ROOT), before)
            with (root / versions.FEATURE_SOURCES[0]).open("a", encoding="utf-8") as handle:
                handle.write("\n# changed\n")
            self.assertNotEqual(before, versions.feature_version(root))
            (root / versions.FEATURE_SOURCES[1]).unlink()
            self.assertIsNone(versions.feature_version(root))


if __name__ == "__main__":
    unittest.main()
