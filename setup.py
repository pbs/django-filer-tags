#!/usr/bin/env python
import os
from setuptools import setup, find_packages

README_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                           'README.rst')

dependencies = [
    'django-filer>=0.9pbs,<0.9pbs.1000',
]

dependency_links = [
]

setup(
    name='django-filer-tags',
    version='1.3.1',
    description='Extra template filters and tags for filer',
    long_description=open(README_PATH, 'r').read(),
    author='Sever Banesiu',
    author_email='banesiu.sever@gmail.com',
    url='https://github.com/pbs/django-filer-tags',
    packages=find_packages(),
    include_package_data=True,
    install_requires=dependencies,
    dependency_links=dependency_links,
)
