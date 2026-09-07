# OSINT-Bench Dataset Construction Guidelines

This guide establishes the standard for contributing, designing, and maintaining cases for the OSINT-Bench dataset. It ensures that all cases remain reproducible, legally/ethically compliant, and logically rigorous.

---

## 1. Core Principles

To be accepted into the benchmark, every case must satisfy the following criteria:

1. **Public-source provenance**: Every source must be a real, publicly accessible source (official record, publisher page, public archive, or official export). Synthetic URLs, mock pages, LLM-generated text, and LLM-generated structured facts are prohibited. The case stores an immutable snapshot so evaluation does not depend on the live web.
2. **Reproducibility**: Every source snapshot must include its canonical HTTPS URL, publisher, publication date, retrieval timestamp, retrieval method, payload SHA-256, and human verification notes. A failed refresh must never replace an existing snapshot with generated text. Do *not* rely on live internet resources during evaluation.
3. **Evidence versus annotation**: `raw_text` is the verbatim or faithfully extracted source payload. `content.evidence_summary`, labels, findings, and ground truth are annotations made by a human reviewer; they are not evidence and must not be generated from unsupported model guesses.
4. **Reasoning-Heavy**: Avoid simple lookup tasks. A case should require the agent to combine pieces of information from at least three different sources to reach the final attribution or conclusion.
5. **Strict Privacy & Ethics**: Under no circumstances should real-world, non-public, or sensitive PII (Personally Identifiable Information) be included. Real-world targets must be limited to publicly documented, sanitized records. Fictionalized cases are not part of the real-source benchmark and must be placed in a separate clearly labelled synthetic dataset.
6. **Logical Consistency Testing**: Each Medium and Hard case must contain at least one contradiction between real source claims or an explicitly documented uncertainty. Do not invent a deceptive clue merely to satisfy this requirement.

---

## 2. Difficulty Tier Definitions

| Difficulty | Hops Required | Sources Count | Contradictions | Key Features |
| :--- | :---: | :---: | :---: | :--- |
| **Easy** | 1–2 hops | 2–4 | 0 | Single direct pivot (e.g., matching a registrant email from WHOIS to a public LinkedIn profile page). |
| **Medium** | 3–4 hops | 5–8 | 1 | Multi-hop attribution (e.g., transaction flow tracking that links a wallet to a forum handle, which contradicts a published alibi blog post). |
| **Hard** | 5+ hops | 8+ | 2+ | Multiple pivots requiring key matching (SSH/PGP signatures), timing alignment, cross-platform linking, and resolving adversarial/deceptive records. |

---

## 3. Injecting Contradictions & Evasion Tactics

Contradictions are essential to evaluate the agent's "Logical Consistency Validation" module. When designing cases, inject contradictions using these methods:

- **Temporal Contradictions**: A blog post claims the owner sold the domain in 2024, but WHOIS history or SSL logs show the same cryptographic key was used to sign certificates in 2025.
- **Identity Confusions**: A social media profile lists a developer's city as "London," but their public commits and transaction signatures align exclusively with timezone UTC+8 (e.g., Singapore/Beijing).
- **Alibi Deceptions**: A target posts a public statement claiming they were hacked during a specific window, but blockchain activity shows their private keys signed transactions concurrently with their active forum comments.

Each contradiction must be documented in the `ground_truth.contradictions` array with a clear `reconciliation` explaining how the analyst resolves the paradox.

---

## 4. Benchmark Size Recommendation

For a research paper submission, we recommend the following target dataset sizes and distributions to ensure statistical significance:

### Recommended Benchmark Size: **120 Cases**

### Distribution by Category
- **Threat Actor & Infrastructure Attribution**: 35 cases (30%)
- **Cryptocurrency & Asset Tracing**: 35 cases (30%)
- **Shell Company & Corporate Fraud**: 25 cases (20%)
- **Social Media & Sockpuppet Networks**: 25 cases (20%)

### Distribution by Difficulty
- **Easy**: 40 cases (approx. 33%)
- **Medium**: 50 cases (approx. 42%)
- **Hard**: 30 cases (approx. 25%)

---

## 5. Structuring Public Sources

Sources in the JSON file must mimic their real-world counterparts. Make sure to provide both structured content and raw text:

```json
{
  "source_id": "SRC-101",
  "type": "WHOIS",
  "uri": "https://whois.mocknic.net/domain/malicious-target.com",
  "content": {
    "domain_name": "malicious-target.com",
    "registrar": "NameCheap",
    "creation_date": "2025-03-12",
    "registrant_email": "shadowops@protonmail.com"
  },
  "raw_text": "Domain Name: malicious-target.com\nRegistry Domain ID: 29837492_DOMAIN_COM-VRSN\nRegistrar: NameCheap, Inc.\nCreation Date: 2025-03-12T08:00:00Z\nRegistrant Email: shadowops@protonmail.com"
}
```

This ensures that:
- Simple entity extraction models can parse the `raw_text`.
- Advanced modules can directly query the structured `content` to simulate API calls.
- Evaluations are fully deterministic.
