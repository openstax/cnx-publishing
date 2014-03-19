# -*- coding: utf-8 -*-
from setuptools import setup, find_packages


install_requires = (
    'cnx-epub',
    'psycopg2',
    'pyramid',
    )
description = """\
Application for accepting publication requests to the Connexions Archive."""


setup(
    name='cnx-publishing',
    version='0.1',
    author='Connexions team',
    author_email='info@cnx.org',
    url="https://github.com/connexions/cnx-publishing",
    license='LGPL, See also LICENSE.txt',
    description=description,
    install_requires=install_requires,
    packages=find_packages(),
    include_package_data=True,
    entry_points="""\
    [paste.app_factory]
    main = cnxpublishing.main:main
    """,
    )
