# Pipeline

1) Upload DWG -> store original; create project/version metadata.
2) Convert: DWG to DXF via ODA; log size, layer/entity counts, success/fail.
3) Parse: extract raw entities (LINE, POLYLINE, LWPOLYLINE, CIRCLE, ARC, TEXT, MTEXT, HATCH, BLOCK/INSERT).
4) Semantic: rule-based candidates (spaces, walls, doors/windows) with confidence; keep provisional state.
5) Build stats: project/drawing summaries (areas, lengths, layer/entity counts).
6) Viewer: DXF->SVG/Canvas, layer toggles, zoom/pan, hover metadata.
7) Index: metadata + semantic summaries into RAG index (exclude raw coords/full DXF text).
8) Q&A: LLM retrieves indexed data, answers with uncertainty notes.
