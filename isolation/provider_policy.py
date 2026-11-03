"""Endpoint permissions for existing public database adapters, without credentials."""
import json
import re
from urllib.parse import parse_qs, unquote

PROVIDER_TOOLS = frozenset({'ncbi_retrieval', 'alphafold_download', 'database_lookup', 'blast_search'})


def validate(tool, parsed, method, body, content_type):
    host, path = parsed.hostname, parsed.path
    if parsed.scheme != 'https' or (parsed.port or 443) != 443:
        raise ValueError('Database adapters require HTTPS on port 443.')
    if any(part in {'.', '..'} for part in unquote(path).split('/')):
        raise ValueError('Invalid provider path.')
    allowed = False
    if tool == 'ncbi_retrieval':
        allowed = method == 'GET' and host == 'eutils.ncbi.nlm.nih.gov' and path in {
            '/entrez/eutils/esearch.fcgi', '/entrez/eutils/efetch.fcgi', '/entrez/eutils/esummary.fcgi'}
    elif tool == 'alphafold_download':
        allowed = method == 'GET' and (
            host in {'alphafold.ebi.ac.uk', 'www.alphafold.ebi.ac.uk'} and (
                path.startswith('/api/prediction/') or bool(re.fullmatch(r'/files/AF-[A-Za-z0-9_.-]+\.(?:cif|pdb)', path)))
            or host == 'ftp.ebi.ac.uk' and path.startswith('/pub/databases/alphafold/') and path.endswith(('.cif', '.pdb')))
    elif tool == 'database_lookup':
        allowed = method == 'GET' and (
            host == 'rest.uniprot.org' and path == '/uniprotkb/search'
            or host == 'www.ebi.ac.uk' and (path.startswith('/interpro/api/') or path.startswith('/QuickGO/services/'))
            or host == 'rest.kegg.jp' and path.split('/')[1] in {'find', 'get', 'list', 'link', 'conv', 'info'}
            or host == 'data.rcsb.org' and bool(re.fullmatch(r'/rest/v1/core/entry/[A-Z0-9]{4}', path))
            or host in {'alphafold.ebi.ac.uk', 'www.alphafold.ebi.ac.uk'} and path.startswith('/api/prediction/'))
        if method == 'POST' and host == 'search.rcsb.org' and path == '/rcsbsearch/v2/query':
            allowed = content_type == 'application/json' and isinstance(json.loads(body), dict)
    elif tool == 'blast_search' and host == 'blast.ncbi.nlm.nih.gov' and path == '/Blast.cgi':
        if method == 'GET':
            values = parse_qs(parsed.query)
            allowed = values.get('CMD') == ['Get'] and bool(values.get('RID'))
        elif method == 'POST' and content_type == 'application/x-www-form-urlencoded':
            values = parse_qs(body)
            allowed = values.get('CMD') == ['Put'] and set(values) <= {
                'CMD', 'PROGRAM', 'DATABASE', 'QUERY', 'HITLIST_SIZE', 'EXPECT'}
    if not allowed:
        raise ValueError(f'{tool} cannot access this provider endpoint or HTTP method.')
