import json
import time

from dotenv import load_dotenv
from agent.tool_decorator import tool

# Loaded lazily by describe_image to keep metadata/config imports lightweight.


load_dotenv()


IMAGE_DESCRIPTION_PROMPT = """
    You are an OSINT agent that describes images in detail for investigation purposes.
    You will be given an image url and you need to describe the image in detail for investigation purposes.
    The image is likely to be a photo of a person, a place, an object, or a scene.
    Describe everything you can see in the image.
"""


@tool
def describe_image(image_url: str) -> str:
    """Describe an image, input the url of the image to describe.
    Args:
        image_url: The url of the image to describe.
    Returns:
        A detailed description of the image.
    """

    max_retries = 3
    backoff_seconds = 1.0
    description_text = None
    last_error_message = None

    for attempt in range(1, max_retries + 1):
        try:
            from llms.client_factory import ACTIVE_LLM_CLIENT
            description_text = ACTIVE_LLM_CLIENT.describe_image(
                image_url=image_url, prompt=IMAGE_DESCRIPTION_PROMPT
            )
            if description_text:
                break
            last_error_message = "Empty response from image descriptor API"
        except Exception as e:
            last_error_message = str(e)
        if attempt < max_retries:
            time.sleep(backoff_seconds)
            backoff_seconds *= 2

    if not description_text:
        description_text = (
            "Unable to generate a detailed description at this time. "
            "Default summary: The image content could not be analyzed due to a temporary issue."
        )

    results = {
        "image_url": image_url,
        "description": description_text,
        "meta": {
            "retries": min(attempt, max_retries),
            "had_error": last_error_message is not None and (description_text is None or "Unable to generate" in description_text),
            "last_error": last_error_message
        }
    }

    # Persist image description into KB as IMAGE entity notes for later retrieval.
    try:
        from tools.knowledge_base import upsert_image_entity_description

        upsert_image_entity_description(image_ref=image_url, description=description_text)
        results["meta"]["kb_entity_updated"] = True
    except Exception as e:
        results["meta"]["kb_entity_updated"] = False
        results["meta"]["kb_update_error"] = str(e)

    return json.dumps(results, indent=2, default=str)