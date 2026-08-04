import brotli


class BrotliMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (response.status_code == 200
                and "text" in response.get("Content-Type", "")
                and not response.get("Content-Encoding")):
            accept_encoding = request.META.get("HTTP_ACCEPT_ENCODING", "")
            if "br" in accept_encoding and len(response.content) > 500:
                compressed = brotli.compress(response.content)
                if len(compressed) < len(response.content):
                    response.content = compressed
                    response["Content-Encoding"] = "br"
                    response["Content-Length"] = str(len(compressed))
        return response