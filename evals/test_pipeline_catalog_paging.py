"""Prevent installed pipelines disappearing when shell output is truncated."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.infrastructure.pipeline_engine import service
from tools.infrastructure.pipeline_engine.commands import dispatch


class CatalogPagingTests(unittest.TestCase):
    def test_all_installed_entries_are_reachable_in_complete_bounded_pages(self):
        entries = service.catalog(compact=True)
        found, offset = [], 0
        while True:
            page = service.catalog_page(entries, offset=offset)
            encoded = json.dumps({"stdout": json.dumps(page)})
            self.assertLess(len(encoded), 32000)
            self.assertEqual(json.loads(json.dumps(page)), page)
            found.extend(page["pipelines"])
            if page["next_offset"] is None:
                break
            self.assertGreater(page["next_offset"], offset)
            offset = page["next_offset"]
        self.assertEqual(found, entries)
        self.assertIn("tcdb_annotator_genome", {row["name"] for row in found})

    def test_named_lookup_preserves_declared_slots_outputs_and_parameters(self):
        with TemporaryDirectory() as root:
            result = dispatch(Path(root), "agent-pipeline catalog --pipeline tcdb_annotator_genome")
        entry, = result["pipelines"]
        self.assertIn("genome_fasta", entry["inputs"])
        self.assertIn("hits", entry["outputs"])
        self.assertIn("genome_context", entry["parameters"])
        self.assertIsNone(result["next_offset"])

    def test_output_budget_can_end_a_page_before_the_requested_limit(self):
        entries = [{"name": f"pipeline-{i}", "description": "a" * 10000} for i in range(4)]
        result = service.catalog_page(entries)
        self.assertEqual(len(result["pipelines"]), 2)
        self.assertEqual(result["next_offset"], 2)
        self.assertLess(len(json.dumps({"stdout": json.dumps(result)})), 32000)

    def test_invalid_page_arguments_are_rejected(self):
        for offset, limit in ((-1, 8), (0, 0), (0, 33)):
            with self.assertRaises(ValueError):
                service.catalog_page([], offset=offset, limit=limit)


if __name__ == "__main__":
    unittest.main()
