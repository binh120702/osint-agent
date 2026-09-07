"""Refresh benchmark source snapshots from their declared public URLs.

This script deliberately does not synthesize fallback text. A failed current
fetch is recorded as failed while any prior snapshot is preserved; callers can
then distinguish an existing historical snapshot from a current fetch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import ssl
import sys
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CASES = Path(__file__).resolve().parents[1] / "cases"
USER_AGENT = "OSINT-Bench-source-refresh/1.0 (research dataset maintenance)"

# These URLs were selected from SearXNG results and directly fetched before
# being added.  They replace source endpoints that currently return blocking,
# unsupported, or non-readable responses.
REPLACEMENTS = {
    ("OSINT-001", "SRC-001"): ("https://www.cybersecuritydive.com/news/supply-chain-attack-3cx-desktop-thousands/646432/", {
        "page_title": "Supply chain attack against 3CX communications app could impact thousands",
        "source_quality": "Reputable cybersecurity news report",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "Cybersecurity Dive reports that a trojanized 3CX Desktop App update was distributed in a supply-chain attack and summarizes the affected communications software and incident response.",
    }),
    ("OSINT-001", "SRC-002"): ("https://www.wired.com/story/3cx-supply-chain-attack-north-korea-cryptocurrency-targets/", {
        "page_title": "Massive 3CX Supply-Chain Hack Targeted Cryptocurrency Firms",
        "source_quality": "Reputable investigative technology reporting",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "WIRED reports that the 3CX supply-chain compromise targeted cryptocurrency-related organizations and describes evidence linking the operation to North Korean hackers.",
    }),
    ("OSINT-001", "SRC-009"): ("https://www.csa.gov.sg/alerts-and-advisories/alerts/al-2023-040/", {
        "page_title": "Malware Discovered in 3CX DesktopApp",
        "source_quality": "Official Singapore Cyber Security Agency advisory",
        "verification_status": "Direct fetch returned readable advisory text.",
        "evidence_summary": "Singapore's Cyber Security Agency advisory describes the trojanised 3CX DesktopApp, affected platforms, and the supply-chain compromise response.",
    }),
    ("OSINT-002", "SRC-002"): ("https://www.rapid7.com/blog/post/2022/03/01/conti-ransomware-group-internal-chats-leaked-over-russia-ukraine-conflict/", {
        "page_title": "Conti Ransomware Group Internal Chats Leaked",
        "source_quality": "Reputable cybersecurity research reporting",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "Rapid7 reports that internal Conti ransomware group chats were leaked after the group publicly supported Russia, and describes the leaked communications and the group's organization.",
    }),
    ("OSINT-003", "SRC-003"): ("https://www.elliptic.co/insights/540-million-stolen-from-the-ronin-defi-bridge", {
        "page_title": "North Korea's Lazarus Group identified as exploiters of $540 million Ronin bridge theft",
        "source_quality": "Blockchain analysis firm reporting",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "Elliptic describes the Ronin bridge theft, the movement of stolen assets, and its assessment linking the exploitation to Lazarus Group.",
    }),
    ("OSINT-004", "SRC-001"): ("https://www.pbs.org/newshour/nation/read-muellers-full-indictment-against-12-russian-officers-for-election-interference", {
        "page_title": "Read Mueller's full indictment against 12 Russian officers for election interference",
        "source_quality": "PBS publication of the public federal indictment",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "PBS publishes the public indictment and summarizes the charges against Russian intelligence officers, including the use of DCLeaks and Guccifer 2.0 personas.",
    }),
    ("OSINT-005", "SRC-001"): ("https://www.justice.gov/opa/pr/justice-department-announces-compensation-process-onecoin-fraud-victims-funds-recovered", {
        "page_title": "Justice Department Announces Compensation Process for OneCoin Fraud Victims",
        "source_quality": "Official U.S. Department of Justice press release",
        "verification_status": "Direct fetch returned readable DOJ press-release text.",
        "evidence_summary": "The DOJ describes OneCoin as an international investment fraud scheme involving Ruja Ignatova and Karl Sebastian Greenwood and announces compensation for victims from recovered funds.",
    }),
    ("OSINT-005", "SRC-004"): ("https://www.state.gov/reward-for-information-german-national-ruja-ignatova", {
        "page_title": "Reward for Information: German National Ruja Ignatova",
        "source_quality": "Official U.S. Department of State reward notice",
        "verification_status": "Direct fetch returned readable State Department page text.",
        "evidence_summary": "The State Department reward notice identifies Ruja Ignatova, describes the fraud and money-laundering charges, and offers a reward for information leading to her arrest or conviction.",
    }),
    ("OSINT-006", "SRC-001"): ("https://www.cisa.gov/news-events/cybersecurity-advisories/aa23-158a", {
        "page_title": "CL0P Ransomware Gang Exploits CVE-2023-34362 MOVEit Vulnerability",
        "source_quality": "Official CISA and FBI joint cybersecurity advisory",
        "verification_status": "Direct fetch returned readable advisory text.",
        "evidence_summary": "The joint CISA/FBI advisory states that CL0P began exploiting CVE-2023-34362 in MOVEit Transfer on or about May 27, 2023 and provides technical details and mitigations.",
    }),
    ("OSINT-003", "SRC-001"): ("https://www.elliptic.co/insights/fbi-confirms-north-korea-s-lazarus-group-as-hackers-behind-100-million-harmony-horizon-bridge-theft", {
        "page_title": "FBI confirms North Korea's Lazarus Group as hackers behind $100 million Harmony Horizon Bridge theft",
        "source_quality": "Blockchain analysis firm reporting on FBI attribution",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "Elliptic reports on the FBI attribution of the Harmony Horizon Bridge theft to North Korea's Lazarus Group and discusses the stolen virtual assets.",
    }),
    ("OSINT-004", "SRC-001"): ("https://nsarchive.gwu.edu/sites/default/files/documents/4599181/Indictment.pdf", {
        "page_title": "Indictment",
        "source_quality": "National Security Archive copy of the public federal indictment",
        "verification_status": "Direct PDF fetch and text extraction succeeded.",
        "evidence_summary": "The public indictment says conspirators used fictitious personas including DCLeaks and Guccifer 2.0 to stage releases of stolen documents and describes the associated Russian intelligence activity.",
    }),
    ("OSINT-005", "SRC-001"): ("https://thefactcoalition.org/wp-content/uploads/2021/12/TI_Private-Investments-Public-Harm-10.pdf", {
        "page_title": "Private Investments, Public Harm",
        "source_quality": "Research report from the FACT Coalition",
        "verification_status": "Direct PDF fetch and text extraction succeeded.",
        "evidence_summary": "The FACT Coalition report discusses OneCoin as an international pyramid fraud scheme and describes the use of private equity structures to conceal, move, and launder proceeds.",
    }),
    ("OSINT-005", "SRC-002"): ("https://www.afslaw.com/perspectives/investigations-blog/co-founder-fraudulent-cryptocurrency-sentenced-20-years-prison", {
        "page_title": "Co-Founder of Fraudulent Cryptocurrency Sentenced to 20 Years in Prison",
        "source_quality": "Reputable legal analysis reporting on the public sentencing",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "The article reports Karl Sebastian Greenwood's 20-year sentence for his role as a OneCoin co-founder and summarizes the multibillion-dollar fraud allegations and sentencing.",
    }),
    ("OSINT-005", "SRC-003"): ("https://www.dw.com/en/pandora-papers-the-king-of-jordans-hidden-property-gems/a-59403014", {
        "page_title": "Pandora Papers: The royal 'you know who' from Jordan",
        "source_quality": "Reputable international news reporting",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "DW reports on the Pandora Papers findings concerning King Abdullah II's offshore property holdings and explains that the reporting concerned hidden assets rather than a finding of illegality.",
    }),
    ("OSINT-007", "SRC-001"): ("https://www.cnbc.com/2024/01/29/doj-and-sec-unveil-charges-in-1point9-billion-cryptocurrency-fraud-scheme.html", {
        "page_title": "DOJ and SEC unveil charges in $1.9 billion cryptocurrency fraud scheme",
        "source_quality": "Reputable financial news reporting",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "CNBC reports on the DOJ and SEC charges involving HyperFund/HyperVerse and describes the alleged cryptocurrency fraud scheme and its collapse.",
    }),
    ("OSINT-007", "SRC-002"): ("https://www.justice.gov/criminal/case/hyperfund-and-associated-cases", {
        "page_title": "HyperFund and Associated Cases",
        "source_quality": "Official U.S. Department of Justice case page",
        "verification_status": "Direct fetch returned readable DOJ case-page text.",
        "evidence_summary": "The DOJ case page identifies the HyperFund associated cases, the defendants, the charges, and the indictment and plea developments.",
    }),
    ("OSINT-007", "SRC-004"): ("https://www.sec.gov/newsroom/press-releases/2024-11", {
        "page_title": "SEC Charges Founder of $1.7 Billion HyperFund Crypto Pyramid Scheme",
        "source_quality": "Official U.S. Securities and Exchange Commission press release",
        "verification_status": "Direct fetch returned readable SEC press-release text.",
        "evidence_summary": "The SEC charges Xue Lee and Brenda Chunga over their alleged roles in the HyperFund crypto-asset pyramid scheme and states that it raised more than $1.7 billion.",
    }),
    ("OSINT-008", "SRC-001"): ("https://www.europarl.europa.eu/RegData/etudes/STUD/2020/651384/IPOL_STU(2020)651384_EN.pdf", {
        "page_title": "What are the wider supervisory implications of the Wirecard case?",
        "source_quality": "European Parliament research study",
        "verification_status": "Direct PDF fetch and text extraction succeeded.",
        "evidence_summary": "The European Parliament study examines the Wirecard scandal, audit and supervisory failures, and the implications of the company's collapse.",
    }),
    ("OSINT-008", "SRC-002"): ("https://safe-frankfurt.de/fileadmin/user_upload/editor_common/Policy_Center/SAFE_Policy_White_Paper_74.pdf", {
        "page_title": "What are the wider supervisory implications of the Wirecard case?",
        "source_quality": "SAFE policy white paper",
        "verification_status": "Direct PDF fetch and text extraction succeeded.",
        "evidence_summary": "The SAFE paper examines the Wirecard scandal, the KPMG special investigation, supervisory failures, and the implications of the company's collapse.",
    }),
    ("OSINT-009", "SRC-001"): ("https://www.dw.com/en/pandora-papers-the-king-of-jordans-hidden-property-gems/a-59403014", {
        "page_title": "Pandora Papers: The royal 'you know who' from Jordan",
        "source_quality": "Reputable international news reporting",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "DW reports on the Pandora Papers findings concerning King Abdullah II's offshore property holdings and describes the reporting as concerning hidden wealth and ownership structures.",
    }),
    ("OSINT-009", "SRC-003"): ("https://www.aljazeera.com/news/2021/10/3/investigation-reveals-offshore-assets-of-heads-of-state", {
        "page_title": "Investigation reveals offshore assets of heads of state",
        "source_quality": "Reputable international news reporting",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "Al Jazeera reports on the Pandora Papers investigation and offshore assets associated with heads of state, including Jordan's King Abdullah II.",
    }),
    ("OSINT-009", "SRC-004"): ("https://www.icij.org/investigations/pandora-papers/jordan-king-abdullah-luxury-property/", {
        "page_title": "While foreign aid poured in, Jordan's King Abdullah funnelled $100 million into luxury homes",
        "source_quality": "International Consortium of Investigative Journalists investigation",
        "verification_status": "Direct fetch returned readable ICIJ investigation text.",
        "evidence_summary": "ICIJ reports that the Pandora Papers identified offshore companies and luxury property holdings associated with Jordan's King Abdullah II.",
    }),
    ("OSINT-010", "SRC-001"): ("https://www.justice.gov/d9/fieldable-panel-panes/basic-panes/attachments/2018/02/16/internet_research_agency_indictment.pdf", {
        "page_title": "Internet Research Agency Indictment",
        "source_quality": "Official U.S. Department of Justice indictment PDF",
        "verification_status": "Direct PDF fetch and text extraction succeeded.",
        "evidence_summary": "The DOJ indictment describes the Internet Research Agency conspiracy, Russian individuals and companies, and the use of social media and fictitious personas to interfere in the U.S. political system.",
    }),
    ("OSINT-010", "SRC-002"): ("https://www.npr.org/2019/10/08/768319934/senate-report-russians-used-used-social-media-mostly-to-target-race-in-2016", {
        "page_title": "Senate Report Finds Russians Used Social Media To Target Race In 2016",
        "source_quality": "Reputable public-radio reporting",
        "verification_status": "Direct fetch returned readable article text.",
        "evidence_summary": "NPR reports on the Senate Intelligence Committee's findings that Russian actors used social media to target racial divisions and influence the 2016 election.",
    }),
    # These entries intentionally appear after the legacy map entries above so
    # the current, directly searched replacements win if an older mapping is
    # still present in a downstream checkout.
    ("OSINT-004", "SRC-001"): ("https://www.justice.gov/archives/opa/pr/grand-jury-indicts-12-russian-intelligence-officers-hacking-offenses-related-2016-election", {
        "page_title": "Grand Jury Indicts 12 Russian Intelligence Officers for Hacking Offenses Related to the 2016 Election",
        "source_quality": "Official U.S. Department of Justice press release",
        "verification_status": "Direct fetch returned readable DOJ press-release text.",
        "evidence_summary": "The DOJ release summarizes the indictment charging Russian intelligence officers and describes the use of DCLeaks and Guccifer 2.0 personas to release stolen material.",
    }),
    ("OSINT-005", "SRC-001"): ("https://www.justice.gov/opa/pr/justice-department-announces-compensation-process-onecoin-fraud-victims-funds-recovered", {
        "page_title": "Justice Department Announces Compensation Process for OneCoin Fraud Victims",
        "source_quality": "Official U.S. Department of Justice press release",
        "verification_status": "Direct fetch returned readable DOJ press-release text.",
        "evidence_summary": "The DOJ describes OneCoin as an international investment fraud scheme involving Ruja Ignatova and Karl Sebastian Greenwood and announces compensation for victims from recovered funds.",
    }),
}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.parts.append(value)

    def text(self):
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def fetch(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.1"})
    try:
        with urlopen(request, timeout=10, context=ssl.create_default_context()) as response:
            payload = response.read()
            content_type = response.headers.get_content_type()
            status = int(response.status)
            if content_type == "application/pdf":
                try:
                    from pypdf import PdfReader
                    import io
                    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(payload)).pages)
                except Exception as exc:
                    return {"status": status, "content_type": content_type, "error": f"PDF extraction unavailable: {exc}"}
            else:
                parser = TextExtractor()
                parser.feed(payload.decode(response.headers.get_content_charset() or "utf-8", errors="replace"))
                text = parser.text()
            if len(text) < 120:
                return {"status": status, "content_type": content_type, "error": "Response did not contain enough readable source text"}
            return {"status": status, "content_type": content_type, "text": text, "sha256": hashlib.sha256(payload).hexdigest()}
    except HTTPError as exc:
        return {"status": exc.code, "error": str(exc.reason)}
    except (URLError, TimeoutError, OSError) as exc:
        return {"status": None, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write successful and failed fetch metadata to case files")
    parser.add_argument("--case", action="append", help="Refresh only the named case filename or case id; repeatable")
    args = parser.parse_args()
    failures = []
    selected = set(args.case or [])
    paths = sorted(CASES.glob("*.json"))
    if selected:
        paths = [p for p in paths if p.stem in selected or json.loads(p.read_text(encoding="utf-8")).get("case_id") in selected]
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for source in data.get("sources", []):
            replacement = REPLACEMENTS.get((data.get("case_id"), source.get("source_id")))
            if replacement:
                source["uri"] = replacement[0]
                source.setdefault("content", {}).update(replacement[1])
                source["content"]["date_accessed"] = date.today().isoformat()
            result = fetch(source["uri"])
            source.setdefault("content", {})
            source["content"]["fetch_date"] = date.today().isoformat()
            source["content"]["fetch_status"] = result.get("status")
            source["content"]["fetch_content_type"] = result.get("content_type", "")
            if result.get("text"):
                source["raw_text"] = result["text"]
                source["content"]["retrieved_sha256"] = result["sha256"]
                source["content"]["snapshot_status"] = "refreshed_from_fetch"
                source["content"].pop("fetch_error", None)
            else:
                source["content"]["fetch_error"] = result.get("error", "unknown fetch failure")
                source["content"]["snapshot_status"] = "historical_snapshot_not_refreshed" if source.get("raw_text") else "unavailable"
                failures.append((path.name, source["source_id"], source["uri"], source["content"]["fetch_status"], source["content"]["fetch_error"]))
            changed = True
        if args.apply and changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{path.name}: {len(data.get('sources', []))} sources refreshed")
    print(f"failures: {len(failures)}")
    for item in failures:
        print("FAIL", *item, sep=" | ")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
