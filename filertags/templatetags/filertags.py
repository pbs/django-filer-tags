import logging
import hashlib

from django import template
from django.db.models import Q
from django.core.cache import cache
from django.template.defaultfilters import stringfilter, slugify

from filer.models import File, Folder

logger = logging.getLogger(__name__)


def filerthumbnail(path):
    parts = path.strip('/').split('/')
    folder_names = parts[:-1]
    file_name = parts[-1]
    if not path or not folder_names or not file_name:
        return None

    current_parent = None
    try:
        for f in folder_names:
            if not current_parent:
                folder = Folder.objects.get(name=f, parent__isnull=True)
            else:
                folder = Folder.objects.get(name=f, parent=current_parent)
            current_parent = folder
        q = Q(original_filename=file_name, folder=folder, name='')
        q |= Q(original_filename=file_name, folder=folder, name__isnull=True)
        q |= Q(name=file_name, folder=folder)
        return File.objects.get(q).file
    except (File.DoesNotExist, File.MultipleObjectsReturned, Folder.DoesNotExist), e:
        logger.info('%s on %s' % (e.message, path))
        return None


def get_filerfile_cache_key(path):
    # since the path might be longer than 250 characters
    # (max lenght allowed by memcached), we use a md5 hash of the path
    return '%s-%d-%s' % ('filer-', len(path), hashlib.md5(path).hexdigest())


def filerfile(path):
    """django-filer has two concepts of paths:
    * the logical path: media/images/foobar.png
    * the actual url: filer_public/2012/11/22/foobar.png
    This tag returns the actual url associated with the logical path.

    Since most of the templates will be referencing the same
    resources (css, js), the returned urls are being cached.
    """
    cache_key = get_filerfile_cache_key(path)
    if cache.has_key(cache_key):
        return cache.get(cache_key)
    file_obj = filerthumbnail(path)
    if file_obj is None or not file_obj:
        url = ''
    else:
        url = file_obj.url
    cache.set(cache_key, url)
    return url


def mustache(path):
    url = filerfile(path)
    return 'http://mustachify.me/?src=%s' % url


register = template.Library()
register.filter(stringfilter(filerthumbnail))
register.filter(stringfilter(filerfile))
register.filter(stringfilter(mustache))
