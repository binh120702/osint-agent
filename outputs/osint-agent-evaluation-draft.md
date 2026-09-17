# OSINT Agent Evaluation: Literature-Review Draft

## Executive findings

The literature supports a narrow conclusion: LLM agents can automate portions of OSINT collection, tool selection, extraction, and synthesis, but the evidence does not yet justify treating autonomous OSINT as operationally validated. The strongest recurring evidence is for bounded tasks and analyst-assistance workflows; evidence for end-to-end factual reliability, contradiction resolution, provenance, safety, and reproducibility is sparse. The 74-study survey explicitly identifies this imbalance and recommends a human-AI co-pilot model rather than autonomous deployment ([Palmieri et al., arXiv:2607.03233v1](https://arxiv.org/abs/2607.03233v1)). That conclusion is independently consistent with CyberThreat-Eval's analyst-workflow results, the OSINT Clinic field study, and the limitations reported for toolkit-based acquisition systems ([Chen et al., CyberThreat-Eval](https://arxiv.org/abs/2603.09452); [Mukhopadhyay and Luther, OSINT Clinic](https://doi.org/10.1145/3706598.3713283); [Yuan et al.](https://doi.org/10.3390/fi16120461)).

For this repository's immutable ten-case narrative-investigation protocol, the most useful comparison targets are OSINT- or CTI-specific systems that expose evidence records, tool traces, structured outputs, or analyst-oriented metrics. General agent benchmarks such as GAIA, AgentBench, WebArena, and BrowseComp are methodological context only: they test tool use, browsing, long-horizon interaction, or answer finding, but not this protocol's joint requirements for entity/relation recovery, grounded contradictions, proof-chain coverage, and source traceability ([GAIA](https://arxiv.org/abs/2311.12983); [AgentBench](https://arxiv.org/abs/2308.03688); [WebArena](https://arxiv.org/abs/2307.13854); [BrowseComp](https://arxiv.org/abs/2504.12516)).

No candidate discussed below was executed for this review. Every run-eligibility label is therefore **provisional pending reproducibility screening**. The fixed repository baseline must remain unchanged: ten cases; 8/10 valid structured outputs; 10/10 complete structured outputs and final-report terminations; no runtime failures; mean entity F1 0.3587260914341864, relation F1 0.1204939504939505, finding F1 0.59, grounded contradiction F1 0.5888888888888889, grounded reasoning score 0.8372319688109162, report quality 0.825, source precision 1.0, and source recall 1.0. Retrieval status is `not_annotated` for all ten cases, so retrieval qrels are unavailable and retrieval effectiveness cannot be inferred from these results.

## Scope and method

This review covers 2023-2026 work on agentic or generative-AI OSINT, public OSINT-agent implementations, and adjacent benchmark frameworks. Older foundational work is used only where necessary. Sources were prioritized in this order: publisher or conference records, arXiv records, official dataset pages, pinned source repositories, and the two supplied research tracks. Critical claims were triangulated where possible rather than accepted from a single paper or README.

The academic and implementation evidence was screened against the repository's actual benchmark contract: immutable source snapshots; offline replay for search/content tools; explicit claim, finding, contradiction, and reasoning-step annotations; deterministic reference validation; module-level entity/relation/contradiction scoring; workflow-level finding, traceability, reasoning, and quality scoring; and recorded-model support. The local protocol also distinguishes deterministic source availability from full runtime determinism: offline mode still depends on the production LLM and Neo4j unless benchmark-specific substitutes are supplied, whereas recorded mode with trace-derived graph scoring can avoid both network inference and graph-state drift.

Version identity was normalized conservatively. TechRxiv v1 ([DOI version 1](https://doi.org/10.36227/techrxiv.175623135.54287545/v1)), TechRxiv v2 ([DOI version 2](https://doi.org/10.36227/techrxiv.175623135.54287545/v2)), the London Metropolitan University repository copy ([institutional record](https://repository.londonmet.ac.uk/10859/)), and the IEEE BCCA paper ([IEEE DOI](https://doi.org/10.1109/BCCA66705.2025.11229637)) share the same work title, authorship, and core abstract. They are treated here as preprint revisions and the conference publication of **one work**, not independent corroborating studies. No inspected source proved otherwise.

A separate identity issue concerns the 74-study survey. The canonical citable record is **“Agentic and Generative AI for Open-Source Intelligence and Cyber Investigations: Taxonomy, Evaluation, Challenges, and Future Directions,” arXiv:2607.03233v1**, submitted 3 July 2026 ([arXiv record](https://arxiv.org/abs/2607.03233v1)). Earlier repository/search-index material exposed under a framework-style title or repository status should be treated as earlier or inconsistent repository metadata, not as a second peer-reviewed survey and not as another version of the BCCA framework paper. The survey is currently an arXiv v1 preprint in the evidence reviewed here; its 74-study synthesis is useful secondary evidence, but its corpus-level conclusions still require checking against primary studies.

## OSINT-specific academic systems

### Toolkit-based threat-intelligence acquisition

Yuan et al. present a scheduling-memory-toolkit architecture in which an LLM iterates through thought, action, and observation and can call vulnerability search, WHOIS, and Bing search tools. Their test set covers question answering, tool choice, parameter passing, and impact on the base model; the authors report improved OSINT acquisition accuracy but also acknowledge manual tool integration, dependence on tool quality and timeliness, and inherited LLM reasoning and bias limitations ([Future Internet article](https://doi.org/10.3390/fi16120461)). This is direct evidence for modular tool orchestration, not evidence that the system satisfies narrative investigation, source-level citation, contradiction, or offline reproducibility requirements.

### Unified agentic OSINT framework

Palmieri et al. propose an integrated architecture combining agent planning, RAG, multi-source ingestion, LLM analysis, scenario generation, tool orchestration, human escalation, and ethical safeguards. The missing-person proof of concept is relevant to multi-source investigative synthesis, but the paper describes future broader benchmarking and open-source release; it does not supply a community benchmark that permits independent cross-system comparison. Claims of improved coverage, accuracy, and speed should therefore be read as system-specific proof-of-concept claims rather than independently replicated operational results ([TechRxiv v2](https://doi.org/10.36227/techrxiv.175623135.54287545/v2); [IEEE BCCA publication](https://doi.org/10.1109/BCCA66705.2025.11229637)). Treating the preprints and IEEE article as separate confirming studies would artificially inflate the evidence.

### OSINT-derived CTI classification and extraction

Shafee et al. compare several chatbots on binary classification and named-entity recognition using OSINT-derived Twitter CTI data. They report strong binary-classification F1 for GPT-4 (0.94) and GPT4All (0.90), while all evaluated chatbots lag on cybersecurity entity recognition ([journal DOI](https://doi.org/10.1016/j.eswa.2024.125509); [arXiv record](https://arxiv.org/abs/2401.15127)). This task-level result aligns with the present baseline's much weaker entity and relation recovery than source-reference validity, but it is not directly comparable: the datasets, entity schema, workflow, and metrics differ, and their study is not an agentic end-to-end investigation.

### Human-centered OSINT investigations

The OSINT Clinic study co-designed AI support with six students and piloted the workflow with three small businesses. It found practical opportunities to streamline investigations alongside privacy and progress-monitoring problems ([ACM DOI](https://doi.org/10.1145/3706598.3713283); [arXiv record](https://arxiv.org/abs/2409.11672)). Its small sample does not establish general performance, but it supplies evidence absent from architecture-only papers: OSINT quality is also a collaboration, oversight, privacy, and workflow-observability problem. This supports retaining human review and detailed traces even when deterministic scoring improves.

### Field-level synthesis

The 74-study survey finds that collection and analysis receive substantially more attention than verification, reporting, dissemination, and decision support; it also reports little end-to-end empirical hallucination measurement and no mature shared cross-study OSINT-agent benchmark ([arXiv:2607.03233v1](https://arxiv.org/abs/2607.03233v1)). These are secondary-source conclusions, but they are consistent with the primary papers above and with the inspected public repositories, most of which provide application tests or demos rather than controlled accuracy datasets. The survey's recommendation of analyst-retained verification is thus supported by multiple evidence types, although the exact prevalence counts depend on the survey's own inclusion and coding decisions.

## Public implementations

Seven repositories were inspected at pinned revisions in the supplied implementation brief. They represent different artifact classes and should not be ranked as though they were interchangeable agents.

| Candidate | Artifact character | Relevant evaluation surface | Main blocker under this protocol | Provisional eligibility pending reproducibility screening |
|---|---|---|---|---|
| [`ccmdi/osintbench`](https://github.com/ccmdi/osintbench/tree/77b861ca6a13f28efc5c5156c82e8c26a03aba21) | Model benchmark harness | Typed OSINT tasks, verifier, CSV and category metrics, refusal reporting | User must create the dataset; most judging and several tools require external models/network | **Provisional adaptable** |
| [`thunderstornX/agentic-osint-agent`](https://github.com/thunderstornX/agentic-osint-agent/tree/6a9b4f9082c615bddf703629431adccf1d0291a6) | LangGraph passive-recon agent | Evidence ledger, traces, JSON/Markdown reports, tool and agent evaluation scripts | Provider credentials and live WHOIS/DNS/API sources; domain task differs from narrative cases | **Provisional adaptable** |
| [`OpenOSINT/OpenOSINT`](https://github.com/OpenOSINT/OpenOSINT/tree/1ab71de6cdb1e6f5423c46e154b7a838b233aae2) | Broad toolkit, agent, MCP and web service | Dockerfile and extensive mock-oriented tests; reports and graph records | Operational tools remain network dependent even with local Ollama | **Provisional adaptable** |
| [`osianet/osia-framework`](https://github.com/osianet/osia-framework/tree/38a6dab828dafa8df7da008f80bc2979e9ea7448) | Distributed intelligence lifecycle platform | Tests, provenance/reliability tiers, contradiction flags | Many services, credentials, Redis/Qdrant/Signal/ADB assumptions; no license found | **Provisional review-only** |
| [`dazzyddos/OSINT_AI_Agent`](https://github.com/dazzyddos/OSINT_AI_Agent/tree/cab0e5ee1835d787d8cafc26d47a8be9e701b0a3) | Educational recon pipeline | Clear deterministic phases and report state | No fixtures or accuracy benchmark; model, Shodan, and live-target dependence; license text absent | **Provisional review-only** |
| [`Ordinary0x/The-3rd-Eye`](https://github.com/Ordinary0x/The-3rd-Eye/tree/378eb5f7713a964b5e5a26d7d9e95f66dd100346) | Person/social OSINT workflow | Structured report and collected-media output | Browser/platform/Gemini dependence; no tests or evaluation; privacy-sensitive target class | **Provisional review-only** |
| [`foron23/OSINT-OA`](https://github.com/foron23/OSINT-OA/tree/615ebf016991ba85146d8ba7747bb72b561a045e) | Multi-agent web/API/Telegram application | Docker/Compose, SQLite evidence and traces, extensive tests | OpenAI and live tools required for meaningful operation; license text absent | **Provisional adaptable** |

The strongest implementation-level consensus is architectural: explicit evidence stores, traces, structured schemas, bounded tool interfaces, authorization controls, and mockable components are valuable. The repositories do not establish a shared accuracy baseline. Unit-test volume, container presence, README test badges, or committed demonstration outputs must not be interpreted as end-to-end investigative validity. No repository candidate was executed in this review.

Licensing is part of reproducibility and adoption screening. MIT text was found in the pinned snapshots of `ccmdi/osintbench`, `thunderstornX/agentic-osint-agent`, `OpenOSINT/OpenOSINT`, and `The-3rd-Eye`. No license file or package grant was found for `osia-framework`; `OSINT_AI_Agent` and `OSINT-OA` advertised MIT in README material but lacked license text in their inspected snapshots. The latter two should not be treated as permissively licensed until the grant is verified.

## Benchmark/evaluation frameworks

### Directly relevant frameworks

**CyberThreat-Eval** is the strongest adjacent workflow comparator because it derives tasks from professional CTI work and separates triage, deep search, and threat-intelligence drafting. It uses expert annotations and metrics covering factual accuracy, content quality, and operational costs; its authors report high triage recall but weak precision and continuing difficulty with detailed TTP mapping ([paper](https://arxiv.org/abs/2603.09452); [official dataset](https://huggingface.co/datasets/xse/CyberThreat-Eval)). Its staged workflow and analyst-centric scoring inform this protocol, but its CTI task distribution, data, and output contracts differ, so score-to-score comparison is invalid.

**`ccmdi/osintbench`** directly labels tasks as geolocation, identification, temporal, and analysis, supports tool use, and provides model/judge evaluation code ([repository](https://github.com/ccmdi/osintbench)). However, the official README states that users must manually create a dataset, flags most outputs as judge-model evaluated, and lists high-quality human-verified datasets as roadmap work. It is therefore a useful harness and schema reference, not a fixed public corpus comparable to this ten-case benchmark.

The present protocol contributes a different evaluation object: an end-to-end narrative investigation over immutable real-source snapshots, with deterministic entity and relation matching, grounded contradiction scoring, explicit proof-step IDs, and source eligibility restricted to material actually returned during the run. Its design avoids awarding evidence or reasoning credit from prose overlap alone. This makes it unusually aligned with provenance and auditability, though its small case count and unavailable retrieval qrels constrain external validity.

### General agent benchmarks as context

**GAIA** contains 466 real-world questions requiring reasoning, multimodality, browsing, and tool use, with answers withheld for 300 questions ([paper](https://arxiv.org/abs/2311.12983)). Its official Hugging Face repository is gated to limit contamination and requires users not to redistribute the dataset outside a gated/private repository or reshare validation/test data in crawlable form ([dataset access terms](https://huggingface.co/datasets/gaia-benchmark/GAIA)). GAIA is relevant to autonomy and tool-use difficulty, but it is not a direct OSINT investigation comparator, and its gated data cannot simply be vendored into this repository.

**AgentBench** evaluates agents across eight interactive environments and emphasizes long-term reasoning, decision-making, and instruction following ([paper](https://arxiv.org/abs/2308.03688)). **WebArena** supplies reproducible websites and functional task-success checks for long-horizon web interaction ([paper](https://arxiv.org/abs/2307.13854)). **BrowseComp** tests persistent browsing over 1,266 hard-to-find questions with short verifiable answers ([paper](https://arxiv.org/abs/2504.12516); [reference implementation](https://github.com/openai/simple-evals)). These benchmarks inform environment control, persistence, tool traces, and functional scoring. They do not test evidence-backed intelligence reports, entity graphs, contradiction handling, or source-level provenance as a combined workflow and must remain context rather than direct comparators.

## Consensus/disagreements/open questions

**Consensus.** Across the academic systems, workflow studies, survey, and public implementations, tool augmentation is useful for overcoming stale model knowledge and widening collection. Multiple sources also converge on the need for structured evidence, human review, and external validation: Yuan et al. acknowledge dependence on tool quality; OSINT Clinic identifies oversight and privacy problems; CyberThreat-Eval finds nuanced analyst tasks remain difficult; and the 74-study survey recommends human-retained verification.

**Consensus.** Evaluation must separate capabilities. Classification, entity extraction, tool choice, retrieval, reasoning, report generation, traceability, cost, and safety can fail independently. The local baseline demonstrates this directly: perfect source precision/recall coexists with low entity and relation F1, and high mean grounded reasoning coexists with only 0.59 finding F1. A single overall score would hide these differences.

**Disagreement in emphasis.** Architecture papers often describe autonomy, scalability, or improved coverage as primary benefits, while human-centered and analyst-workflow studies emphasize false positives, expert nuance, privacy, monitoring, and verification. This is not a direct factual contradiction because they measure different things, but it is a consequential evaluation mismatch. The present protocol should privilege demonstrated grounded performance over architectural capability claims.

**Disagreement in benchmark design.** OSINTBench uses judge-model evaluation for most outputs and lacks a bundled high-quality corpus, whereas this protocol emphasizes deterministic matching and immutable snapshots. CyberThreat-Eval adds expert and operational metrics but includes stages whose full evaluation may require models, browsing, or inaccessible operational context. No source establishes one method as sufficient; a defensible approach combines deterministic scoring with bounded expert review and reports them separately.

**Open questions.** It remains unclear whether multi-agent routing improves quality after controlling for base model, tool access, token budget, and retries; whether proof-step annotations measure genuine reasoning rather than format compliance; how robust systems are to poisoned or contradictory snapshots; and whether source precision remains high when retrieval is scored rather than fixed. The current literature does not support strong answers.

## Reproducibility and benchmark-fit screening

A candidate should advance beyond provisional status only after the following checks:

1. Pin the exact commit, dependency graph, model identifier, prompts, environment, and license; archive build logs and hashes.
2. Build and test in a network-denied container. Record every attempted outbound connection, not just declared API dependencies.
3. Replace live tools with an adapter over immutable case snapshots. Reject candidates whose useful logic cannot be separated from live targets or third-party accounts.
4. Replace cloud judging and generation with recorded fixtures for deterministic smoke tests, then run a separately reported fixed-model evaluation where credentials are permitted.
5. Map native outputs into the protocol's entities, relations, findings, claims, contradictions, reasoning steps, and source IDs without silently adding facts.
6. Verify authorization, privacy, rate-limit, credential-isolation, and target-interaction controls. A README disclaimer alone is insufficient.
7. Run repeated trials where stochastic inference is retained; report variance, failures, latency, tokens, and cost rather than only the best run.
8. Preserve stdout/stderr, tool traces, final reports, normalized outputs, and scorer versions so an independent reviewer can replay the score.

Under this screen, `ccmdi/osintbench`, `agentic-osint-agent`, OpenOSINT, and OSINT-OA appear **provisionally adaptable**, while OSIA, OSINT_AI_Agent, and The-3rd-Eye appear **provisionally review-only**. These are source-inspection judgments, not execution results. None is presently established as runnable under the strict offline, containerized, credential-free, no-live-target profile.

Data access also limits reproduction. GAIA is gated and restricts redistribution. CyberThreat-Eval makes benchmark material available, but some evaluation paths require browser/runtime dependencies or model APIs. `ccmdi/osintbench` supplies a harness but requires users to create the dataset. This repository preserves its own source snapshots, but the aggregate baseline contains no retrieval annotations or qrels; consequently, retrieval precision, recall, ranking quality, and missed-source attribution are not reproducible from the aggregate file.

## Implications for this ten-case protocol

The baseline should be interpreted as a pipeline diagnosis, not a leaderboard. The exact means show the main weakness is structured recovery: relation F1 is 0.1204939504939505 and entity F1 is 0.3587260914341864, far below grounded reasoning (0.8372319688109162), report quality (0.825), and source precision/recall (1.0/1.0). Finding F1 (0.59) and grounded contradiction F1 (0.5888888888888889) are intermediate. Two outputs were structurally invalid despite all ten being structurally complete, which indicates that presence of all required sections does not ensure valid references.

The perfect source scores should not be interpreted as perfect retrieval or factuality. They show that parsed citations met the benchmark's source-eligibility and coverage rules for the generated claims/findings. Since every case has retrieval status `not_annotated`, there is no qrel-based evidence that the agent found all relevant sources, ranked them well, or avoided irrelevant retrieval. Likewise, deterministic report-quality checks are not a substitute for expert assessment of writing or real-world actionability.

The next evaluation should therefore prioritize output normalization and relation extraction before adding more agent roles. It should also separate four experimental layers: deterministic recorded-fixture regression; fixed-model offline snapshot runs; optional candidate-adapter comparisons; and human review of a stratified sample. General benchmarks should inform stress-test design, not supply headline comparative scores.

Ablations should preserve identical model, prompt budget, snapshots, and scorer version. The protocol's full, single-agent, no-reasoning, no-consistency-validation, and no-evidence-trace conditions are useful, but claims about architectural benefit require repeated trials and confidence intervals. “No reasoning” also needs an operational definition that does not depend on exposing private chain-of-thought; observable planning actions, tool sequences, and explicit proof-step outputs are safer evaluation objects.

## Recommended next research decisions

1. **Create retrieval qrels before comparing agents.** Annotate relevant, supporting, contradictory, and distractor source IDs per investigative question. Keep qrels separate from agent-visible fixtures.
2. **Run a reproducibility gate before a performance bake-off.** Start with the four provisionally adaptable candidates and require a network-denied build, fixture replay, license verification, and output-contract mapping. Do not call any candidate runnable until this passes.
3. **Prioritize one narrow adapter.** `thunderstornX/agentic-osint-agent` offers explicit evidence and trace mechanics; OpenOSINT offers the strongest container/test surface; `ccmdi/osintbench` offers evaluator ideas. Select one only after estimating adapter effort against the narrative-case schema.
4. **Add adversarial snapshot cases.** Include source poisoning, copied claims, temporal inconsistency, conflicting authoritative sources, and prompt injection in retrieved text. Score both detection and unsafe propagation.
5. **Add uncertainty and abstention metrics.** Measure unsupported-claim rate, calibrated abstention, contradiction reconciliation, and confidence/error association alongside existing F1 metrics.
6. **Specify expert review separately.** Use a blinded rubric for evidential sufficiency, uncertainty communication, privacy, and actionability; do not blend subjective review into deterministic scores.
7. **Increase case diversity only after scorer reliability is measured.** Double-score annotations, report inter-annotator agreement, and freeze a benchmark version before expanding beyond ten cases.

## References

- Chen, X. et al. “CyberThreat-Eval: Can Large Language Models Automate Real-World Threat Research?” TMLR / arXiv:2603.09452. [Paper](https://arxiv.org/abs/2603.09452). [Dataset](https://huggingface.co/datasets/xse/CyberThreat-Eval).
- Liu, X. et al. “AgentBench: Evaluating LLMs as Agents.” ICLR 2024 / arXiv:2308.03688. [Paper](https://arxiv.org/abs/2308.03688).
- Mialon, G. et al. “GAIA: a benchmark for General AI Assistants.” arXiv:2311.12983. [Paper](https://arxiv.org/abs/2311.12983). [Gated dataset](https://huggingface.co/datasets/gaia-benchmark/GAIA).
- Mukhopadhyay, A., and Luther, K. “OSINT Clinic: Co-Designing AI-Augmented Collaborative OSINT Investigations for Vulnerability Assessment.” CHI 2025. [DOI](https://doi.org/10.1145/3706598.3713283).
- Palmieri, E. A., Ghanem, M. C., Sowinski-Mydlarz, V., and Dunsin, D. “A Framework for Embedding Generative and Agentic AI in Open Source Intelligence.” TechRxiv v1/v2 and IEEE BCCA 2025. [TechRxiv v1](https://doi.org/10.36227/techrxiv.175623135.54287545/v1). [TechRxiv v2](https://doi.org/10.36227/techrxiv.175623135.54287545/v2). [IEEE DOI](https://doi.org/10.1109/BCCA66705.2025.11229637). [Institutional record](https://repository.londonmet.ac.uk/10859/).
- Palmieri, E. A. et al. “Agentic and Generative AI for Open-Source Intelligence and Cyber Investigations: Taxonomy, Evaluation, Challenges, and Future Directions.” arXiv:2607.03233v1. [Paper](https://arxiv.org/abs/2607.03233v1).
- Shafee, S., Bessani, A., and Ferreira, P. M. “Evaluation of LLM Chatbots for OSINT-based Cyber Threat Awareness.” Expert Systems with Applications 261 (2025). [DOI](https://doi.org/10.1016/j.eswa.2024.125509). [arXiv](https://arxiv.org/abs/2401.15127).
- Wei, J. et al. “BrowseComp: A Simple Yet Challenging Benchmark for Browsing Agents.” arXiv:2504.12516. [Paper](https://arxiv.org/abs/2504.12516). [Reference code](https://github.com/openai/simple-evals).
- Yuan, X., Wang, J., Zhao, H., Yan, T., and Qi, F. “Empowering LLMs with Toolkits: An Open-Source Intelligence Acquisition Method.” Future Internet 16(12), 461 (2024). [DOI](https://doi.org/10.3390/fi16120461).
- Zhou, S. et al. “WebArena: A Realistic Web Environment for Building Autonomous Agents.” arXiv:2307.13854. [Paper](https://arxiv.org/abs/2307.13854). [Project](https://webarena.dev/).
- `ccmdi/osintbench`. [Pinned source](https://github.com/ccmdi/osintbench/tree/77b861ca6a13f28efc5c5156c82e8c26a03aba21).
- `thunderstornX/agentic-osint-agent`. [Pinned source](https://github.com/thunderstornX/agentic-osint-agent/tree/6a9b4f9082c615bddf703629431adccf1d0291a6).
- `OpenOSINT/OpenOSINT`. [Pinned source](https://github.com/OpenOSINT/OpenOSINT/tree/1ab71de6cdb1e6f5423c46e154b7a838b233aae2).
- `osianet/osia-framework`. [Pinned source](https://github.com/osianet/osia-framework/tree/38a6dab828dafa8df7da008f80bc2979e9ea7448).
- `dazzyddos/OSINT_AI_Agent`. [Pinned source](https://github.com/dazzyddos/OSINT_AI_Agent/tree/cab0e5ee1835d787d8cafc26d47a8be9e701b0a3).
- `Ordinary0x/The-3rd-Eye`. [Pinned source](https://github.com/Ordinary0x/The-3rd-Eye/tree/378eb5f7713a964b5e5a26d7d9e95f66dd100346).
- `foron23/OSINT-OA`. [Pinned source](https://github.com/foron23/OSINT-OA/tree/615ebf016991ba85146d8ba7747bb72b561a045e).

## Coverage limitations

The requested academic-paper research brief, `outputs/osint-agent-evaluation-research-papers.md`, was unavailable at the specified workspace path. This draft therefore reconstructs that track from primary publisher, arXiv, institutional, dataset, and repository sources; it does not claim to reproduce any unavailable brief's full candidate list or judgments. The public-implementation brief, local protocol, benchmark README, plan, and aggregate baseline were available.

No candidate implementation, test suite, container, model, or benchmark was executed. Repository findings derive from the supplied pinned-source inspection and primary repository content, so all run eligibility remains provisional pending reproducibility screening. GitHub metadata rate limits prevented using repository API statistics as evidence; popularity was not used as a quality proxy.

The TechRxiv DOI landing pages were not directly fetchable in this environment, so lineage was triangulated from their stable DOI records, the institutional repository, the IEEE DOI record, and matching bibliographic/abstract information. Automated source checking did not independently resolve every version-linkage field; the evidence supports treating the records as versions of one work, but exact textual changes between v1, v2, and the camera-ready paper were not diffed.

The 74-study survey is an arXiv v1 preprint, not an independently replicated meta-analysis. Its field-wide counts and “hallucination-validation gap” framing should be treated as secondary evidence. Earlier repository/search-index title/status metadata was not sufficiently stable to establish a separate publication identity; this review uses the canonical arXiv title and status.

GAIA validation/test content is gated and redistribution restricted. Other benchmarks may require APIs, browsers, live web state, proprietary operational context, or judge models. The local aggregate has no retrieval qrels (`not_annotated` for all ten cases), so retrieval metrics and missed-evidence analysis are unavailable. The ten-case sample is too small for broad claims about all OSINT domains, languages, modalities, or threat models.
