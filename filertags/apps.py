from django.apps import AppConfig


class FilerTagsConfig(AppConfig):

    name = 'filertags'
    verbose_name = 'Django Filer TemplateTags'

    def ready(self):
        import filertags.signals