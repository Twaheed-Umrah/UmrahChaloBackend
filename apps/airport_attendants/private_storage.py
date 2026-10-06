from django.conf import settings
from django.core.files.storage import FileSystemStorage


if getattr(settings, 'USE_S3', False):
    from storages.backends.s3boto3 import S3Boto3Storage

    class PrivateKYCStorage(S3Boto3Storage):
        default_acl = 'private'
        querystring_auth = True
        file_overwrite = False
else:
    class PrivateKYCStorage(FileSystemStorage):
        def __init__(self, *args, **kwargs):
            kwargs.setdefault('location', settings.BASE_DIR / 'private_kyc')
            super().__init__(*args, **kwargs)


private_kyc_storage = PrivateKYCStorage()
