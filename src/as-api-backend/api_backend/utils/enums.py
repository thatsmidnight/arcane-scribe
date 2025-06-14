# Standard Library
from enum import Enum


class AllowedMethod(str, Enum):
    """Enumeration of allowed HTTP methods.

    Attributes:
        get: HTTP GET method.
        post: HTTP POST method.
        put: HTTP PUT method.
        delete: HTTP DELETE method.
        patch: HTTP PATCH method.
        head: HTTP HEAD method.
    """

    get = "GET"
    post = "POST"
    put = "PUT"
    delete = "DELETE"
    patch = "PATCH"
    head = "HEAD"


class ResponseSource(str, Enum):
    """Enumeration of possible response sources.

    Attributes:
        retrieval_only: Response generated using only retrieval methods.
        bedrock_llm: Response generated using Bedrock LLM.
    """

    retrieval_only = "retrieval_only"
    bedrock_llm = "bedrock_llm"
