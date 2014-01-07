DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sites',
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'filer',
    'easy_thumbnails'
]

import filer.settings

filer_storages = getattr(filer.settings, 'FILER_STORAGES', {})

LOGICAL_EQ_ACTUAL_URL = all(
    storage['main']['UPLOAD_TO'] == 'filer.utils.generate_filename.by_path'
    for storage in filer_storages.values())
