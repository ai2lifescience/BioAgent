"""No-network smoke checks for extended biological database adapters."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bio_data.alphafold import query_alphafold
from bio_data.api_http import request_api, validate_api_url
from bio_data.interpro import query_interpro
from bio_data.kegg import query_kegg
from bio_data.pdb import query_pdb
from bio_data.quickgo import query_quickgo


class FakeResponse:
    def __init__(
        self,
        *,
        payload=None,
        text: str = "",
        content: bytes | None = None,
        status_code: int = 200,
    ) -> None:
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")
        self.content = content if content is not None else self.text.encode("utf-8")
        self.status_code = status_code
        self.headers = {"Content-Length": str(len(self.content))}

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(f"HTTP {self.status_code}", response=response)


def _single_response(response: FakeResponse):
    return patch("bio_data.api_http.requests.request", return_value=response)


def main() -> int:
    interpro_payload = {
        "results": [
            {
                "metadata": {
                    "accession": "IPR000001",
                    "name": "Kringle",
                    "type": "Domain",
                    "source_database": "interpro",
                    "go_terms": [{"identifier": "GO:0005515"}],
                },
                "entry_protein_locations": [{"fragments": [{"start": 10, "end": 40}]}],
            }
        ]
    }
    with _single_response(FakeResponse(payload=interpro_payload)):
        interpro = query_interpro("P0A7V8", operation="protein_domains")
    assert interpro["operation"] == "protein_domains"
    assert interpro["records"][0]["accession"] == "IPR000001"
    assert interpro["records"][0]["go_terms"] == ["GO:0005515"]
    assert "retrieved_at" in interpro["provenance"]

    kegg_text = "ENTRY       eco:b0002\nNAME        thrA\nDEFINITION  bifunctional enzyme\n///\n"
    with (
        _single_response(FakeResponse(text=kegg_text)),
        patch("bio_data.kegg._throttle"),
    ):
        kegg = query_kegg("eco:b0002")
    assert kegg["operation"] == "get"
    assert kegg["records"][0]["entry"] == "eco:b0002"
    assert "academic use" in kegg["warnings"][0]

    quickgo_payload = {
        "results": [
            {
                "geneProductId": "UniProtKB:P0A7V8",
                "goId": "GO:0003735",
                "goName": "structural constituent of ribosome",
                "taxonId": 562,
                "evidenceCode": "ECO:0000314",
            }
        ]
    }
    with _single_response(FakeResponse(payload=quickgo_payload)) as quickgo_request:
        quickgo = query_quickgo(
            "UniProtKB:P0A7V8",
            operation="annotation_search",
            taxid=562,
        )
    assert quickgo["records"][0]["go_id"] == "GO:0003735"
    assert quickgo_request.call_args.kwargs["params"]["taxonId"] == 562

    pdb_payload = {
        "struct": {"title": "MOCK STRUCTURE"},
        "exptl": [{"method": "X-RAY DIFFRACTION"}],
        "rcsb_entry_info": {"resolution_combined": [1.8], "polymer_entity_count": 2},
        "rcsb_accession_info": {"initial_release_date": "2000-01-01T00:00:00Z"},
    }
    with _single_response(FakeResponse(payload=pdb_payload)):
        pdb = query_pdb("1a3n")
    assert pdb["records"][0]["identifier"] == "1A3N"
    assert pdb["records"][0]["experimental_methods"] == ["X-RAY DIFFRACTION"]

    alphafold_payload = [
        {
            "entryId": "AF-P0A7V8-F1",
            "uniprotAccession": "P0A7V8",
            "uniprotDescription": "Small ribosomal subunit protein uS4",
            "globalMetricValue": 92.4,
            "cifUrl": "https://alphafold.ebi.ac.uk/files/AF-P0A7V8-F1-model_v4.cif",
            "pdbUrl": "https://alphafold.ebi.ac.uk/files/AF-P0A7V8-F1-model_v4.pdb",
        }
    ]
    with TemporaryDirectory(prefix="bioagent-alphafold-") as temporary_dir:
        responses = [
            FakeResponse(payload=alphafold_payload),
            FakeResponse(content=b"data_mock\n#\n"),
        ]
        with patch("bio_data.api_http.requests.request", side_effect=responses):
            alphafold = query_alphafold(
                "P0A7V8",
                download=True,
                output_dir=temporary_dir,
            )
        artifact = alphafold["artifacts"][0]
        assert Path(artifact["path"]).read_bytes() == b"data_mock\n#\n"
        assert alphafold["records"][0]["mean_plddt"] == 92.4

    with _single_response(FakeResponse(status_code=404)):
        missing = query_alphafold("P0A7V8")
    assert missing["record_count"] == 0
    assert missing["warnings"]

    try:
        validate_api_url("http://www.ebi.ac.uk/not-https")
    except ValueError as exc:
        assert "HTTPS" in str(exc)
    else:
        raise AssertionError("Non-HTTPS database URL was accepted.")

    try:
        validate_api_url("https://example.invalid/api")
    except ValueError as exc:
        assert "allowlisted" in str(exc)
    else:
        raise AssertionError("Non-allowlisted database host was accepted.")

    oversized = FakeResponse(content=b"12345")
    with _single_response(oversized):
        try:
            request_api("GET", "https://www.ebi.ac.uk/test", max_response_bytes=4)
        except RuntimeError as exc:
            assert "size limit" in str(exc)
        else:
            raise AssertionError("Oversized API response was accepted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
