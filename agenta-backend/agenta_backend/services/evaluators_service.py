import re
import json
import httpx
from typing import Any, Dict, Tuple

from agenta_backend.services.security import sandbox
from agenta_backend.models.db_models import Error, Result

from langchain.llms import OpenAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def auto_exact_match(
    inputs: Dict[str, Any],
    output: str,
    correct_answer: str,
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    try:
        exact_match = True if output == correct_answer else False
        result = Result(type="bool", value=exact_match)
        return result
    except Exception as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Exact Match evaluation", stacktrace=str(e)
            ),
        )


def auto_similarity_match(
    inputs: Dict[str, Any],
    output: str,
    correct_answer: str,
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    try:
        set1 = set(output.split())
        set2 = set(correct_answer.split())
        intersect = set1.intersection(set2)
        union = set1.union(set2)

        similarity = len(intersect) / len(union)

        is_similar = (
            True if similarity > settings_values["similarity_threshold"] else False
        )
        result = Result(type="bool", value=is_similar)
        return result
    except Exception as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Similarity Match evaluation",
                stacktrace=str(e),
            ),
        )


def auto_regex_test(
    inputs: Dict[str, Any],
    output: str,
    correct_answer: str,
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    try:
        re_pattern = re.compile(settings_values["regex_pattern"], re.IGNORECASE)
        result = (
            bool(re_pattern.search(output)) == settings_values["regex_should_match"]
        )
        return Result(type="bool", value=result)
    except Exception as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Regex evaluation", stacktrace=str(e)
            ),
        )


def field_match_test(
    inputs: Dict[str, Any],
    output: str,
    correct_answer: str,
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    try:
        output_json = json.loads(output)
        result = output_json[settings_values["json_field"]] == correct_answer
        return Result(type="bool", value=result)
    except Exception as e:
        logging.debug("Field Match Test Failed because of Error: " + str(e))
        return Result(type="bool", value=False)


def auto_webhook_test(
    inputs: Dict[str, Any],
    output: str,
    correct_answer: str,
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    try:
        with httpx.Client() as client:
            webhook_body = settings_values.get("webhook_body", None)
            if isinstance(webhook_body, str):
                payload = json.loads(webhook_body)
            if not webhook_body:
                payload = {}
            if isinstance(webhook_body, dict):
                payload = webhook_body
            response = client.post(url=settings_values["webhook_url"], json=payload)
            response.raise_for_status()
            response_data = response.json()
            score = response_data.get("score", None)
            if not score:
                return Result(
                    type="error",
                    value=None,
                    error=Error(
                        message="Error during Auto Webhook evaluation; Webhook did not return a score",
                    ),
                )
            if score < 0 or score > 1:
                return Result(
                    type="error",
                    value=None,
                    error=Error(
                        message="Error during Auto Webhook evaluation; Webhook returned an invalid score. Score must be between 0 and 1",
                    ),
                )
            return Result(type="number", value=score)
    except httpx.HTTPError as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Webhook evaluation; An HTTP error occurred",
                stacktrace=str(e),
            ),
        )
    except Exception as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Webhook evaluation", stacktrace=str(e)
            ),
        )


def auto_custom_code_run(
    inputs: Dict[str, Any],
    output: str,
    correct_answer: str,
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    try:
        result = sandbox.execute_code_safely(
            app_params=app_params,
            inputs=inputs,
            output=output,
            correct_answer=correct_answer,
            code=settings_values["code"],
        )
        return Result(type="number", value=result)
    except Exception as e:
        return Result(
            type="error",
            value=None,
            error=Error(
                message="Error during Auto Custom Code Evaluation", stacktrace=str(e)
            ),
        )


def auto_ai_critique(
    inputs: Dict[str, Any],
    output: str,
    correct_answer: str,
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> str:
    """
    Evaluate a response using an AI critique based on provided inputs, output, correct answer, app parameters, and settings.

    Args:
        inputs (Dict[str, Any]): Input parameters for the LLM app variant.
        output (str): The output of the LLM app variant.
        correct_answer (str): Correct answer for evaluation.
        app_params (Dict[str, Any]): Application parameters.
        settings_values (Dict[str, Any]): Settings for the evaluation.
        lm_providers_keys (Dict[str, Any]): Keys for language model providers.

    Returns:
        str: Evaluation result.
    """
    try:
        llm = OpenAI(
            openai_api_key=lm_providers_keys["OPENAI_API_KEY"],
            temperature=0.8,
            model="gpt-3.5-turbo-instruct",
        )

        chain_run_args = {
            "llm_app_prompt_template": app_params.get("prompt_user", ""),
            "variant_output": output,
            "correct_answer": correct_answer,
        }

        for key, value in inputs.items():
            chain_run_args[key] = value

        prompt = PromptTemplate(
            input_variables=list(
                chain_run_args.keys()
            ),  # Use the keys from chain_run_args
            template=settings_values["prompt_template"],
        )
        chain = LLMChain(llm=llm, prompt=prompt)

        evaluation_output = chain.run(**chain_run_args)

        return Result(type="text", value=evaluation_output.strip())
    except Exception as e:
        return Result(
            type="error",
            value=None,
            error=Error(message="Error during Auto AI Critique", stacktrace=str(e)),
        )


def evaluate(
    evaluator_key: str,
    inputs: Dict[str, Any],
    output: str,
    correct_answer: str,
    app_params: Dict[str, Any],
    settings_values: Dict[str, Any],
    lm_providers_keys: Dict[str, Any],
) -> Result:
    evaluation_function = globals().get(evaluator_key, None)
    if not evaluation_function:
        raise ValueError(f"Evaluation method '{evaluator_key}' not found.")
    try:
        return evaluation_function(
            inputs,
            output,
            correct_answer,
            app_params,
            settings_values,
            lm_providers_keys,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Error occurred while running {evaluator_key} evaluation. Exception: {str(exc)}"
        )
