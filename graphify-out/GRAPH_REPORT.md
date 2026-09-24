# Graph Report - maqam_listen_proof  (2026-09-24)

## Corpus Check
- Corpus is ~18,292 words - fits in a single context window. You may not need a graph.

## Summary
- 262 nodes · 452 edges · 20 communities (9 shown, 11 thin omitted)
- Extraction: 97% EXTRACTED · 3% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Frontend App Logic
- Flask Backend API
- Export & Migration Scripts
- Documentation & UI Concepts
- API Endpoint Tests
- Pytest Fixtures
- JS Tooling Config
- Ratings Endpoint Tests
- Config & Index Tests
- Duplicate Basename Tests
- Legacy Migration Tests
- Graphify Plugin
- Item Identity Tests
- Config Loading Tests
- Audio Streaming Tests
- Stats Endpoint Tests
- Audio Index Tests
- Reference File Tests
- OpenCode Config
- Graphify Workflow

## God Nodes (most connected - your core abstractions)
1. `loadMaqam()` - 11 edges
2. `main()` - 10 edges
3. `_config_payload()` - 9 edges
4. `results_dir()` - 8 edges
5. `_basename_to_ids()` - 8 edges
6. `api_maqam()` - 8 edges
7. `fetchJSON()` - 8 edges
8. `loadCatalog()` - 8 edges
9. `rateCandidate()` - 8 edges
10. `renderFilteredList()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Data Folder Configuration Modal` --semantically_similar_to--> `Settings Panel (gear icon)`  [INFERRED] [semantically similar]
  templates/index.html → README.md
- `main()` --calls--> `results_dir()`  [EXTRACTED]
  migrate_ratings.py → app.py
- `main()` --calls--> `list_maqams()`  [EXTRACTED]
  migrate_ratings.py → app.py
- `Maqam Catalog` --shares_data_with--> `Reference vs. Candidate Listening & Rating Tool`  [INFERRED]
  catalog_stats_mockup.html → README.md
- `Maqam Catalog` --conceptually_related_to--> `Per-take Identity`  [INFERRED]
  catalog_stats_mockup.html → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Ratings Review & Progress-Stats Flow** — readme_per_take_identity, readme_ratings_storage, templates_index_star_rating, templates_index_home_view, catalog_stats_mockup_catalog_stats_dashboard [INFERRED 0.85]
- **Data Folder Configuration Flow** — readme_settings_panel, readme_data_folder_config, templates_index_settings_modal, readme_reference_candidate_listening_tool [INFERRED 0.85]

## Communities (20 total, 11 thin omitted)

### Community 0 - "Frontend App Logic"
Cohesion: 0.07
Nodes (57): applyFilters(), applyRowFilters(), avgStars(), bandCount(), bindFilterControls(), browseState, buildHomeDashboard(), cap() (+49 more)

### Community 1 - "Flask Backend API"
Cohesion: 0.07
Nodes (57): api_browse(), api_config(), api_maqam(), api_maqams(), api_set_rating(), api_settings(), api_stats(), audio_ref() (+49 more)

### Community 2 - "Export & Migration Scripts"
Cohesion: 0.12
Nodes (20): argparse, csv, audio_root_default(), audio_root_default_cfg_results(), AudioRoot, discover(), find_ranking_csv(), load_ranking_index() (+12 more)

### Community 3 - "Documentation & UI Concepts"
Cohesion: 0.23
Nodes (14): Catalog Stats Dashboard (Proposed Home Page), Maqam Catalog, Data Folder Configuration (config.json), Per-take Identity, Ratings Storage, Reference vs. Candidate Listening & Rating Tool, Settings Panel (gear icon), Similarity Ranking CSV (+6 more)

### Community 4 - "API Endpoint Tests"
Cohesion: 0.15
Nodes (6): pytest, TestConfigEndpoint, TestIndexPage, TestMaqamDetailEndpoint, TestMaqamsEndpoint, TestSettingsEndpoint

### Community 5 - "Pytest Fixtures"
Cohesion: 0.24
Nodes (11): fixture, importlib, pathlib, app_module(), client(), configured_app(), data_dirs(), dup_app() (+3 more)

### Community 6 - "JS Tooling Config"
Cohesion: 0.17
Nodes (10): devDependencies, jsdom, vitest, name, private, scripts, test, type (+2 more)

### Community 8 - "Config & Index Tests"
Cohesion: 0.29
Nodes (3): json, TestResolve, TestSaveConfig

### Community 11 - "Graphify Plugin"
Cohesion: 0.40
Nodes (3): IMPORTANT: keep the reminder string free of backticks and $(...) constructs., ref_fs, ref_path

## Knowledge Gaps
- **15 isolated node(s):** `$schema`, `plugin`, `name`, `private`, `type` (+10 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 99 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TestRatingsEndpoint` connect `Ratings Endpoint Tests` to `API Endpoint Tests`?**
  _High betweenness centrality (0.032) - this node is a cross-community bridge._
- **Why does `TestDuplicateBasenameTakes` connect `Duplicate Basename Tests` to `API Endpoint Tests`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `TestLegacyRatingsMigration` connect `Legacy Migration Tests` to `API Endpoint Tests`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **What connects `$schema`, `plugin`, `name` to the rest of the system?**
  _15 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Frontend App Logic` be split into smaller, more focused modules?**
  _Cohesion score 0.07211538461538461 - nodes in this community are weakly interconnected._
- **Should `Flask Backend API` be split into smaller, more focused modules?**
  _Cohesion score 0.07422559906487435 - nodes in this community are weakly interconnected._
- **Should `Export & Migration Scripts` be split into smaller, more focused modules?**
  _Cohesion score 0.12333333333333334 - nodes in this community are weakly interconnected._