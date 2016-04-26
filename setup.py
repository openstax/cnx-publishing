# -*- coding: utf-8 -*-
import sys
from setuptools import setup, find_packages


IS_PY3 = sys.version_info > (3,)

install_requires = (
    'beaker',
    'cnx-archive',
    'cnx-epub',
    'jinja2',
    'openstax-accounts>=1.0.0',
    'psycopg2',
    'pyramid>=1.5',
    'pyramid_jinja2',
    'pyramid_multiauth',
    )
tests_require = [
    'webtest',
    ]
extras_require = {
    'test': tests_require,
    }
description = """\
Application for accepting publication requests to the Connexions Archive."""

if not IS_PY3:
    tests_require.append('mock==1.0.1')

setup(
    name='cnx-publishing',
    version='0.6.0',
    author='Connexions team',
    author_email='info@cnx.org',
    url="https://github.com/connexions/cnx-publishing",
    license='LGPL, See also LICENSE.txt',
    description=description,
    install_requires=install_requires,
    tests_require=tests_require,
    extras_require=extras_require,
    test_suite='cnxpublishing.tests',
    packages=find_packages(),
    include_package_data=True,
    package_data={
        'cnxpublishing': ['sql/*.sql', 'sql/*/*.sql', 'templates/*.*'],
        'cnxpublishing.tests': ['data/*.*'],
        },
    entry_points="""\
    [paste.app_factory]
    main = cnxpublishing.main:main
    [console_scripts]
    cnx-publishing-initdb = cnxpublishing.scripts.initdb:main
    [dbmigrator]
    migrations_directory = cnxpublishing.main:find_migrations_directory
    """,
    )
