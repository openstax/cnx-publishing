.. Use the following to start a new version entry:

   |version|
   ----------------------

   - feature message

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
