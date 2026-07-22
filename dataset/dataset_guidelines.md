# OSINT-Bench Dataset Construction Guidelines

This guide establishes the standard for contributing, designing, and maintaining cases for the OSINT-Bench dataset. It ensures that all cases remain reproducible, legally/ethically compliant, and logically rigorous.

---

## 1. Core Principles

To be accepted into the benchmark, every case must satisfy the following criteria:

1. **Reproducibility**: All public sources used by a case must be fully snapshotted or mock-represented within the `sources` array of the JSON file. Do *not* rely on live internet resources, which are prone to link rot, API changes, or content modifications.
2. **Reasoning-Heavy**: Avoid simple lookup tasks. A case should require the agent to combine pieces of information from at least three different sources to reach the final attribution or conclusion.
3. **Strict Privacy & Ethics**: Under no circumstances should real-world, non-public, or sensitive PII (Personally Identifiable Information) be included. Any real-world targets (e.g., active threat groups) must be analyzed using publicly documented, sanitized reports, or completely fictionalized (using mock data).
4. **Logical Consistency Testing**: Each Medium and Hard case must contain at least one intentional logical contradiction or deceptive clue that testing systems must resolve.

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
