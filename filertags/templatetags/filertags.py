import logging

from django import template
from django.db.models import Q
from django.template.defaultfilters import stringfilter

from filer.models import File, Folder
import filer.settings as filer_settings
# TODO: this is ugly: the ..settings is because the toplevel package
#    name has the same name as this module; should probably rename the toplevel package?
from ..settings import LOGICAL_EQ_ACTUAL_URL

logger = logging.getLogger(__name__)


def q_matches_name(file_name):
    return (Q(original_filename=file_name, name='') |
            Q(original_filename=file_name, name__isnull=True) |
            Q(name=file_name))


def filerthumbnail(path):
    parts = path.strip('/').split('/')
    folder_names = parts[:-1]
    file_name = parts[-1]
    if not path or not folder_names or not file_name:
        return None

    current_parent = None
    try:
        for folder_name in folder_names:
            if not current_parent:
                folder = Folder.objects.get(name=folder_name, parent__isnull=True)
            else:
                folder = Folder.objects.get(name=folder_name, parent=current_parent)
            current_parent = folder
        return File.objects.get(q_matches_name(file_name), Q(folder=folder)).file
    except (File.DoesNotExist, File.MultipleObjectsReturned, Folder.DoesNotExist), e:
        logger.info('%s on %s' % (e.message, path))
        return None


def get_possible_paths(path):
    return ['%s/%s' % (storage['main']['UPLOAD_TO_PREFIX'], path)
            for storage in filer_settings.FILER_STORAGES.values()]


def find_hashed_file(path):
    path = path.strip('/')
    slash_index = path.rfind('/')
    folder_slug, file_name = path[:slash_index+1], path[slash_index+1:]
    for folder_path in get_possible_paths(folder_slug):
        slash_count = folder_path.count('/')
        candidates = File.objects.filter(q_matches_name(file_name), file__startswith=folder_path)
        for candidate in candidates:
            if str(candidate.file).count('/') == slash_count:
                return candidate


def filerfile(path):
    """django-filer has two concepts of paths:
    * the logical path: media/images/foobar.png
    * the actual url: filer_public/2012/11/22/foobar.png
    This tag returns the actual url associated with the logical path.
    """
    path = path.strip('/')
    if LOGICAL_EQ_ACTUAL_URL:
        try:
            return File.objects.get(file__in=get_possible_paths(path)).url
        except (File.DoesNotExist, File.MultipleObjectsReturned), e:
            filer_file = find_hashed_file(path)
            if filer_file:
                return filer_file.url
            logger.info('%s on %s' % (e.message, path))
            return path
    else:
        file_obj = filerthumbnail(path)
        return file_obj.url if file_obj else ''


def mustache(path):
    url = filerfile(path)
    return 'http://mustachify.me/?src=%s' % url


register = template.Library()
register.filter(stringfilter(filerthumbnail))
register.filter(stringfilter(filerfile))
register.filter(stringfilter(mustache))
