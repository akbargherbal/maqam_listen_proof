# Graph Report - maqam_listen_proof  (2026-09-24)

## Corpus Check
- 22 files · ~21,174 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 307 nodes · 527 edges · 22 communities (11 shown, 11 thin omitted)
- Extraction: 96% EXTRACTED · 4% INFERRED · 0% AMBIGUOUS · INFERRED: 20 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `868a5152`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
- app.test.js

## God Nodes (most connected - your core abstractions)
1. `main()` - 15 edges
2. `loadMaqam()` - 13 edges
3. `loadCatalog()` - 11 edges
4. `resolve()` - 9 edges
5. `load_ranking()` - 9 edges
6. `_config_payload()` - 9 edges
7. `api_category()` - 9 edges
8. `results_dir()` - 8 edges
9. `resolve_ref_file()` - 8 edges
10. `_basename_to_ids()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Data Folder Configuration Modal` --semantically_similar_to--> `Settings Panel (gear icon)`  [INFERRED] [semantically similar]
  templates/index.html → README.md
- `Maqam Catalog` --conceptually_related_to--> `Per-take Identity`  [INFERRED]
  catalog_stats_mockup.html → README.md
- `Maqam Catalog` --shares_data_with--> `Reference vs. Candidate Listening & Rating Tool`  [INFERRED]
  catalog_stats_mockup.html → README.md
- `Data Folder Configuration Modal` --shares_data_with--> `Data Folder Configuration (config.json)`  [INFERRED]
  templates/index.html → README.md
- `Star Rating Widget` --shares_data_with--> `Ratings Storage`  [INFERRED]
  templates/index.html → README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Data Folder Configuration Flow** — readme_settings_panel, readme_data_folder_config, templates_index_settings_modal, readme_reference_candidate_listening_tool [INFERRED 0.85]
- **Ratings Review & Progress-Stats Flow** — readme_per_take_identity, readme_ratings_storage, templates_index_star_rating, templates_index_home_view, catalog_stats_mockup_catalog_stats_dashboard [INFERRED 0.85]

## Communities (22 total, 11 thin omitted)

### Community 0 - "Frontend App Logic"
Cohesion: 0.08
Nodes (61): applyExperimentChrome(), applyFilters(), applyRowFilters(), avgStars(), bandCount(), bindFilterControls(), browseState, buildHomeDashboard() (+53 more)

### Community 1 - "Flask Backend API"
Cohesion: 0.06
Nodes (70): api_browse(), api_categories(), api_category(), api_config(), api_set_rating(), api_settings(), api_stats(), _as_float() (+62 more)

### Community 2 - "Export & Migration Scripts"
Cohesion: 0.14
Nodes (21): argparse, csv, audio_root_default(), audio_root_default_cfg_results(), AudioRoot, discover(), experiment_columns(), experiment_ranking() (+13 more)

### Community 3 - "Documentation & UI Concepts"
Cohesion: 0.23
Nodes (14): Catalog Stats Dashboard (Proposed Home Page), Maqam Catalog, Data Folder Configuration (config.json), Per-take Identity, Ratings Storage, Reference vs. Candidate Listening & Rating Tool, Settings Panel (gear icon), Similarity Ranking CSV (+6 more)

### Community 4 - "API Endpoint Tests"
Cohesion: 0.12
Nodes (8): json, pytest, TestConfigEndpoint, TestIndexPage, TestMaqamDetailEndpoint, TestMaqamsEndpoint, TestSettingsEndpoint, TestSaveConfig

### Community 5 - "Pytest Fixtures"
Cohesion: 0.06
Nodes (14): importlib, pathlib, dup_app(), Shared pytest fixtures for the Flask backend (app.py)., Fixture for the duplicate-basename bug: the SAME basename (same_song.mp3)     ex, Tests for the generic, spec-driven A/B testing layer.  These prove the app is no, Reload app.py under a custom experiment spec + isolated data dirs., spec_app() (+6 more)

### Community 6 - "JS Tooling Config"
Cohesion: 0.18
Nodes (10): jsdom, devDependencies, jsdom, vitest, name, private, scripts, test (+2 more)

### Community 11 - "Graphify Plugin"
Cohesion: 0.40
Nodes (3): IMPORTANT: keep the reminder string free of backticks and $(...) constructs., ref_fs, ref_path

### Community 18 - "OpenCode Config"
Cohesion: 0.50
Nodes (3): plugin, $schema, .opencode/plugins/graphify.js

### Community 20 - "app.test.js"
Cohesion: 0.31
Nodes (4): freshApp(), loadVariedMaqam(), mockSequentialFetch(), setupLoadedMaqam()

## Knowledge Gaps
- **14 isolated node(s):** `$schema`, `.opencode/plugins/graphify.js`, `name`, `private`, `type` (+9 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `TestRatingsEndpoint` connect `Ratings Endpoint Tests` to `API Endpoint Tests`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `TestDuplicateBasenameTakes` connect `Duplicate Basename Tests` to `API Endpoint Tests`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Why does `TestLegacyRatingsMigration` connect `Legacy Migration Tests` to `API Endpoint Tests`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Are the 5 inferred relationships involving `Path` (e.g. with `.__init__()` and `discover()`) actually correct?**
  _`Path` has 5 INFERRED edges - model-reasoned connections that need verification._
- **What connects `$schema`, `.opencode/plugins/graphify.js`, `name` to the rest of the system?**
  _14 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Frontend App Logic` be split into smaller, more focused modules?**
  _Cohesion score 0.07787698412698413 - nodes in this community are weakly interconnected._
- **Should `Flask Backend API` be split into smaller, more focused modules?**
  _Cohesion score 0.05707762557077625 - nodes in this community are weakly interconnected._