# OSINT-Bench Evaluation Protocol

This document defines the formal evaluation protocol for systems tested against the OSINT-Bench dataset. It specifies metric formulations for both module-level and workflow-level tasks, and provides instructions for running ablation studies.

---

## 1. Evaluation Architecture

OSINT-Bench supports evaluation at two distinct levels:
1. **Module-Level Evaluation**: Isolates specific components (e.g., entity extractors, relationship matchers, logic checkers) to test their individual performance.
2. **Workflow-Level Evaluation**: Evaluates the complete agent or multi-agent system from initial target input to the final generated investigation report.

---

## 2. Module-Level Metrics

### A. Entity Extraction
Measures the system's ability to extract specific types of entities from the simulated web sources.

- Let $E_{GT}$ be the set of ground truth entities defined in the case.
- Let $E_{SYS}$ be the set of entities extracted by the system.
- An entity match is successful if the extracted entity matches both the ground truth `value` (case-insensitive) and the `type` classification.

$$\text{Precision}_{Ent} = \frac{|E_{SYS} \cap E_{GT}|}{|E_{SYS}|}$$
$$\text{Recall}_{Ent} = \frac{|E_{SYS} \cap E_{GT}|}{|E_{GT}|}$$
$$F_1\text{-Score}_{Ent} = 2 \times \frac{\text{Precision}_{Ent} \times \text{Recall}_{Ent}}{\text{Precision}_{Ent} + \text{Recall}_{Ent}}$$

---

### B. Relation Discovery & Entity Linking
Measures the system's ability to identify relationships between extracted entities and resolve co-references (linking alias profiles back to real-world entities).

- Let $R_{GT}$ be the set of ground truth relations: tuples of `(source_id, relationship_type, target_id)`.
- Let $R_{SYS}$ be the set of relations output by the system.
- A relation match is successful if both the source and target entity IDs match, and the relationship type aligns semantically (mapped via a semantic dictionary or LLM evaluator).

$$\text{Precision}_{Rel} = \frac{|R_{SYS} \cap R_{GT}|}{|R_{SYS}|}$$
$$\text{Recall}_{Rel} = \frac{|R_{SYS} \cap R_{GT}|}{|R_{GT}|}$$
$$F_1\text{-Score}_{Rel} = 2 \times \frac{\text{Precision}_{Rel} \times \text{Recall}_{Rel}}{\text{Precision}_{Rel} + \text{Recall}_{Rel}}$$

---

### C. Contradiction Detection
Measures the system's ability to detect conflicting claims or data points across sources (e.g., WHOIS domain age vs. website archives).

- **True Positives (TP)**: System correctly flags a ground-truth contradiction and identifies the correct conflicting source IDs.
- **False Positives (FP)**: System flags a contradiction that does not exist in the ground truth.
- **False Negatives (FN)**: System fails to flag a ground-truth contradiction.

$$\text{Precision}_{Contra} = \frac{TP}{TP + FP}$$
$$\text{Recall}_{Contra} = \frac{TP}{TP + FN}$$
$$F_1\text{-Score}_{Contra} = 2 \times \frac{\text{Precision}_{Contra} \times \text{Recall}_{Contra}}{\text{Precision}_{Contra} + \text{Recall}_{Contra}}$$

---

## 3. Workflow-Level (End-to-End) Metrics

These metrics evaluate the final output report and trace logs of the agent.

### A. Investigation Completion (Key Findings Accuracy)
Determines if the agent answered the core investigative questions correctly.

- For each question in `key_findings`:
  - **Correct (Score 1.0)**: The answer matches the ground truth answer (verified by exact string match or LLM semantic similarity) and cites at least one of the expected supporting entities.
  - **Partially Correct (Score 0.5)**: The answer is correct but fails to link or cite the correct supporting entities.
  - **Incorrect (Score 0.0)**: The answer is wrong or missing.

$$\text{Investigation Completion (IC)} = \frac{\sum \text{Score of Findings}}{|Key Findings|}$$

---

### B. Source Traceability
Verifies that the agent's findings are verifiable and not hallucinated.

- For each finding reported by the agent, we count the number of claims that contain direct links or citations to the source URIs.
- A claim is "Traceable" if the cited source ID matches the ground-truth `source_references` for that entity/relation.

$$\text{Source Traceability (ST)} = \frac{\text{Number of Correctly Traced Claims}}{\text{Total Number of Claims in Report}}$$

---

### C. Reasoning Chain Coverage
Measures how much of the ground-truth proof chain the agent traversed. This is verified by analyzing the agent's reasoning logs against the step-by-step logic defined in the case.

- Let $P_{GT}$ be the set of reasoning steps in `reasoning_proof_chains`.
- A step is counted as "covered" if the agent's logs contain the conclusion and the supporting evidence/premises for that step.

$$\text{Reasoning Coverage (RC)} = \frac{\text{Number of Traversed Steps}}{|P_{GT}|}$$

---

### D. Qualitative Report Quality
Evaluates the professionalism and clarity of the generated markdown report. Rated on a scale of 1-5 (or normalized to 0-1) using a standardized rubric:
1. **Structure (0.2)**: Follows a professional intelligence report format (Executive Summary, Findings, Evidence Map).
2. **Clarity (0.2)**: Clear, objective language with no stylistic fluff.
3. **Actionability (0.2)**: Provides clear intelligence or next steps.
4. **OpSec awareness (0.2)**: Identifies risks associated with target interaction.
5. **Formatting (0.2)**: Correct use of tables, code blocks, and markdown structure.

---

## 4. Ablation Study Framework

To understand which cognitive architectures contribute to OSINT performance, evaluators should run the benchmark under the following five configurations:

| Configuration | Enabled Modules | Expected Impact | Ablation Target |
| :--- | :--- | :--- | :--- |
| **Full System** | Multi-agent coordination, reasoning loops, contradiction checkers, and citation tracers. | Baseline (highest expected performance across all metrics). | N/A |
| **Single-Agent** | Disable multi-agent routing. Run a single LLM loop with all tools. | Tests the impact of division-of-labor and collaborative reviews. | Multi-agent collaboration. |
| **No Reasoning** | Disable chain-of-thought and multi-hop hypothesis generation. Force direct, greedy tool actions. | Expected to lower IC and RC scores on Hard/Medium cases. | Reasoner module. |
| **No Consistency Validation** | Disable contradiction detection scripts and validation agents. | Expected to drop Contradiction F1 to 0; reports might contain conflicting claims. | Validation module. |
| **No Evidence Trace** | Disable the tracking of source citations and strict reference logs. | Lowers ST score to near-zero. Tests LLM baseline hallucination rate. | Traceability module. |

### Conducting an Ablation Run
1. Run the test harness for each case using the specified configuration.
2. Log the output graph, final report, and run history.
3. Compute the metrics and plot performance drops to quantify the ablation delta. For example, a significant drop in **Investigation Completion** between *Full System* and *No Reasoning* demonstrates the system's reliance on multi-hop logical inferences.
