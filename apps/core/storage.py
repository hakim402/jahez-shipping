"""Retained confidential files have no public URL; no upload/download workflow exists."""
from django.core.files.storage import FileSystemStorage

class PrivateStorage(FileSystemStorage):
    def url(self, name):
        raise ValueError('Private storage has no public URL.')
