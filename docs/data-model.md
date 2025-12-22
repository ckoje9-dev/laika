# Data Model (draft)

- projects: id, name, address, purpose, created_at.
- versions: id, project_id, label/tag, created_at.
- files: id, version_id, path_original, path_dxf, type (dwg/pdf/img/doc), read_only flag for DWG.
- conversion_logs: file_id, status, tool_version, entity_count, layer_count, width/height, message.
- dxf_entities_raw: id, file_id, type, layer, coords, bbox, length, area, attributes.
- semantic_objects: id, file_id, kind (space/wall/door/window/etc), geometry_ref, confidence, source_rule.
- project_stats: project_id, totals (area/rooms/floors), extraction_status.
- qa_history: project_id, question, answer, sources, confidence.
