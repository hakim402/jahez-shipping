from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    def url(self, name):
        raise ValueError("Private documents have no public URL. Use the authorized download view.")
