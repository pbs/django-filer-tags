import hashlib
import os.path
import re
import StringIO
import urlparse

from django.core.cache import cache
from django.core.files.uploadedfile import UploadedFile
from django.db.models import signals

from filer.models.filemodels import File
from filer.models.imagemodels import Image

from templatetags.filertags import filerfile, get_filerfile_cache_key


_LOGICAL_URL_TEMPLATE = "/* logicalurl('%s') */"
_RESOURCE_URL_TEMPLATE = "url('%s') " + _LOGICAL_URL_TEMPLATE
_RESOURCE_URL_REGEX = re.compile(r"\burl\(([^\)]*)\)")

_COMMENT_REGEX = re.compile(r"/\*.*?\*/")
_ALREADY_PARSED_MARKER = '/* Filer urls already resolved */'


def _is_in_clipboard(filer_file):
    return filer_file.folder is None


def _construct_logical_folder_path(filer_file):
    return os.path.join(*(folder.name for folder in filer_file.logical_path))


def _get_commented_regions(content):
    return [(m.start(), m.end()) for m in re.finditer(_COMMENT_REGEX, content)]


def _is_not_on_s3(file_):
    return isinstance(file_, UploadedFile)


def _rewrite_file_content(filer_file, new_content):
    if _is_not_on_s3(filer_file.file.file):
        filer_file.file.seek(0)
        filer_file.file.write(new_content)
    else:
        storage = filer_file.file.storage
        fp = StringIO.StringIO()
        fp.write(new_content)
        fp.seek(0)
        storage.save(filer_file.file.name, fp)
    sha = hashlib.sha1()
    sha.update(new_content)
    filer_file.sha1 = sha.hexdigest()
    filer_file._file_size = len(new_content)


def _resolve_resource_urls(css_file):
    logical_folder_path = _construct_logical_folder_path(css_file)
    content = css_file.file.read()
    if content.startswith(_ALREADY_PARSED_MARKER):
        # this css' resource urls have already been resolved
        # this happens when moving the css in and out of the clipboard
        # multiple times
        return

    commented_regions = _get_commented_regions(content)
    local_cache = {}

    def change_urls(match):
        for start, end in commented_regions:
            # we don't make any changes to urls that are part of commented regions
            if start < match.start() < end or start < match.end() < end:
                return match.group()
        # strip spaces and quotes
        url = match.group(1).strip('\'\" ')
        parsed_url = urlparse.urlparse(url)
        if parsed_url.netloc:
            # if the url is absolute, leave it unchaged
            return match.group()
        relative_path = url
        logical_file_path = os.path.normpath(
            os.path.join(logical_folder_path, relative_path))
        if not logical_file_path in local_cache:
            local_cache[logical_file_path] = _RESOURCE_URL_TEMPLATE % (
                filerfile(logical_file_path), logical_file_path)
        return local_cache[logical_file_path]

    new_content = '%s\n%s' % (
        _ALREADY_PARSED_MARKER,
        re.sub(_RESOURCE_URL_REGEX, change_urls, content))
    _rewrite_file_content(css_file, new_content)


def _update_referencing_css_files(resource_file):
    if resource_file.name:
        resource_name = resource_file.name
    else:
        resource_name = resource_file.original_filename
    logical_file_path = os.path.join(
        _construct_logical_folder_path(resource_file),
        resource_name)
    css_files = File.objects.filter(original_filename__endswith=".css")

    for css in css_files:
        logical_url_snippet = _LOGICAL_URL_TEMPLATE % logical_file_path
        url_updating_regex = "%s %s" % (
            _RESOURCE_URL_REGEX.pattern, re.escape(logical_url_snippet))
        repl = "url('%s') %s" % (resource_file.url, logical_url_snippet)
        try:
            new_content = re.sub(url_updating_regex, repl, css.file.read())
        except IOError:
            # the filer database might have File entries that reference
            # files no longer phisically exist
            # TODO: find the root cause of missing filer files
            continue
        else:
            _rewrite_file_content(css, new_content)


def resolve_css_resource_urls(instance, **kwargs):
    """Post save hook for filer resources.
    It's purpose is to resolve the actual urls of resources referenced
    in css files.

    django-filer has two concepts of urls:
    * the logical url: media/images/foobar.png
    * the actual url: filer_public/2012/11/22/foobar.png

    The css as written by the an end user uses logical urls:
    .button.nice { 
        background: url('../images/misc/foobar.png');
        -moz-box-shadow: inset 0 1px 0 rgba(255,255,255,.5);
    }

    In order for the resources to be found, the logical urls need to be
    replaced with the actual urls.

    This post save hook does this in two ways:
    1) whenever a css is saved it parses the content and rewrites all logical
       urls to their actual urls; the logical url is still being saved
       as a comment that follows the actual url. This comment is needed for
       the behaviour described at point 2.

       After url rewriting the above css snippet will look like:
       .button.nice { 
          background: url('filer_public/2012/11/22/foobar.png') /* logicalurl('media/images/misc/foobar.png') /* ;
          -moz-box-shadow: inset 0 1px 0 rgba(255,255,255,.5);
       }

    2) when any other kind of resource is saved, all css files are parsed for
       references to the resource being saved. If found, the actual url is
       being rewritten.

       References are found by looking for comments such as:
       /* logicalurl('media/images/misc/foobar.png') */

       If the url between parentheses matches the logical url of the resource
       being saved, the actual url (which percedes the comment)
       is being updated.
    """
    if _is_in_clipboard(instance):
        return
    if instance.original_filename.endswith('.css'):
        _resolve_resource_urls(instance)
    else:
        _update_referencing_css_files(instance)


def clear_urls_cache(instance, **kwargs):
    """Clears urls cached by the filerfile tag. """
    logical_file_path = os.path.join(
        _construct_logical_folder_path(instance),
        instance.original_filename)
    cache_key = get_filerfile_cache_key(logical_file_path)
    cache.delete(cache_key)


signals.pre_save.connect(resolve_css_resource_urls, sender=File)
signals.pre_save.connect(resolve_css_resource_urls, sender=Image)

signals.post_save.connect(clear_urls_cache, sender=File)
signals.post_save.connect(clear_urls_cache, sender=Image)
