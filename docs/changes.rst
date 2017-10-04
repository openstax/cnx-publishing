
.. Use the following to start a new version entry:

   |version|
   ----------------------

   - feature message

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
