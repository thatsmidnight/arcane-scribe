from enum import Enum


class AllowedMethod(str, Enum):
    get = "GET"
    post = "POST"
    put = "PUT"
    delete = "DELETE"
    patch = "PATCH"
    head = "HEAD"
