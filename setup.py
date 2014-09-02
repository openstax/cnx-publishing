# -*- coding: utf-8 -*-
import sys
from setuptools import setup, find_packages


IS_PY3 = sys.version_info > (3,)

install_requires = (
    'cnx-archive',
    'cnx-epub',
    'openstax-accounts>=0.8',
    'psycopg2',
    'pyramid>=1.5',
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
    tests_require.append('mock')

setup(
    name='cnx-publishing',
    version='0.1',
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
        'cnxpublishing': ['sql/*.sql', 'sql/*/*.sql'],
        },
    entry_points="""\
    [paste.app_factory]
    main = cnxpublishing.main:main
    [console_scripts]
    cnx-publishing-initdb = cnxpublishing.scripts.initdb:main
    """,
    )
