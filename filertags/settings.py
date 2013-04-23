from django.conf import settings

filer_storages = getattr(settings, 'FILER_STORAGES', {})

LOGICAL_EQ_ACTUAL_URL = all(
    storage['main']['UPLOAD_TO'] == 'filer.utils.generate_filename.by_path'
    for storage in filer_storages.values())
