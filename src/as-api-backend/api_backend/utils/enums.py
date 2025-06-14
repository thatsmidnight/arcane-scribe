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
        generative_llm: Response generated using a generative LLM.
        hybrid: Response generated using a combination of retrieval and generative methods.
    """

    retrieval_only = "retrieval_only"
    generative_llm = "generative_llm"
    hybrid = "hybrid"
