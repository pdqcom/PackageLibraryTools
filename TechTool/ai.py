import json
import os
import urllib.error
import urllib.request


API_KEY_ENV = "OpenAI_API_Key"
API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5-mini"


def ask_ai(prompt, instructions="", context="", model=DEFAULT_MODEL):
    api_key = os.getenv(API_KEY_ENV)
    if not api_key: raise Exception(f"Ai Key '{API_KEY_ENV}' was not found. Please set this value in the app settings.")

    body = {
        "model": model,
        "instructions": instructions,
        "input": f"""CONTEXT
    -------
    {context}

    USER REQUEST
    ------------
    {prompt}
    """
    }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as ex:
        error_text = ex.read().decode("utf-8")
        raise Exception(f"OpenAI API Error ({ex.code}): {error_text}")

    except urllib.error.URLError as ex:
        raise Exception(f"Unable to contact OpenAI: {ex.reason}")

    except Exception as ex:
        raise Exception(f"Unexpected AI error: {ex}")

    try:
        for item in result["output"]:
            if item["type"] != "message": continue

            for content in item["content"]:
                if content["type"] == "output_text": return content["text"]

        raise Exception("No assistant response was returned.")

    except Exception as ex:
        raise Exception(f"{ex}\n\nOpenAI returned:\n{json.dumps(result, indent=2)}")