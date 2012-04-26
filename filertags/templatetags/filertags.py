from django import template
from django.template.defaultfilters import stringfilter
from django.db.models import Q
from django.core.urlresolvers import reverse
from filer.models import File, Folder


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
    except (File.DoesNotExist, Folder.DoesNotExist):
        pass


def filerfile(path):
    ft = filerthumbnail(path)
    if ft is None or not ft:
        return ''
    return ft.url

def mustache(path):
    url = filerfile(path)
    return 'http://mustachify.me/?src=%s' % url

def filercss(path):
    return reverse('css-preprocessor', args=[path])


register = template.Library()
register.filter(stringfilter(filerthumbnail))
register.filter(stringfilter(filerfile))
register.filter(stringfilter(filercss))
register.filter(stringfilter(mustache))
