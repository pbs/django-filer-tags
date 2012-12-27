import os.path
import re

from django.core.cache import cache
from django.core.files.base import File as DjangoFile, ContentFile
from django.test import TestCase

from filer.models.filemodels import File
from filer.models.foldermodels import Folder
from filer.tests.helpers import (create_superuser, create_folder_structure,
                                 create_image, create_clipboard_item)

from filertags.signals import _ALREADY_PARSED_MARKER, _LOGICAL_URL_TEMPLATE


class CssRewriteTest(TestCase):

    def setUp(self):
        self.superuser = create_superuser()
        self.client.login(username='admin', password='secret')
        media_folder = Folder.objects.create(name='media')
        producer = Folder.objects.create(name='producer', parent=media_folder)
        self.producer_css = Folder.objects.create(name='css', parent=producer)
        self.producer_images = Folder.objects.create(name='images', parent=producer)

    def tearDown(self):
        cache.clear()

    def create_file(self, name, folder, content=None):
        if content is None:
            file_obj = DjangoFile(
                open(os.path.join(os.path.dirname(__file__), 'test_files', name)),
                name=name)
        else:
            file_obj = ContentFile(content, name)
        return File.objects.create(owner=self.superuser,
                                   original_filename=name,
                                   file=file_obj,
                                   folder=folder)


    def test_abslute_url_css_before_image(self):
        css = self.create_file('absolute_url_to_image.css', self.producer_css,
                               content="""\
.pledge-block {
    background: url('/media/producer/images/foobar.png');
}
""")
        css_content = open(css.path).read()
        self.assertTrue(css_content.startswith(_ALREADY_PARSED_MARKER))
        self.assertIn("url('')", css_content)
        logical_url = _LOGICAL_URL_TEMPLATE % '/media/producer/images/foobar.png'
        self.assertIn(logical_url, css_content)
        image = self.create_file('foobar.png', self.producer_images)
        updated_css = File.objects.get(pk=css.pk)
        new_content = open(updated_css.path).read()
        self.assertIsNotNone(re.search(r"\burl\('[^']*foobar[^']*png'\)", new_content))

    def _verify_css_is_corectly_rewritten(self, css):
        css_content = open(css.path).read()
        self.assertTrue(css_content.startswith(_ALREADY_PARSED_MARKER))
        logical_url = _LOGICAL_URL_TEMPLATE % '/media/producer/images/foobar.png'
        self.assertIn(logical_url, css_content)
        self.assertIsNotNone(re.search(r"\burl\('[^']*foobar[^']*png'\)", css_content))

    def test_abslute_url_image_before_css(self):
        image = self.create_file('foobar.png', self.producer_images)
        css = self.create_file('absolute_url_to_image.css', self.producer_css,
                               content="""\
.pledge-block {
    background: url('/media/producer/images/foobar.png');
}
""")
        self._verify_css_is_corectly_rewritten(css)

    def test_relative_url_image_before_css(self):
        image = self.create_file('foobar.png', self.producer_images)
        css = self.create_file('relative_url_to_image.css', self.producer_css,
                               content="""\
.pledge-block {
    background: url('../images/foobar.png');
}
""")
        self._verify_css_is_corectly_rewritten(css)

    def test_double_quoted_url(self):
        image = self.create_file('foobar.png', self.producer_images)
        css = self.create_file('relative_url_to_image.css', self.producer_css,
                               content="""\
.pledge-block {
    background: url(  " ../images/foobar.png " );
}
""")
        self._verify_css_is_corectly_rewritten(css)

    def test_unquoted_url(self):
        image = self.create_file('foobar.png', self.producer_images)
        css = self.create_file('relative_url_to_image.css', self.producer_css,
                               content="""\
.pledge-block {
    background: url(  ../images/foobar.png  );
}
""")
        self._verify_css_is_corectly_rewritten(css)

