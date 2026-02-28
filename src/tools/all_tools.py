from tools.deep_search import deep_search
from tools.engine_search import engine_search_tool
from tools.final_report import final_report
from tools.github_tools import github_repo_summary, github_search_repos
from tools.image_descriptor import describe_image
from tools.pinterest import pinterest_scrape_by_username
from tools.web_content_tools import get_url_content
from tools.wiki_tools import wiki_fetch_page, wiki_search_pages

def get_all_tools():
    return [
        pinterest_scrape_by_username,
        deep_search,
        engine_search_tool,
        get_url_content,
        # get_pdf_content,
        wiki_fetch_page,
        wiki_search_pages,
        github_repo_summary,
        github_search_repos,
        describe_image,
        final_report,
    ]