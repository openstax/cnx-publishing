# -*- coding: utf-8 -*-
import os
import versioneer
from setuptools import setup, find_packages


here = os.path.abspath(os.path.dirname(__file__))


def read_from_requirements_txt(filepath):
    f = os.path.join(here, filepath)
    with open(f) as fb:
        return tuple([x.strip() for x in fb if not x.strip().startswith('#')])


install_requires = read_from_requirements_txt('requirements/main.txt')
tests_require = read_from_requirements_txt('requirements/test.txt')
extras_require = {
    'test': tests_require,
}

description = """\
Application for accepting publication requests to the Connexions Archive."""


setup(
    name='cnx-publishing',
    version=versioneer.get_version(),
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
        'cnxpublishing': ['sql/*.sql', 'sql/*/*.sql',
                          'views/templates/*.*',
                          'static/css/*.*',
                          'static/js/*.*',
                          'static/js/vendor/*.*',
                          ],
        'cnxpublishing.tests': ['data/*.*'],
    },
    cmdclass=versioneer.get_cmdclass(),
    entry_points="""\
    [paste.app_factory]
    main = cnxpublishing.main:make_wsgi_app
    [console_scripts]
    cnx-publishing-channel-processing = \
        cnxpublishing.scripts.channel_processing:main
    [dbmigrator]
    migrations_directory = cnxpublishing.main:find_migrations_directory
    """,
)
