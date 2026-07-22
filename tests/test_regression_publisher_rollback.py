"""Transactional rollback tests for regression-aware report publication."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from reporting.exceptions import ReportPublishError
from reporting.professional_schema import ProfessionalPostCloseReport
from reporting.publisher import _write_atomic as real_write_atomic
from reporting.publisher import publish_report_v2
from reporting.regression_schema import serialize_regression_artifact
from tests import test_canonical_publisher_integrity as canonical_helpers
from tests.regression_fixtures import make_artifact_document, rehash_artifact_document


class TestRegressionPublisherRollback(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        helper = canonical_helpers.CanonicalPublisherIntegrityTests()
        self.report_document = helper._base_report_doc()
        self.metadata = helper._base_metadata_doc(self.report_document)
        self.report = ProfessionalPostCloseReport.from_document(self.report_document)
        self.artifact = make_artifact_document()
        self.artifact["identity"]["source_manifest"] = self.report.identity.source_manifest
        self.artifact["identity"]["source_manifest_sha256"] = self.report.identity.source_manifest_sha256
        rehash_artifact_document(self.artifact)
        self.regression_bytes = serialize_regression_artifact(self.artifact)
        self.regression_sha = hashlib.sha256(self.regression_bytes).hexdigest()
        self.publish_dir = self.root / "publish" / "reports" / "v2"
        self.index_path = self.publish_dir / "index-TW.json"
        self.latest_path = self.publish_dir / "latest-TW-post_close.json"
        self.previous_index = json.dumps(
            {
                "schema_version": 2,
                "kind": "absorb-report-index",
                "market": "TW",
                "updated_at": "2026-07-16T10:30:00Z",
                "reports": [],
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        self.previous_latest = b'{"previous":true}'
        self.index_path.parent.mkdir(parents=True)
        self.index_path.write_bytes(self.previous_index)
        self.latest_path.write_bytes(self.previous_latest)

    def tearDown(self):
        self.temp.cleanup()

    def publish(self):
        return publish_report_v2(
            self.root,
            copy.deepcopy(self.metadata),
            professional_report=self.report,
            regression_artifact=copy.deepcopy(self.artifact),
        )

    def assert_previous_pointers_restored(self):
        self.assertEqual(self.index_path.read_bytes(), self.previous_index)
        self.assertEqual(self.latest_path.read_bytes(), self.previous_latest)

    def fail_write_for(self, fragment, *, after_write=False):
        def writer(path, content):
            if fragment in path.as_posix():
                if after_write:
                    real_write_atomic(path, content)
                raise OSError(f"injected {fragment} failure")
            return real_write_atomic(path, content)
        return writer

    def test_regression_canonical_metadata_index_and_latest_failures_roll_back(self):
        stages = (
            "objects/regression/",
            "objects/canonical/",
            "metadata/",
            "index-TW.json",
            "latest-TW-post_close.json",
        )
        for stage in stages:
            with self.subTest(stage=stage):
                with tempfile.TemporaryDirectory() as directory:
                    original_root = self.root
                    self.root = Path(directory)
                    self.publish_dir = self.root / "publish" / "reports" / "v2"
                    self.index_path = self.publish_dir / "index-TW.json"
                    self.latest_path = self.publish_dir / "latest-TW-post_close.json"
                    self.index_path.parent.mkdir(parents=True)
                    self.index_path.write_bytes(self.previous_index)
                    self.latest_path.write_bytes(self.previous_latest)
                    try:
                        with mock.patch(
                            "reporting.publisher._write_atomic",
                            side_effect=self.fail_write_for(stage),
                        ):
                            with self.assertRaises(Exception):
                                self.publish()
                        self.assert_previous_pointers_restored()
                        self.assertFalse(any((self.publish_dir / "objects" / "canonical").glob("*.json")))
                        self.assertFalse(any((self.publish_dir / "objects" / "regression").glob("*.json")))
                        self.assertFalse(any((self.publish_dir / "metadata").glob("*.json")))
                    finally:
                        self.root = original_root

    def test_failure_after_latest_replace_restores_previous_latest_and_index(self):
        with mock.patch(
            "reporting.publisher._write_atomic",
            side_effect=self.fail_write_for("latest-TW-post_close.json", after_write=True),
        ):
            with self.assertRaises(Exception):
                self.publish()
        self.assert_previous_pointers_restored()

    def test_regression_readback_mismatch_rolls_back_new_object(self):
        original_read = Path.read_bytes

        def corrupted_read(path):
            payload = original_read(path)
            if "objects/regression/" in path.as_posix():
                return payload[:-1] + bytes([payload[-1] ^ 1])
            return payload

        with mock.patch.object(Path, "read_bytes", corrupted_read):
            with self.assertRaises(ReportPublishError):
                self.publish()
        self.assert_previous_pointers_restored()
        self.assertFalse(any((self.publish_dir / "objects" / "regression").glob("*.json")))

    def test_regression_content_hash_mismatch_writes_nothing(self):
        artifact = copy.deepcopy(self.artifact)
        artifact["presentation"]["headline"] += " tampered"
        with self.assertRaises(ReportPublishError):
            publish_report_v2(
                self.root,
                copy.deepcopy(self.metadata),
                professional_report=self.report,
                regression_artifact=artifact,
            )
        self.assert_previous_pointers_restored()
        self.assertFalse(any((self.publish_dir / "objects" / "regression").glob("*.json")))
        self.assertFalse(any((self.publish_dir / "objects" / "canonical").glob("*.json")))
        self.assertFalse(any((self.publish_dir / "metadata").glob("*.json")))

    def test_existing_identical_regression_object_is_reused_and_never_deleted(self):
        regression_path = self.publish_dir / "objects" / "regression" / f"{self.regression_sha}.json"
        regression_path.parent.mkdir(parents=True)
        regression_path.write_bytes(self.regression_bytes)
        with mock.patch(
            "reporting.publisher._write_atomic",
            side_effect=self.fail_write_for("index-TW.json"),
        ):
            with self.assertRaises(Exception):
                self.publish()
        self.assertEqual(regression_path.read_bytes(), self.regression_bytes)
        self.assert_previous_pointers_restored()

    def test_metadata_conflict_rolls_back_new_regression_and_canonical_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            clean_root = Path(directory)
            latest = publish_report_v2(
                clean_root,
                copy.deepcopy(self.metadata),
                professional_report=self.report,
                regression_artifact=copy.deepcopy(self.artifact),
            )
            metadata_relative = json.loads(latest.read_text(encoding="utf-8"))["metadata"]
        conflict = self.publish_dir / metadata_relative
        conflict.parent.mkdir(parents=True)
        conflict.write_bytes(b"conflict")
        with self.assertRaisesRegex(ReportPublishError, "metadata conflict"):
            self.publish()
        self.assertEqual(conflict.read_bytes(), b"conflict")
        self.assert_previous_pointers_restored()
        self.assertFalse(any((self.publish_dir / "objects" / "regression").glob("*.json")))
        self.assertFalse(any((self.publish_dir / "objects" / "canonical").glob("*.json")))

    def test_cleanup_failure_is_reported_after_restoring_previous_pointers(self):
        original_unlink = Path.unlink

        def fail_regression_cleanup(path, *args, **kwargs):
            if "objects/regression/" in path.as_posix() and path.suffix == ".json":
                raise OSError("cleanup")
            return original_unlink(path, *args, **kwargs)

        with mock.patch(
            "reporting.publisher._write_atomic",
            side_effect=self.fail_write_for("index-TW.json"),
        ), mock.patch.object(Path, "unlink", fail_regression_cleanup):
            with self.assertRaisesRegex(ReportPublishError, "rollback"):
                self.publish()
        self.assert_previous_pointers_restored()

    def test_rollback_only_deletes_paths_created_by_this_publication(self):
        unrelated = self.publish_dir / "objects" / "regression" / "unrelated.json"

        def writer(path, content):
            if path.name == "index-TW.json":
                unrelated.parent.mkdir(parents=True, exist_ok=True)
                unrelated.write_bytes(b"concurrent writer")
                raise OSError("injected index failure")
            return real_write_atomic(path, content)

        with mock.patch("reporting.publisher._write_atomic", side_effect=writer):
            with self.assertRaises(OSError):
                self.publish()
        self.assertEqual(unrelated.read_bytes(), b"concurrent writer")
        self.assert_previous_pointers_restored()


if __name__ == "__main__":
    unittest.main()
