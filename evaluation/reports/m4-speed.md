# M4: ingest speed on 2 CPU cores

API and worker as separate processes pinned to 2 CPU cores (two P-cores of an i7-13620H laptop, CPU only), each run on a fresh database, uploads through the HTTP API, real embeddings. The 2-OCPU ARM server is expected to be slower per core; the targets are for that server.

| Document | Pages | Ready, before | Ready, after | First searchable, before | First searchable, after | API /health p95, before | API /health p95, after | API DB read p95, after |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cbe_2006_07 | 60 | 5.4 min | 3.1 min | 5.4 min | 7 s | 322 s (blocked) | 4 ms | 9 ms |
| cbe_2023_24 | 161 | 12.5 min | 9.7 min | 12.5 min | 6 s | 749 s (blocked) | 4 ms | 10 ms |
| dbe_audit_2023 | 95 | 18.0 min | 9.4 min | 18.0 min | 3 s | 1079 s (blocked) | 4 ms | 8 ms |

First searchable: the time until questions can use the document. Before M4 that was only when the whole document was done. Now the pages that have a text layer are indexed first; table pages get their tables and scanned pages their text when the full read finishes (column 'Ready').

Before M4 the upload request itself ran the whole ingest on the API's event loop, so every other request (health checks and logins included) waited until it finished.
