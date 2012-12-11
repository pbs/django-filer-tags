import codecs
import hashlib
import os
import os.path
import re
import urlparse

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db.models import signals

from filer.models.filemodels import File
from filer.models.imagemodels import Image

from templatetags.filertags import filerfile, get_filerfile_cache_key


_LOGICAL_URL_TEMPLATE = u"/* logicalurl('%s') */"
_RESOURCE_URL_TEMPLATE = u"url('%s') " + _LOGICAL_URL_TEMPLATE
_RESOURCE_URL_REGEX = re.compile(ur"\burl\(([^\)]*)\)")

_COMMENT_REGEX = re.compile(ur"/\*.*?\*/")
_ALREADY_PARSED_MARKER = u'/* Filer urls already resolved */'


def _is_in_clipboard(filer_file):
    return filer_file.folder is None


def _construct_logical_folder_path(filer_file):
    return os.path.join(*(folder.name for folder in filer_file.logical_path))


def _get_commented_regions(content):
    return [(m.start(), m.end()) for m in re.finditer(_COMMENT_REGEX, content)]


def _is_in_memory(file_):
    return isinstance(file_, UploadedFile)


def _get_encoding_from_bom(content):
    bom_to_encoding = {
        codecs.BOM_UTF8: 'utf-8-sig',
        codecs.BOM_UTF16_LE: 'utf-16',
        codecs.BOM_UTF16_BE: 'utf-16',
        codecs.BOM_UTF32_LE: 'utf-32',
        codecs.BOM_UTF32_BE: 'utf-32'
        }
    for bom in bom_to_encoding:
        if content.startswith(bom):
            return bom_to_encoding[bom]
    return None


def _get_css_encoding(content, css_name):
    """ Return a css file's character encoding using the rules from:
    http://www.w3.org/TR/CSS2/syndata.html#charset
    """
    # look for BOM
    from_bom = _get_encoding_from_bom(content)
    if from_bom:
        return from_bom
    # no BOM, look for @charset directive
    encoding = re.match(r'@charset "([^"]*)";', content)
    if encoding:
        encoding = encoding.group(1)
        try:
            codecs.lookup(encoding)
        except LookupError:
            # a nicely displayed error for the end user would be nice here
            # unfortunately you can't do that from a pre/post save hook...
            # this will result in a 500, but this shouldn't happen often, but
            # in case it does, the exception message will help debugging
            raise ValueError(
                'Css %s specifies invalid charset %s' % (css_name, encoding))
        return encoding
    # assume utf-8. If we're wrong, the user will get an ugly 500 ...
    # (same problem as described in the comment above...)
    return 'utf-8'


def _rewrite_file_content(filer_file, new_content):
    if _is_in_memory(filer_file.file.file):
        filer_file.file.seek(0)
        filer_file.file.write(new_content)
    else:
        storage = filer_file.file.storage
        fp = ContentFile(new_content, filer_file.file.name)
        filer_file.file.file = fp
        filer_file.file.name = storage.save(filer_file.file.name, fp)
    sha = hashlib.sha1()
    sha.update(new_content)
    filer_file.sha1 = sha.hexdigest()
    filer_file._file_size = len(new_content)


def _is_css(filer_file):
    return _get_filer_file_name(filer_file).endswith('.css')


def _get_filer_file_name(file_):
    return file_.name if file_.name else file_.original_filename


def _insert_already_parsed_marker(content):
    match = re.match(ur'@charset "[^"]*";', content)
    if not match:
        return u'%s\n%s' % (_ALREADY_PARSED_MARKER, content)
    else:
        # make sure that the @charset statement remains the first
        # directive in the css
        end = match.end()
        return u'%s%s%s' % (
            content[:end], _ALREADY_PARSED_MARKER, content[end:])


def _is_already_parsed(content):
    regex = ur'(@charset "([^"]*)";)?' + re.escape(_ALREADY_PARSED_MARKER)
    return re.match(regex, content) is not None


def resolve_resource_urls(instance, **kwargs):
    """Post save hook for css files uploaded to filer.
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

    Whenever a css is saved it parses the content and rewrites all logical
    urls to their actual urls; the logical url is still being saved
    as a comment that follows the actual url. This comment is needed for
    the behaviour described at point 2.

    After url rewriting the above css snippet will look like:
    .button.nice {
       background: url('filer_public/2012/11/22/foobar.png') /* logicalurl('media/images/misc/foobar.png') /* ;
       -moz-box-shadow: inset 0 1px 0 rgba(255,255,255,.5);
    }
    """
    if not _is_css(instance):
        return
    css_file = instance
    if _is_in_clipboard(css_file):
        return
    content = css_file.file.read()
    encoding = _get_css_encoding(content, _get_filer_file_name(css_file))
    content = content.decode(encoding)
    if _is_already_parsed(content):
        # this css' resource urls have already been resolved
        # this happens when moving the css in and out of the clipboard
        # multiple times
        return

    logical_folder_path = _construct_logical_folder_path(css_file)
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

    new_content = _insert_already_parsed_marker(
        re.sub(_RESOURCE_URL_REGEX, change_urls, content))
    new_content = new_content.encode(encoding)
    _rewrite_file_content(css_file, new_content)


def update_referencing_css_files(instance, **kwargs):
    """Post save hook for any resource uploaded to filer that
    might be referenced by a css.
    The purpose of this hook is to update the actual url in all css files that
    reference the resource pointed by 'instance'.

    References are found by looking for comments such as:
    /* logicalurl('media/images/misc/foobar.png') */

    If the url between parentheses matches the logical url of the resource
    being saved, the actual url (which percedes the comment)
    is being updated.
    """
    if _is_css(instance):
        return
    resource_file = instance
    if _is_in_clipboard(resource_file):
        return
    resource_name = _get_filer_file_name(resource_file)
    logical_file_path = os.path.join(
        _construct_logical_folder_path(resource_file),
        resource_name)
    css_files = File.objects.filter(original_filename__endswith=".css")
    for css in css_files:
        logical_url_snippet = _LOGICAL_URL_TEMPLATE % logical_file_path
        url_updating_regex = u"%s %s" % (
            _RESOURCE_URL_REGEX.pattern, re.escape(logical_url_snippet))
        repl = u"url('%s') %s" % (resource_file.url, logical_url_snippet)
        try:
            old_content = css.file.read()
            encoding = _get_css_encoding(old_content, _get_filer_file_name(css))
            content = old_content.decode(encoding)
            new_content = re.sub(url_updating_regex, repl, content)
            new_content = new_content.encode(encoding)
        except IOError:
            # the filer database might have File entries that reference
            # files no longer phisically exist
            # TODO: find the root cause of missing filer files
            continue
        else:
            if old_content != new_content:
                _rewrite_file_content(css, new_content)
                css.save()


def clear_urls_cache(instance, **kwargs):
    """Clears urls cached by the filerfile tag. """
    logical_file_path = os.path.join(
        _construct_logical_folder_path(instance),
        instance.original_filename)
    cache_key = get_filerfile_cache_key(logical_file_path)
    cache.delete(cache_key)


signals.pre_save.connect(resolve_resource_urls, sender=File)
signals.post_save.connect(update_referencing_css_files, sender=File)
signals.post_save.connect(update_referencing_css_files, sender=Image)

signals.post_save.connect(clear_urls_cache, sender=File)
signals.post_save.connect(clear_urls_cache, sender=Image)
