"""Stored names for uploaded files.

A proof or attachment is saved under a random name, not the one it was
uploaded with: the original name ("paspor Ahmad.pdf") leaks in URLs and logs,
and a predictable path can be guessed. The display name, where one is shown,
lives in its own field (Attachment.name).
"""
import os
import uuid

from django.utils.deconstruct import deconstructible


def random_name(filename):
    """<32 hex chars><original extension, lower-case>."""
    return f"{uuid.uuid4().hex}{os.path.splitext(filename)[1].lower()[:10]}"


@deconstructible
class RandomFileName:
    """upload_to for a FileField: `folder` + a random name."""

    def __init__(self, folder):
        self.folder = folder

    def __call__(self, instance, filename):
        return f"{self.folder}{random_name(filename)}"

    def __eq__(self, other):
        return isinstance(other, RandomFileName) and other.folder == self.folder
