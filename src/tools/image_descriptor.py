import json
import time

from dotenv import load_dotenv
from langchain.tools import tool
from openai import OpenAI


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

    client = OpenAI()

    max_retries = 3
    backoff_seconds = 1.0
    description_text = None
    last_error_message = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.responses.create(
                model="gpt-4.1-nano-2025-04-14",
                input=[{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": IMAGE_DESCRIPTION_PROMPT},
                        {"type": "input_image", "image_url": image_url},
                    ]
                }]
            )
            description_text = getattr(response, "output_text", None)
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
    return json.dumps(results, indent=2, default=str)