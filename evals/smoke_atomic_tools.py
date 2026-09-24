"""Offline composition checks for atomic tools and SDK report synthesis."""
from __future__ import annotations

import json
import importlib
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx2
from Bio import SeqIO
from Bio.Seq import Seq
from Bio.SeqFeature import CompoundLocation, SeqFeature, SimpleLocation
from Bio.SeqRecord import SeqRecord
from agents import Agent, Runner
from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call
from harness.context import AgentRunContext
from harness.sessions import SessionMetadata
from harness.streaming import PublicEvents, STREAM_SINK
from harness.tracing import configure_tracing
from tools.agent_tools.reporting import build_report_synthesize
pubmed_module = importlib.import_module("tools.function_tools.sources.pubmed_search")
web_module = importlib.import_module("tools.function_tools.sources.web_search")
retrieve_module = importlib.import_module("tools.function_tools.knowledge.evidence_retrieve")
write_module = importlib.import_module("tools.function_tools.workspace.report_write")
from tools.function_tools.biology.genome_read_features import FeatureDocument, _calculate as read_features
from tools.function_tools.biology.genome_render_map import _calculate as render_map
from tools.function_tools.biology.sequence_find_orfs import _find_orfs as find_orfs, _calculate as orfs
from tools.function_tools.biology.sequence_translate import _calculate as translate
from tools.function_tools.biology.structure_inspect import _calculate as inspect_structure
from tools.function_tools.data_analysis.table_group import _calculate as group
from tools.function_tools.data_analysis.table_profile import _calculate as profile
from tools.infrastructure.tool_support.results import FunctionResult as Result
from tools.infrastructure.tool_support.context import OperationContext

configure_tracing()


class AtomicToolsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.run = {"session_dir": temporary.name, "workspace_dir": str(self.root / "outputs")}
        self.context = AgentRunContext(
            session=SessionMetadata(session_id="atomic", metadata={"run": self.run}), model_key="fixture"
        )

    def workflow(self, name):
        return OperationContext(name, self.run)

    def test_sequence_features_compose_with_renderer(self):
        source = {"sequence": "ATGAAATAG", "path": None, "sequence_type": "dna"}
        result = orfs(source=source, max_records=1, min_length=9, strand="both",
                      context=self.workflow("sequence_find_orfs"))
        document = FeatureDocument.model_validate_json((self.root / result["data"]["features_path"]).read_text())
        self.assertEqual([(f.start, f.end, f.strand) for f in document.records[0].features], [(1, 9, 1)])
        genome_map = render_map(features_path=result["data"]["features_path"], sequence_id=None,
                                label="<untrusted>", context=self.workflow("genome_render_map"))
        map_document = json.loads((self.root / genome_map["data"]["genome_map_path"]).read_text())
        self.assertEqual(map_document["coordinates"], "0-based-half-open")
        self.assertEqual(map_document["title"], "<untrusted>")
        self.assertEqual(map_document["features"][0]["start"], 0)
        self.assertEqual(map_document["features"][0]["end"], 9)
        self.assertEqual((self.root / genome_map["data"]["reference_path"]).read_text(), ">sequence_1\nATGAAATAG\n")
        self.assertFalse(genome_map["data"]["truncated"])
        self.assertEqual(list(find_orfs("ATGNNNAAATAG", 9, "forward")), [])
        reverse = list(find_orfs("CTATTTCAT", 9, "reverse"))
        self.assertEqual((reverse[0].start, reverse[0].end, reverse[0].strand), (1, 9, -1))
        protein = translate(source=source, max_records=1, frame=1, genetic_code=1,
                            context=self.workflow("sequence_translate"))
        self.assertEqual(protein["data"]["records"][0]["protein"], "MK*")

    def test_table_artifacts_retain_groups_beyond_preview(self):
        (self.root / "table.csv").write_text("group,value\n" + "".join(f"g{i},{i}\n" for i in range(105)))
        result = group(path="table.csv", group_by=["group"], column="value", max_rows=1000,
                       context=self.workflow("table_group"))
        self.assertEqual(result["data"]["returned"], 100)
        self.assertEqual(result["data"]["total"], 105)
        self.assertTrue(result["data"]["truncated"])
        complete = profile(path=result["data"]["table_path"], max_rows=1000, context=self.workflow("table_profile"))
        self.assertEqual(complete["data"]["rows"], 105)
        with self.assertRaises(ValueError):
            profile(path=str(self.root / "table.csv"), max_rows=10, context=self.workflow("table_profile"))
        with self.assertRaises(ValueError):
            profile(path="../table.csv", max_rows=10, context=self.workflow("table_profile"))

    def test_annotation_coordinates_and_structure_counts(self):
        (self.root / "input.fa").write_text(">ctg\nATGAAATAG\n")
        annotation = self.root / "input.gff"
        annotation.write_text("ctg\tfixture\tgene\t1\t9\t.\t+\t.\tID=g1\n")
        result = read_features(path="input.gff", fasta_path="input.fa", sequence_id=None,
                               context=self.workflow("genome_read_features"))
        self.assertEqual(result["data"]["total"], 1)
        genome_map = render_map(features_path=result["data"]["features_path"], sequence_id=None,
                                label=None, context=self.workflow("genome_render_map"))
        self.assertEqual((self.root / genome_map["data"]["reference_path"]).read_text(), ">ctg\nATGAAATAG\n")
        annotation.write_text("ctg\tfixture\tgene\t1\t99\t.\t+\t.\tID=g1\n")
        with self.assertRaises(ValueError):
            read_features(path="input.gff", fasta_path="input.fa", sequence_id=None,
                          context=self.workflow("genome_read_features"))
        (self.root / "input.pdb").write_text(
            "ATOM      1  CA AALA A   1       0.000   0.000   0.000  0.50 20.00           C  \n"
            "ATOM      2  CA BALA A   1       1.000   0.000   0.000  0.50 20.00           C  \nEND\n"
        )
        result = inspect_structure(path="input.pdb", context=self.workflow("structure_inspect"))
        self.assertEqual(result["data"]["atom_count"], 2)
        self.assertEqual(result["data"]["residue_count"], 1)

    def test_genbank_reference_and_joined_features_reach_genome_browser(self):
        record = SeqRecord(Seq("ATGAAATAG"), id="ctg")
        record.annotations["molecule_type"] = "DNA"
        record.features = [SeqFeature(
            CompoundLocation([SimpleLocation(0, 3, strand=-1), SimpleLocation(6, 9, strand=-1)]),
            type="CDS", qualifiers={"gene": ["joined_gene"]},
        )]
        SeqIO.write(record, self.root / "input.gb", "genbank")
        result = read_features(path="input.gb", fasta_path=None, sequence_id=None,
                               context=self.workflow("genome_read_features"))
        genome_map = render_map(features_path=result["data"]["features_path"], sequence_id=None,
                                label=None, context=self.workflow("genome_render_map"))
        document = json.loads((self.root / genome_map["data"]["genome_map_path"]).read_text())
        self.assertEqual(document["reference_format"], "fasta")
        self.assertEqual((self.root / document["reference_path"]).read_text(), ">ctg\nATGAAATAG\n")
        self.assertEqual([(f["start"], f["end"], f["strand"]) for f in document["features"]],
                         [(0, 3, "-"), (6, 9, "-")])

    def test_genome_browser_without_bases_uses_sequence_length(self):
        (self.root / "features.json").write_text(json.dumps({
            "records": [{"sequence_id": "ctg", "length": 100, "features": []}],
        }))
        result = render_map(features_path="features.json", sequence_id=None, label=None,
                            context=self.workflow("genome_render_map"))
        document = json.loads((self.root / result["data"]["genome_map_path"]).read_text())
        self.assertEqual(document["reference_format"], "chromsizes")
        self.assertEqual((self.root / document["reference_path"]).read_text(), "ctg\t100\n")
        self.assertEqual(result["files"][0]["kind"], "genome_map")

    async def test_search_retrieve_synthesize_write(self):
        requests = []
        def respond(request):
            requests.append(str(request.url))
            if request.url.path.endswith("esearch.fcgi"):
                return httpx2.Response(200, json={"esearchresult": {"idlist": ["123"], "count": "1"}})
            if request.url.path.endswith("efetch.fcgi"):
                return httpx2.Response(200, text=("<PubmedArticleSet><PubmedArticle><MedlineCitation>"
                    "<PMID>123</PMID><Article><ArticleTitle>Sequence evidence</ArticleTitle>"
                    "<Abstract><AbstractText>A sequence result.</AbstractText></Abstract>"
                    "</Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"))
            return httpx2.Response(200, text='<div class="result"><a class="result__a" href="https://example.org/a">Sequence</a><div class="result__snippet">Sequence evidence</div></div>')
        real_client = httpx2.AsyncClient
        def client(**kwargs):
            kwargs.pop("proxy", None)
            return real_client(**{**kwargs, "trust_env": False}, transport=httpx2.MockTransport(respond))
        with patch.object(pubmed_module.httpx2, "AsyncClient", side_effect=client), patch.object(web_module.httpx2, "AsyncClient", side_effect=client):
            pubmed = Result[pubmed_module.SearchResult].model_validate(await pubmed_module._operation(query="sequence", max_records=1, context=self.workflow("pubmed_search")))
            web = Result[web_module.SearchResult].model_validate(await web_module._operation(query="sequence", domains=["example.org"], max_sources=1, context=self.workflow("web_search")))
        self.assertEqual(len(requests), 3)  # Search only; web pages are not fetched.
        selected = retrieve_module._operation(question="sequence", evidence_paths=[pubmed.data.evidence_path, web.data.evidence_path],
                                                top_k=2, context=self.workflow("evidence_retrieve"))
        self.assertEqual(selected["data"]["returned"], 2)
        draft = {"markdown": "Sequence [evidence](https://pubmed.ncbi.nlm.nih.gov/123/).",
                 "source_ids": [pubmed.data.sources[0].id], "limitations": ["Abstract only."]}
        nested = ScriptedModel([ModelStep(output=[assistant_message(json.dumps(draft))])])
        model = ScriptedModel([
            ModelStep(output=[function_call("report_synthesize", {"question": "What does the sequence evidence show?", "evidence_paths": [selected["data"]["evidence_path"]]}, call_id="draft")]),
            ModelStep(output=[assistant_message("Done.")]),
        ])
        # Explicit consumer exercises Agent.as_tool(on_stream=...) as well as typed input/output.
        events = []
        sink = PublicEvents(self.context, lambda name, payload: events.append((name, payload)))
        token = STREAM_SINK.set(sink)
        try:
            agent = Agent(name="test", model=model, tools=[build_report_synthesize(nested)])
            await Runner.run(agent, "Research sequence evidence", context=self.context)
        finally:
            STREAM_SINK.reset(token)
        self.assertEqual(self.context.tool_results[0]["result"], draft)
        self.assertIn("A sequence result.", nested.calls[0].system_instructions)
        self.assertTrue(any(payload.get("parent_call_id") == "draft" for _, payload in events))
        written = write_module._operation(markdown=draft["markdown"], title="Report", context=self.workflow("report_write"))
        self.assertEqual((self.root / written["data"]["report_path"]).read_text(), draft["markdown"])

    def test_stream_projection_handles_split_host_paths(self):
        events = []
        sink = PublicEvents(self.context, lambda name, payload: events.append(payload))
        for delta in ["File /private/", "host/secret.txt ", "done"]:
            sink(SimpleNamespace(type="raw_response_event", data=SimpleNamespace(
                type="response.output_text.delta", delta=delta, item_id="text", content_index=0)))
        sink.flush()
        text = "".join(item.get("delta", "") for item in events)
        self.assertEqual(text, "File [internal path] done")


if __name__ == "__main__":
    unittest.main()
