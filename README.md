# slmm
Standalone NL43 addon module (keep separate from the SFM/terra-view codebase).

Run the addon API:
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

Endpoints:
- `GET /health`
- `GET /api/nl43/{unit_id}/config`
- `PUT /api/nl43/{unit_id}/config`
- `GET /api/nl43/{unit_id}/status`
- `POST /api/nl43/{unit_id}/status`

Use `app/services.py` to wire in the TCP connector and call `persist_snapshot` with parsed DOD/DRD data.
