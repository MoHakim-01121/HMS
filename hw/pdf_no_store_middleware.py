class PdfNoStoreMiddleware:
    """Generated PDFs must never be reused from a browser cache.

    Phones (Safari, Chrome on Android, in-app PDF viewers) kept showing an old
    invoice or CL after it was edited, because the PDF came back without a
    Cache-Control header and the URL never changes. A view that sets its own
    Cache-Control (uploaded attachments in media_views) keeps it.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (response.get("Content-Type", "").startswith("application/pdf")
                and not response.has_header("Cache-Control")):
            response["Cache-Control"] = "private, no-store, max-age=0"
        return response
