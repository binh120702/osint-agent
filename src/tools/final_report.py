from langchain.messages import SystemMessage, HumanMessage
from langchain.tools import tool

from llms.openai_client import OPENAI_CLIENT


FINAL_REPORT_SYSTEM_PROMPT = """
You are an OSINT agent that helps exploring and investigating information about a person.
You have been given a case to investigate.
Generate a final report of the investigation.

When using, citing any information from the internet, you MUST ALWAYS cite the source.
When citing the source, you MUST ALWAYS cite the source URL, not just the domain name.
If there are many subpages, you MUST ALWAYS cite the source URLs of the subpages independently.
DO NOT MERGE THE CITATION OF THE SUBPAGES WITH THE SOURCE URL OF THE MAIN PAGE.
DO NOT FORGET TO INCLUDE THE HTTP/HTTPS PROTOCOL IN THE SOURCE URL.
When making any conclusion about the object, you must cite the sentence or image with URL to prove the conclusion.
The report should be in the following format (you may adapt it based on the information you have gathered):
- CASE BACKGROUND
- GENERAL OBJECTIVES
- LEGAL ISSUES
- INVESTIGATION PREPARATION
- OSINT STEPS
- FINDINGS
- CONCLUSION
- REFERENCES

Only use this tool after the user has explicitly asked for a final report and confirmed they are ready to stop gathering new information.
"""


@tool
def final_report(investigation_summary: str) -> str:
    """Generate a structured OSINT final report from the investigation summary.

    This tool MUST only be called after the user explicitly asks for a final report
    and confirms they are ready to stop gathering additional information.
    """
    messages = [
        SystemMessage(content=FINAL_REPORT_SYSTEM_PROMPT),
        HumanMessage(content=investigation_summary),
    ]
    response = OPENAI_CLIENT.invoke(messages)
    return getattr(response, "content", str(response))

