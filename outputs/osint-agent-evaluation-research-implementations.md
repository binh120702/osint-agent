# Research: Public OSINT-agent implementations and evaluation frameworks

## Summary

Seven public GitHub repositories were inspected at pinned commits. `ccmdi/osintbench` is the clearest evaluation framework; `thunderstornX/agentic-osint-agent` is the clearest small operational agent with an explicit evaluation harness; `OpenOSINT/OpenOSINT` and `foron23/OSINT-OA` provide the broadest reusable implementation and test surfaces. None qualifies as fully **runnable** under the strict requirement of offline, containerized, credential-free operation against no live targets: four are **adaptable** through fixtures/mocks or local components, while three are **review-only** because their useful workflows are tightly coupled to live services, targets, or specialized infrastructure.

Four snapshots contain MIT license text. Three do not contain a license file; README statements such as “MIT” are not equivalent to an included license grant and are reported separately. GitHub REST metadata access was rate-limited without authentication, but repository clones, source files, and GitHub Atom commit feeds remained accessible.

## Method and status definitions

- Snapshot date: 2026-09-17.
- **runnable**: source supports meaningful fully offline, containerized, credential-free execution against no live target.
- **adaptable**: meaningful components, fixtures, or mocked tests can be modified or run under those constraints, but the operational workflow cannot.
- **review-only**: useful architecture/source, but operational behavior is fundamentally coupled to live targets/services and no substantial offline evaluation path is supplied.
- **blocked**: essential source could not be inspected. None of the seven is blocked.
- Commit dates below are the dates exposed by GitHub commit Atom feeds. Several are later than the model's pre-existing knowledge and are intentionally reproduced rather than “corrected.”

## Findings

