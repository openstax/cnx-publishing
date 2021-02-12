0.17.27
------

- Dependency update including cnx-archive dependencies (`#360 <https://github.com/openstax/cnx-publishing/pull/360>`_)


0.17.26
------

- Dependency update including cnx-archive dependencies (`#353 <https://github.com/openstax/cnx-publishing/pull/353>`_)


0.17.25
------

- Dependency update including cnx-archive dependencies (`#348 <https://github.com/openstax/cnx-publishing/pull/348>`_)


0.17.24
------

- Dependency update including cnx-archive dependencies (`#345 <https://github.com/openstax/cnx-publishing/pull/345>`_)

0.17.23
------

- Dependency update including cnx-archive dependencies (#343)

0.17.22
------

- Dependency update including cnx-archive dependencies (#342)

0.17.21
------

- Dependency update including cnx-archive dependencies (#340)

0.17.20
------

- Dependency update including cnx-archive dependencies (#338)
- Add pyup: update no pragma to amqp (#336)

0.17.19
------

- Dependency update including cnx-archive dependencies (#334)


0.17.18
------

- Dependency update including cnx-archive dependencies (#331)


0.17.16
------

- Dependency update including cnx-archive dependencies

0.17.15
------

- Dependency update including cnx-archive dependencies

0.17.14
------

- Update cnx-epub

0.17.13
------

- Update cnxmlutils to 2.0

0.17.12
------

- Update cnx common and archive dependency versions (#318)

0.17.11
------

- Update cnx common and archive dependency versions (#316)

0.17.10
------

- Update cnx-common, cnx-epub, lxml pins (#314)

0.17.9
------

- Scheduled weekly dependency update for week 16 (#311)

0.17.8
------

- Scheduled weekly dependency update for week 14 (#308)
- added pyup.yml config file so that individual PRs aren't made for each dependency update (#307)

0.17.7
------

- upgraded cnx-db from 3.5.2 to 3.5.3 (#273)

0.17.6
------

- Bump waitress from 1.4.2 to 1.4.3 in /requirements (#270)
- Extra logging, add soft + hard timeout to baking task (#271)
- Bump urllib3 for security fix (#272)

0.17.5
------

- Unrestrict recipes dependency (#269)

0.17.4
------

- Update waitress dependency to 1.4.2 (#268)

0.17.3
______

- Update dependency versions of cnx-epub and waitress to 0.21.0 and 1.4.2, respectively

0.17.1
------

- Change docker-compose db to build from github master
- Add check for pypi release errors
- Remove upload pypi step in Jenkinsfile
- Remove `<4.1.0` restriction for pytest in requirements/test.txt (#261)
- Bypass celery error when queueing books for post publication (#260)

0.17.0
------

- Generate the content slug during the persistence of baked content
  to the database (#255)

  - Supply slug values when inserting the baked tree
  - Add utility func to amend the tree with slug values
  - Add the slug value during tree insertion
  - Fix tests associated with cnx-db tree_to_json changes

0.16.4
------

- Use requirements.txt files for dependencies
- Add base Makefile to the project
- Run tests on Travis-CI the same as one would run them in development (#…
- Remove redundant mention of the cnx-epub dependency
- Filter out invalid requirements that start with # or -
- Build the container from the requirement/*.txt files

0.16.3
------

- Fix admin view template paths after previous changes refactored the admin
  views into individual modules (#251)

0.16.2
------

- Re-release 0.16.0, which fixes CI tooling to release this package

0.16.1
------

- Re-release 0.16.0, which contained Python modules from previous versions.

0.16.0
------

- Remove the unused post-publications view (#250)

0.15.1
------

- Fix tests to use <body> when creating cnxepub.Document to correct
  adjustment made in cnx-epub
- Fix to explicitly install cnx-epub with collation support in the container setup
- Refactor admin views (split into sub-modules)
- Fix ImportError for ident-hash functionality

0.15.0
------

- Add a config INI that uses environment variables (#234)
- Comment out assertion for testing postgres notifications count (#238)
- Correct errors due to cnx-epub changes
- Rename cssselect2 to cnx-cssselect2
- Add Sentry integration for exception tracking (#243)
- Avoid double encoding when publishing content. This is in
  association with ``cnx-epub>=0.15.3`` (#244)

0.14.0
------

- Set Cache-Control headers (#235)

0.13.0
------

- Update README to fix installation documentation.
- Add 'fallback' state to the content-status (GOB) dashboard. This indicates
  when the content has failed to bake with the newest version and will fallback
  to the previous version.
  See https://github.com/Connexions/cnx-publishing/issues/224

0.12.0
------

- Fetch exercises by nickname when baking (#221)

0.11.1
------

- Bugfix for content-status admin page - show one, oldest recipe version

0.11.0
------

- Remove celery ``AsyncResult`` calls from the content-status view because
  they were causing performance issues. (#212, #213)
- Add the concept of a 'fallback' state for baked content (#211, #214, #215)

0.10.0
------

- Fix link to display None for print-styles without a recipe (#209 & #210)
- Add print style view recipe information. (#201)
- Add ability to unbake even in the presence of previous succcessful bake.
  (#204)
- Change config files db settings to use postgresql:// urls. (#203)

0.9.5
-----

- Fix distribution to include static files for the admin interface. (#205)

0.9.4
-----

- Expose STARTED state for baking on content status view (#191)
- Enable filter for QUEUED state (#193)
- Improve appearance of content status view
- Track time of baking (#194)

0.9.3
-----

- Explicitly close all psycopg2 db connections (#187)
- Refactor and fix content-status view (#186)

0.9.2
-----

- Check for a traceback when handling a celery task failure (#185)

0.9.1
-----

- Make sure to reserve uuids for new composite content (#184)

0.9.0
-----

- Use default icon for unknown states on content-status page (#182)
- Fix to not error when no recipe is found (#180)
- Optimize post publishing queue (#175)
- Reword baking procedure log messages (#174)
- Fix to add view templates to the package distribution (#169)
- Allow content status pages to be publicly visible (#171)
- Add views to view and inspect the content publication status (#161)
- Add a workaround an issue with celery tests, which allows us
  to unskip them (#170)
- Fix tests by adding an empty ruleset file
- Fix tests for change in bake() function signature
- Fix to fetch recipe text durning baking
- Use print-style to select recipe and fallback (#162)
- Add admin page for managing site banner messages (#163)

0.8.1
-----

- Check for a traceback when handling a celery task failure (#185)

0.8.0
-----

- Raise not found on an invalid ident-hash
- Require a specific version on rebake request
- Remove needless epub building on rebake request
- Add rough documentation for channel processing and the celery worker
- Use a celery task for the baking process
- Include celery in the app
- Rewrite subscriber tests using pytest methods
- Assign the most recent version at interp-time
- Clear database on first test run
- Add channel_processing.channels config setting to dev config
- Use memcache the same way as archive
- Remove unused imports
- Move the cache manager to its own module
- Rename file-upload-limit setting to file_upload_limit
- Move configuration to the config module and sub includemes
- Rename the main function to be more specific
- Rewrite post-publication as a general purpose channel processing utility
- Make bake function application aware
- Use memcache server for exercises and math conversion
- Rename collate terminology to baking terminology


0.7.0
-----

- Fix dependency definition for cnx-epub, so that it pulls in cnx-easybake
- Add the ability to publish and bake Composite Chapters
- Install versioneer for version management via git
- Convert SQL stements to use ident_hash and module_version SQL functions
- Use cnx-db init and remove cnx-publishing-initdb
- Move schema to cnx-db and use it as the database schema definition library
- Use notification for view based baking
- Provide token and mathmlcloud URL in configuration logic
- Add error handling and interface for post-publication tasks
- Add post-publication worker
- Fix republishing of binders with trees latest flag set to null
- Add ability to re-run baking procedure
- Persist Binder resources during publish
- Fix baking's resulting object

0.0.0
-----

- Initialized project
