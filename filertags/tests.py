import os

from django.core.files import File as DjangoFile
from django.test import TestCase

from filer.models.foldermodels import Folder
from filer.models.imagemodels import Image
from filer.models.filemodels import File

from filer.tests.helpers import (create_superuser, create_folder_structure,
                                 create_image, create_clipboard_item)

from filertags.signals import _ALREADY_PARSED_MARKER


class CssResourceUrlResolvingTest(TestCase):

    def setUp(self):
        self.superuser = create_superuser()
        self.client.login(username='admin', password='secret')
        self.image = create_image()
        self.image_name = 'test_file.jpg'
        self.image_filename = os.path.join(
            os.path.dirname(__file__), 'test_resources', self.image_name)
        self.image.save(self.image_filename, 'JPEG')
        self.resource_folder = Folder.objects.create(
            owner=self.superuser,
            name='css_resources_test')
        self.css_folder = Folder.objects.create(
            owner=self.superuser,
            name='css',
            parent=self.resource_folder)
        self.images_folder = Folder.objects.create(
            owner=self.superuser,
            name='images',
            parent=self.resource_folder)
        image_file_obj = DjangoFile(open(self.image_filename), name=self.image_name)
        filer_image = Image(
            owner=self.superuser,
            original_filename=self.image_name,
            folder=self.images_folder,
            file=image_file_obj)
        filer_image.save()

    def test_resolve_urls_quoted(self):
        css_content = """
.bgimage-single-quotes {
    background:#CCCCCC url( '../images/test_file.jpg' ) no-repeat center center;
    background-color: black;
}
"""
        css_path = os.path.join(os.path.dirname(__file__),
                                'test_resources', 'resources.css')
        with open(css_path, 'w') as f:
            f.write(css_content)
        css_file_obj = DjangoFile(open(css_path), name='resources.css')
        filer_css = File(owner=self.superuser,
                         original_filename='resources.css',
                         folder=self.css_folder,
                         file=css_file_obj)
        filer_css.save()
        with open(filer_css.path) as f:
            new_content = f.read()
            self.assertTrue(new_content.startswith(_ALREADY_PARSED_MARKER))