1. **Claim:** `ccmdi/osintbench` is a model benchmark/evaluation harness, not a deployable investigation service. **Sources:** [repository](https://github.com/ccmdi/osintbench), [pinned README](https://github.com/ccmdi/osintbench/blob/77b861ca6a13f28efc5c5156c82e8c26a03aba21/README.md), [runner](https://github.com/ccmdi/osintbench/blob/77b861ca6a13f28efc5c5156c82e8c26a03aba21/osintbench.py), [evaluation script](https://github.com/ccmdi/osintbench/blob/77b861ca6a13f28efc5c5156c82e8c26a03aba21/scripts/eval.py), [tools](https://github.com/ccmdi/osintbench/blob/77b861ca6a13f28efc5c5156c82e8c26a03aba21/tools.py), [license](https://github.com/ccmdi/osintbench/blob/77b861ca6a13f28efc5c5156c82e8c26a03aba21/LICENSE). **Support:** direct evidence. **Confidence:** high.

   - **Pinned revision:** [`77b861ca6a13f28efc5c5156c82e8c26a03aba21`](https://github.com/ccmdi/osintbench/commit/77b861ca6a13f28efc5c5156c82e8c26a03aba21), dated 2025-12-29.
   - **License:** MIT license text is present.
   - **Architecture/capabilities:** a Python runner loads user-created cases, images, context, tasks, and answers; model adapters solve geolocation, identification, temporal, and analysis tasks. Tool support includes local EXIF plus web search, site retrieval, reverse-image/geospatial-oriented functions.
   - **Dependencies/model/network:** provider SDKs and browser/search libraries are declared. Provider credentials are configured through `SAMPLE.env`; most output is evaluated by a Gemini 2 Flash judge, so a stock evaluation run needs an external model API and network. Network tools likewise prevent a full offline run.
   - **Evaluation assets:** dataset schema, runner, answer verification, detailed CSV/run outputs, aggregate and category metrics, and refusal-rate reporting are present. The README explicitly says the user must create a dataset; no distributable benchmark cases were found. No Dockerfile or conventional test suite was visible at the pinned tree.
   - **I/O shape:** input is dataset JSON containing cases, local image paths, context, typed tasks, and ground truth. Output includes per-task responses plus run CSV/metrics.
   - **Safety:** README warns that most outputs are judge-model evaluated and should be checked. The benchmark itself does not impose a target-authorization gate.
   - **Suitability:** **adaptable**. Local parsing, EXIF, verifier logic, and result analysis can be containerized and tested with synthetic fixtures, but a meaningful stock run needs a supplied dataset and external inference/judging; several tools are network-bound.

2. **Claim:** `thunderstornX/agentic-osint-agent` is a compact LangGraph ReAct passive-recon agent with unusually explicit evidence, authority, and evaluation mechanics. **Sources:** [repository](https://github.com/thunderstornX/agentic-osint-agent), [pinned README](https://github.com/thunderstornX/agentic-osint-agent/blob/6a9b4f9082c615bddf703629431adccf1d0291a6/README.md), [CLI](https://github.com/thunderstornX/agentic-osint-agent/blob/6a9b4f9082c615bddf703629431adccf1d0291a6/agent/cli.py), [agent evaluation](https://github.com/thunderstornX/agentic-osint-agent/blob/6a9b4f9082c615bddf703629431adccf1d0291a6/eval/run_eval.py), [tool smoke evaluation](https://github.com/thunderstornX/agentic-osint-agent/blob/6a9b4f9082c615bddf703629431adccf1d0291a6/eval/run_tool_smoke.py), [ethical-use policy](https://github.com/thunderstornX/agentic-osint-agent/blob/6a9b4f9082c615bddf703629431adccf1d0291a6/ETHICAL_USE.md), [license](https://github.com/thunderstornX/agentic-osint-agent/blob/6a9b4f9082c615bddf703629431adccf1d0291a6/LICENSE). **Support:** direct evidence. **Confidence:** high.

   - **Pinned revision:** [`6a9b4f9082c615bddf703629431adccf1d0291a6`](https://github.com/thunderstornX/agentic-osint-agent/commit/6a9b4f9082c615bddf703629431adccf1d0291a6), dated 2026-06-12.
   - **License:** MIT license text is present.
   - **Architecture/capabilities:** LangGraph ReAct loop over WHOIS, DNS, Shodan InternetDB, GitHub search, and Wayback CDX; deterministic evidence ledger; Rich/Typer CLI/TUI; Markdown and JSON reporting.
   - **Dependencies/model/network:** Python requirements include LangGraph, LangChain Core, HTTPX, `python-whois`, and `dnspython`. LLM use requires OpenRouter or NVIDIA NIM credentials; GitHub token is optional. All five investigation sources require DNS/Internet or public APIs.
   - **Docker/tests/evaluation:** CI and tests are present. `run_tool_smoke.py` performs 20 targets x five live tools and outputs row-level CSV plus summary JSON. `run_eval.py` performs full agent runs and records iterations, tool-category coverage, evidence count, elapsed time, finish reason, and a clearly labelled loose citation/hallucination proxy. Committed result artifacts are present. No project Dockerfile was found.
   - **I/O shape:** CLI input is a domain, iteration budget, provider/model, output directory, and mandatory authority statement. Output is structured JSON and Markdown with run metadata, evidence, trace, tools called, timings, and final report.
   - **Safety:** an authority statement is mandatory. Policy limits scope to authorized/public-interest passive reconnaissance, excludes private persons and small organizations, bans authentication/active probing, and warns reports are sensitive. The implementation cannot independently validate the truth of operator authority.
   - **Suitability:** **adaptable**. Mocked tests, report formatting, state transitions, and stored result analysis are useful offline; the full agent and supplied evaluation explicitly require provider credentials and live public sources.

3. **Claim:** `OpenOSINT/OpenOSINT` is the broadest reusable self-hosted toolkit inspected, with direct CLI tools, AI REPL/web interfaces, MCP, Docker, and substantial tests. **Sources:** [repository](https://github.com/OpenOSINT/OpenOSINT), [pinned README](https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/README.md), [package manifest](https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/pyproject.toml), [Dockerfile](https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/Dockerfile), [tests](https://github.com/OpenOSINT/OpenOSINT/tree/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/tests), [license](https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/LICENSE), [disclaimer](https://github.com/OpenOSINT/OpenOSINT/blob/1ab71de6cdb1e6f5423c46e154b7a838b233aae2/DISCLAIMER.md). **Support:** direct evidence. **Confidence:** high.

   - **Pinned revision:** [`1ab71de6cdb1e6f5423c46e154b7a838b233aae2`](https://github.com/OpenOSINT/OpenOSINT/commit/1ab71de6cdb1e6f5423c46e154b7a838b233aae2), dated 2026-09-17.
   - **License:** MIT license text is present; `pyproject.toml` also declares MIT.
   - **Architecture/capabilities:** natural-language agent with hard-stop tool calls; direct non-AI CLI; MCP server; web UI; optional entity graph. The pinned README lists 20 tools spanning email, usernames, breach data, WHOIS, IP/domain/DNS, dorks, phone, Shodan, VirusTotal, Censys, AbuseIPDB, GitHub, GDELT, web scraping, and search footprinting.
   - **Dependencies/model/network:** core Python package uses MCP, Anthropic, FastAPI, HTTP clients, WHOIS/DNS and reporting libraries; optional Ollama and OpenAI-compatible backends are supported. Ollama can remove cloud-model credentials, but investigation tools still call live websites, DNS, or APIs. Several integrations require dedicated API keys; others are keyless but network-dependent.
   - **Docker/tests/evaluation:** Dockerfile builds the web service and installs Holehe, Sherlock, and Sublist3r. A large pytest tree covers tools, MCP/web behavior, schemas, actors and integrations, frequently with mocks/synthetic data. This is principally implementation testing, not a standardized end-to-end accuracy benchmark.
   - **I/O shape:** CLI commands take target identifiers; REPL/web accept natural-language investigations; MCP exposes structured tool calls. Outputs include terminal/JSON-style tool results, Markdown/PDF reports, session history, and optional graph records.
   - **Safety:** authorized-use disclaimer; remote web binding requires explicit `--allow-remote`; proxied/non-loopback requests do not inherit local keys and breach lookups are blocked unless a trusted-proxy opt-in is set. This is a concrete credential-exposure control, not proof that every target is authorized.
   - **Suitability:** **adaptable**. Container and mock-rich tests provide a strong offline adaptation surface, and dork generation is locally deterministic. A meaningful investigation still needs network access; local Ollama only removes the model credential, not the target/source dependency.

4. **Claim:** `osianet/osia-framework` is an infrastructure-heavy intelligence lifecycle platform rather than a portable agent benchmark. **Sources:** [repository](https://github.com/osianet/osia-framework), [pinned README](https://github.com/osianet/osia-framework/blob/38a6dab828dafa8df7da008f80bc2979e9ea7448/README.md), [package manifest](https://github.com/osianet/osia-framework/blob/38a6dab828dafa8df7da008f80bc2979e9ea7448/pyproject.toml), [environment template](https://github.com/osianet/osia-framework/blob/38a6dab828dafa8df7da008f80bc2979e9ea7448/.env.example), [tests](https://github.com/osianet/osia-framework/tree/38a6dab828dafa8df7da008f80bc2979e9ea7448/tests). **Support:** direct evidence. **Confidence:** high.

   - **Pinned revision:** [`38a6dab828dafa8df7da008f80bc2979e9ea7448`](https://github.com/osianet/osia-framework/commit/38a6dab828dafa8df7da008f80bc2979e9ea7448), dated 2026-05-10.
   - **License:** **no license file or package license declaration was found in the inspected snapshot**. Copyright therefore remains reserved by default; absence must not be read as permissive licensing.
   - **Architecture/capabilities:** Signal/API/RSS ingress; Redis queues; Chief of Staff routing; multiple specialist desks; Tavily/Wikipedia/ArXiv/Semantic Scholar/YouTube research; Qdrant RAG; background research and corroboration workers; INTSUM/PDF generation; Signal delivery; optional ADB phone capture and persona automation.
   - **Dependencies/model/network:** pinned Python stack includes Anthropic, Gemini, MCP, Qdrant, Redis, yt-dlp, datasets, browser/scraping and media packages. Configuration requests Venice, OpenRouter, Gemini, Tavily, Hugging Face, Qdrant, Signal and other credentials/endpoints. Deployment assumes Redis, Qdrant, systemd services and in some workflows ARM hardware plus Android/ADB.
   - **Docker/tests/evaluation:** extensive tests, scripts, configuration, service units, ingestion tools and CI assets exist. Setup is systemd/host-service oriented; no general application Dockerfile was found in the inspected top level. Corroboration tiers and reliability metadata are operational features, not a controlled benchmark demonstrating accuracy.
   - **I/O shape:** accepts Signal messages, URLs, RSS items, and authenticated HTTP submissions; emits structured desk reports/INTSUMs, PDFs, Qdrant points, queues, Signal messages, and scheduled multimedia briefings.
   - **Safety:** authenticated ingress/status/queue endpoints, token/UA controls, API-key separation, provenance/reliability tiers, contradiction flags, and human-facing intelligence reports are present. Conversely, README-described uncensored routing, HUMINT, persona automation, account cookies/device automation, and sensitive-person datasets materially raise privacy, authorization, and dual-use risk.
   - **Suitability:** **review-only**. Individual algorithms and unit tests could be isolated, but the useful system is fundamentally distributed and connected to live AI, search, messaging, vector-store, phone, and media services; no bounded credential-free offline evaluation profile is documented.

5. **Claim:** `dazzyddos/OSINT_AI_Agent` is a small educational LangGraph supervisor pipeline that containerizes reconnaissance binaries, not the agent application or a test benchmark. **Sources:** [repository](https://github.com/dazzyddos/OSINT_AI_Agent), [pinned README](https://github.com/dazzyddos/OSINT_AI_Agent/blob/cab0e5ee1835d787d8cafc26d47a8be9e701b0a3/README.md), [requirements](https://github.com/dazzyddos/OSINT_AI_Agent/blob/cab0e5ee1835d787d8cafc26d47a8be9e701b0a3/requirements.txt), [tool Dockerfile](https://github.com/dazzyddos/OSINT_AI_Agent/blob/cab0e5ee1835d787d8cafc26d47a8be9e701b0a3/docker/Dockerfile.tools), [coordinator](https://github.com/dazzyddos/OSINT_AI_Agent/blob/cab0e5ee1835d787d8cafc26d47a8be9e701b0a3/agents/coordinator.py). **Support:** direct evidence. **Confidence:** high.

   - **Pinned revision:** [`cab0e5ee1835d787d8cafc26d47a8be9e701b0a3`](https://github.com/dazzyddos/OSINT_AI_Agent/commit/cab0e5ee1835d787d8cafc26d47a8be9e701b0a3), dated 2026-02-04.
   - **License:** README says “MIT License,” but **no license file containing grant text was found**. Treat licensing as missing/unverified, not MIT.
   - **Architecture/capabilities:** deterministic supervisor phases call recon, Shodan, fingerprint and reporting agents. Subfinder enumerates subdomains, Shodan supplies infrastructure intelligence, and WhatWeb fingerprints responsive sites.
   - **Dependencies/model/network:** LangGraph/LangChain OpenAI-compatible stack, Shodan, Docker SDK and HTTP clients; configuration requires DeepSeek and Shodan keys. Docker is required to run Subfinder/WhatWeb/httpx; all useful collection targets live domains/services.
   - **Docker/tests/evaluation:** `Dockerfile.tools` builds Ubuntu with WhatWeb, Subfinder and httpx. It does not package the Python orchestrator. No test suite, fixtures, evaluation dataset, metrics, or committed benchmark results were found.
   - **I/O shape:** CLI takes a domain and optional checkpointing. State contains target, messages, subdomains, live hosts, Shodan data, technologies, errors, phases and final Markdown-like report.
   - **Safety:** README limits use to authorized, educational, passive reconnaissance and mentions input quoting, resource limits, rate limits and timeouts. WhatWeb/httpx still contact target hosts, so “passive” is not equivalent to “no live-target traffic.”
   - **Suitability:** **review-only**. The graph is pedagogically clear, but there is no offline fixture/evaluation path and every substantive phase depends on a model API, Shodan, or live target probing.

6. **Claim:** `Ordinary0x/The-3rd-Eye` is an early-stage person/identity and social-platform OSINT workflow with structured report output but little reproducibility infrastructure. **Sources:** [repository](https://github.com/Ordinary0x/The-3rd-Eye), [pinned README](https://github.com/Ordinary0x/The-3rd-Eye/blob/378eb5f7713a964b5e5a26d7d9e95f66dd100346/README.md), [main entry point](https://github.com/Ordinary0x/The-3rd-Eye/blob/378eb5f7713a964b5e5a26d7d9e95f66dd100346/main.py), [requirements](https://github.com/Ordinary0x/The-3rd-Eye/blob/378eb5f7713a964b5e5a26d7d9e95f66dd100346/requirements.txt), [license](https://github.com/Ordinary0x/The-3rd-Eye/blob/378eb5f7713a964b5e5a26d7d9e95f66dd100346/LICENSE). **Support:** direct evidence. **Confidence:** high.

   - **Pinned revision:** [`378eb5f7713a964b5e5a26d7d9e95f66dd100346`](https://github.com/Ordinary0x/The-3rd-Eye/commit/378eb5f7713a964b5e5a26d7d9e95f66dd100346), dated 2025-12-18.
   - **License:** MIT license text is present.
   - **Architecture/capabilities:** LangGraph-oriented search agent, URL classification, social-platform scrapers, username/email analysis, media collection and report synthesis. Integrations include Maigret, Holehe, LinkedIn scraper, Instaloader, twscrape and Facebook scraper.
   - **Dependencies/model/network:** requires Google Gemini (`GOOGLE_API_KEY`) for synthesis; HIBP, BreachDirectory and Intelligence X keys are optional. Selenium/browser management and social/network libraries make live Internet and platform behavior central.
   - **Docker/tests/evaluation:** no Dockerfile, CI test suite, benchmark dataset, evaluation script, quantitative metrics, or committed evaluation results were found in the inspected tree.
   - **I/O shape:** interactive `main.py` launches the workflow; outputs a target directory with downloaded photos/media and a fixed-outline `final_report.md`.
   - **Safety:** README states educational, research and defensive use. No mandatory authorization field, allowlist, privacy gate, or target-type enforcement was found. Person and social-account correlation is intrinsically privacy-sensitive.
   - **Suitability:** **review-only**. Some parsers could be unit-tested after extraction, but the represented workflow depends on Gemini, browsers, live social platforms and real identity targets, without an existing offline fixture harness.

7. **Claim:** `foron23/OSINT-OA` is a containerized multi-agent web/API/Telegram application with a strong conventional test surface but no included license grant. **Sources:** [repository](https://github.com/foron23/OSINT-OA), [pinned README](https://github.com/foron23/OSINT-OA/blob/615ebf016991ba85146d8ba7747bb72b561a045e/README.md), [base agent](https://github.com/foron23/OSINT-OA/blob/615ebf016991ba85146d8ba7747bb72b561a045e/agents/base.py), [requirements](https://github.com/foron23/OSINT-OA/blob/615ebf016991ba85146d8ba7747bb72b561a045e/requirements.txt), [Dockerfile](https://github.com/foron23/OSINT-OA/blob/615ebf016991ba85146d8ba7747bb72b561a045e/Dockerfile), [Compose file](https://github.com/foron23/OSINT-OA/blob/615ebf016991ba85146d8ba7747bb72b561a045e/docker-compose.yml), [tests](https://github.com/foron23/OSINT-OA/tree/615ebf016991ba85146d8ba7747bb72b561a045e/tests). **Support:** direct evidence. **Confidence:** high.

   - **Pinned revision:** [`615ebf016991ba85146d8ba7747bb72b561a045e`](https://github.com/foron23/OSINT-OA/commit/615ebf016991ba85146d8ba7747bb72b561a045e), dated 2025-12-23.
   - **License:** README and badge say MIT, but **no LICENSE file containing MIT terms was found**. This is missing/unverified licensing, not a permissive grant.
   - **Architecture/capabilities:** ControlAgent orchestrates specialist LangGraph/ReAct agents; evidence, IOCs, entities and MITRE ATT&CK techniques are stored in SQLite and traces. Interfaces include Flask REST/web UI, MCP support and Telegram commands/report publication. Tools include Tavily/DuckDuckGo, scraping, Maigret, BBOT, Holehe, Amass and PhoneInfoga.
   - **Dependencies/model/network:** OpenAI key is required by the base agents; Tavily and Telegram credentials are optional by feature. Keyless OSINT tools still access search engines, websites and target infrastructure. Requirements include Flask, LangChain/LangGraph, Telethon, search/scraping clients and multiple OSINT packages.
   - **Docker/tests/evaluation:** multi-stage Dockerfile, Compose, health check, non-root app processes, persistent SQLite/Telegram volumes, and many pytest tests are present. Tests include mocks and unit/smoke coverage, but no controlled accuracy dataset or end-to-end benchmark metrics were found. The README's “222 passed” badge is a project claim, not independently reproduced here.
   - **I/O shape:** REST collection accepts `{query, depth}`; Telegram accepts natural-language/command queries; outputs runs, traces, structured JSON evidence, confidence scores, sources and reports stored in SQLite or sent to Telegram.
   - **Safety:** README prohibits stalking/doxing and claims public-only collection; `.env.example` offers timeouts, concurrency limits, rate limits and optional allowed-domain scope. The allowed scope is empty by default, and the source does not establish mandatory authorization validation.
   - **Suitability:** **adaptable**. The container, SQLite model, mocked tests and evidence schemas provide useful offline work, but the operational agents require OpenAI and live tools; no stock credential-free/no-target investigation is meaningful.

## Comparison matrix

| Repository | Type | Pinned SHA / date | License at snapshot | Model/API and network requirements | Docker | Tests / evaluation assets | Primary I/O | Safety controls | Strict suitability |
|---|---|---|---|---|---|---|---|---|---|
| [ccmdi/osintbench](https://github.com/ccmdi/osintbench) | Model benchmark | `77b861c` / 2025-12-29 | MIT text present | Provider keys; Gemini judge; web tools; user dataset | No | Dataset schema, verifier, CSV/metrics; no bundled cases | Case JSON + images -> responses/CSV/metrics | Judge-output caution | **adaptable** |
| [thunderstornX/agentic-osint-agent](https://github.com/thunderstornX/agentic-osint-agent) | Passive ReAct domain agent | `6a9b4f9` / 2026-06-12 | MIT text present | OpenRouter or NVIDIA; optional GitHub token; all tools online | No | CI/tests, 20-target tool and agent eval, committed results | Domain + authority -> JSON/Markdown evidence report | Mandatory authority; explicit passive scope | **adaptable** |
| [OpenOSINT/OpenOSINT](https://github.com/OpenOSINT/OpenOSINT) | Toolkit/agent/MCP/web | `1ab71de` / 2026-09-17 | MIT text present | Cloud or local Ollama; most tools require live network; some API keys | Yes | Large pytest/mocks/integration tree; no standard accuracy benchmark | Target/tool or NL query -> tool results/reports/graph | Authorized-use policy; remote-key and breach controls | **adaptable** |
| [osianet/osia-framework](https://github.com/osianet/osia-framework) | Distributed intelligence platform | `38a6dab` / 2026-05-10 | **No license found** | Many model/search/messaging/vector APIs; Redis/Qdrant/Signal/ADB | No general app image found | Extensive tests/CI/ingestion scripts; operational corroboration, not benchmark | Signal/RSS/API -> INTSUM/PDF/Qdrant/Signal | Auth tokens, provenance tiers; significant HUMINT/persona risk | **review-only** |
| [dazzyddos/OSINT_AI_Agent](https://github.com/dazzyddos/OSINT_AI_Agent) | Educational supervisor recon agent | `cab0e5e` / 2026-02-04 | **No license file; README says MIT** | DeepSeek + Shodan; Docker; live target/domain | Tools image only | No tests/evaluation found | Domain -> state + generated report | Disclaimer, quoting/timeouts; tool traffic reaches targets | **review-only** |
| [Ordinary0x/The-3rd-Eye](https://github.com/Ordinary0x/The-3rd-Eye) | Identity/social OSINT workflow | `378eb5f` / 2025-12-18 | MIT text present | Gemini; browser/social services; optional breach APIs | No | No tests/evaluation found | Interactive person/query -> media + Markdown report | Educational/defensive disclaimer only | **review-only** |
| [foron23/OSINT-OA](https://github.com/foron23/OSINT-OA) | Multi-agent web/API/Telegram app | `615ebf0` / 2025-12-23 | **No license file; README says MIT** | OpenAI required; live search/tools; optional Tavily/Telegram | Yes + Compose | Many pytest mocks/unit/smoke tests; no accuracy benchmark | REST/Telegram query -> traces/evidence/reports/SQLite | Anti-doxing policy; configurable limits/scope | **adaptable** |

## Contradictions

1. **License metadata conflict:** `dazzyddos/OSINT_AI_Agent` and `foron23/OSINT-OA` advertise MIT in README text/badges, but no license text was present in their inspected snapshots. The conservative legal reading is “no license found,” not “MIT.” `source_check` could not establish this negative claim from indexed web passages (status unclear, confidence 0.30); the conclusion is based on direct full-tree inspection. `osianet/osia-framework` likewise had no license file or package declaration found.
2. **“Passive” terminology:** `dazzyddos/OSINT_AI_Agent` calls its workflow passive, while WhatWeb/httpx fingerprinting sends traffic to target hosts. This is passive in the no-exploitation sense, but it fails the study's stronger “no live targets” condition.
3. **OpenOSINT tool count:** the pinned README header says 20 tools while the pinned package description still says 19 tools. Capability should be derived from registered code/tests for formal counting; this review reports the README's explicit table and does not resolve the stale metadata string.
4. **OSIA model descriptions:** the pinned README contains internal prose/table differences about Watch Floor model assignments. This does not affect the suitability result: all described choices are external provider models.

## Missing evidence

- GitHub's unauthenticated REST API returned rate-limit failures during metadata collection. Stars, forks, issue counts, archived status, release state and API-detected SPDX license fields were therefore not treated as verified. Clone access, GitHub HTML/source, raw repository content, and commit Atom feeds succeeded.
- Tests and container builds were inspected but not executed. Claims are about committed assets, not passing status or runtime reproducibility.
- No API-backed agent run was performed and no live target was queried, consistent with the no-credential/no-live-target review boundary.
- Exact negative license findings could not be independently validated by `source_check`; full-tree inspection is stronger evidence for the pinned snapshots, but a license could be added after those commits.
- No project supplied a demonstrated, end-to-end offline/no-credential/no-live-target benchmark profile. “Adaptable” is a researcher inference from mocks, deterministic modules, fixtures, schemas, and container assets.
- Published performance claims, benchmark result quality, and README test-count badges were not independently reproduced.

## Rejected/deprioritized candidates and access failures

- Search-result pages that resolved only to generic `github.com` pages rather than a repository/file were rejected as non-evidence.
- Older OpenOSINT commits surfaced by search were deprioritized because the pinned head source was available.
- No alternate repository was substituted for the seven named candidates; all seven were publicly cloneable and inspectable.
- GitHub REST repository/commit metadata endpoints were rejected for this run after unauthenticated rate limiting. Git clones, exact blob URLs, and commit Atom feeds were used instead.

## Sources

### Kept

- [ccmdi/osintbench at `77b861c`](https://github.com/ccmdi/osintbench/tree/77b861ca6a13f28efc5c5156c82e8c26a03aba21) — primary benchmark source, schema, tools and evaluator.
- [thunderstornX/agentic-osint-agent at `6a9b4f9`](https://github.com/thunderstornX/agentic-osint-agent/tree/6a9b4f9082c615bddf703629431adccf1d0291a6) — primary source for agent, policy, tests and evaluations.
- [OpenOSINT/OpenOSINT at `1ab71de`](https://github.com/OpenOSINT/OpenOSINT/tree/1ab71de6cdb1e6f5423c46e154b7a838b233aae2) — primary source for interfaces, tools, package metadata, Docker and tests.
- [osianet/osia-framework at `38a6dab`](https://github.com/osianet/osia-framework/tree/38a6dab828dafa8df7da008f80bc2979e9ea7448) — primary source for distributed architecture, dependencies and service assumptions.
- [dazzyddos/OSINT_AI_Agent at `cab0e5e`](https://github.com/dazzyddos/OSINT_AI_Agent/tree/cab0e5ee1835d787d8cafc26d47a8be9e701b0a3) — primary educational agent and tool-container source.
- [Ordinary0x/The-3rd-Eye at `378eb5f`](https://github.com/Ordinary0x/The-3rd-Eye/tree/378eb5f7713a964b5e5a26d7d9e95f66dd100346) — primary identity/social agent source.
- [foron23/OSINT-OA at `615ebf0`](https://github.com/foron23/OSINT-OA/tree/615ebf016991ba85146d8ba7747bb72b561a045e) — primary multi-agent application, Docker and tests source.

### Rejected/deprioritized

- GitHub REST API metadata responses — unauthenticated rate-limit failure prevented reliable use.
- Generic GitHub search landing pages — did not identify a stable source file or repository revision.
- Search snippets and README badges as proof of passing tests, performance, or licensing — discovery aids only; source trees and license text control the findings.
- Older OpenOSINT commit pages — superseded by the inspected pinned head.

## Next steps

1. Build a common offline fixture contract: synthetic target, recorded tool responses, fixed model outputs, and a shared report schema. Run the four **adaptable** projects against it in network-denied containers.
2. Separate agent quality from retrieval availability. Score tool-call validity, evidence provenance, citation entailment, refusal behavior, privacy leakage, deterministic replay, and cost/latency independently.
3. Seek explicit license clarification from the maintainers of `osia-framework`, `OSINT_AI_Agent`, and `OSINT-OA` before copying or modifying code.
4. Re-run repository metadata collection with an authenticated GitHub token and execute each test suite/container at the pinned SHA; record platform, lockfile resolution, failures, and network attempts.
