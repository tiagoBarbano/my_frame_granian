import re
import msgspec
import orjson

from jsonschema import Draft7Validator, ValidationError

from functools import lru_cache

CONTENT_TYPE_TEXT_HTML_HEADER = [(b"content-type", b"text/html")]
CONTENT_TYPE_TEXT_PLAIN_HEADER = [(b"content-type", b"text/plain")]
CONTENT_TYPE_APPLICATION_JSON_HEADER = [(b"content-type", b"application/json")]


@lru_cache(maxsize=128)
def get_validator(model_cls):
    schema = msgspec.json.schema(model_cls)
    validator = Draft7Validator(schema["$defs"][model_cls.__name__])
    return validator


async def validate_schema_dict(body, ModelDto):
    """
    Validate the request body against the provided schema.
    This function takes the request body and a model class as input,
    and uses the jsonschema library to validate the data.
    If the validation fails, it raises a ValidationError with the
    appropriate error message.
    If the validation succeeds, it returns the validated data
    as a dictionary.
    """
    data = msgspec.json.decode(body) if isinstance(body, bytes) else body
    validator = get_validator(ModelDto)

    if erros := sorted(validator.iter_errors(data), key=lambda e: e.path):
        message_error = []
        message_error.extend(
            {
                "field": e.json_path,
                "message": e.message,
                "validator": e.validator,
            }
            for e in erros
        )
        error = {"detail": message_error, "body": body}
        raise ValidationError(message=error)

    return ModelDto(**data).encode_dict()


async def validate_schema_object(body, ModelDto):
    """
    Validate the request body against the provided schema.
    This function takes the request body and a model class as input,
    and uses the jsonschema library to validate the data.
    If the validation fails, it raises a ValidationError with the
    appropriate error message.
    If the validation succeeds, it returns the validated data
    as an instance of the model class.
    """
    data = orjson.loads(body) if isinstance(body, bytes) else body
    validator = get_validator(ModelDto)

    if erros := sorted(validator.iter_errors(data), key=lambda e: e.path):
        message_error = []
        message_error.extend(
            {
                "field": e.json_path,
                "message": e.message,
                "validator": e.validator,
            }
            for e in erros
        )
        error = {"detail": message_error, "body": body}
        raise ValidationError(message=error)

    return ModelDto(**data)


def compile_path_to_regex(path_template):
    """
    Convert a path template with placeholders into a regex pattern.
    This function takes a path template string (e.g., "/item/{id}")
    and converts it into a regex pattern that can be used for matching.
    The placeholders in the path template are replaced with regex groups
    that capture the corresponding values.
    For example, "/item/{id}" becomes "^/item/(?P<id>[^/]+)$".
    """

    pattern = re.sub(r"{(\w+)}", r"(?P<\1>[^/]+)", path_template)
    return re.compile(f"^{pattern}$")


def json_response(data, status=200, headers: dict[str, str] = None):
    """
    Return a response with JSON content type.
    This function takes the response data and status code as input
    and returns a tuple containing the status code, headers, and body.
    The headers include the content type set to "application/json".
    """
    headers_response = (
        [(k.encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()]
        if headers
        else []
    )
    headers_response.extend(CONTENT_TYPE_APPLICATION_JSON_HEADER)

    return status, headers_response, [msgspec.json.encode(data)]


def text_plain_response(data, status=200, headers=None):
    """
    Return a response with plain text content type.
    This function takes the response data and status code as input
    and returns a tuple containing the status code, headers, and body.
    The headers include the content type set to "text/plain".
    """

    headers_response = (
        [(k.encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()]
        if headers
        else []
    )
    headers_response.extend(CONTENT_TYPE_TEXT_PLAIN_HEADER)

    return status, headers_response, [data]


def text_html_response(data, status=200, headers=None):
    """
    Return a response with HTML content type.
    This function takes the response data and status code as input
    and returns a tuple containing the status code, headers, and body.
    The headers include the content type set to "text/html".
    """

    headers_response = (
        [(k.encode("utf-8"), v.encode("utf-8")) for k, v in headers.items()]
        if headers
        else []
    )
    headers_response.extend(CONTENT_TYPE_TEXT_HTML_HEADER)

    return status, headers_response, [data]


async def read_body(receive) -> dict:
    """
    Read the body of the request from the ASGI receive channel.
    This function handles chunked transfer encoding and concatenates
    the received chunks into a single bytes object.
    It returns the complete request body as a dictionary.
    """
    body = b""
    while True:
        message = await receive()
        if message["type"] == "http.request":
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
    return msgspec.json.decode(body)


async def send_response(send, response):
    """
    Send an HTTP response to the ASGI send channel.
    This function takes the ASGI send channel and a response tuple
    containing the status code, headers, and body.
    It sends the response start message and then sends the response body
    in chunks.
    """

    status, headers, body = response
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body[0]})
