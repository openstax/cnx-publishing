.. Note that the reStructuredText (rst) 'note' directive is not used,
   because github does not style these in a way that makes them obvious.
   If this document is ever put into a sphinx scroll,
   therefore outside of the github readme,
   the adjustment should be made to make notes use the rst 'note' directive.

=============================
Connexions Publishing Service
=============================

Interface for:

- Accepting publication requests
- Previewing publication requests
- Submitting publications to the archive database
- Accepting or denying role requests
- Kicking off post-publication jobs 

Getting started
---------------

Install using one of the following methods (run within the project root)::

    python setup.py install

Or::

    pip install .

If you haven't done so already, you will need to initialize an archive
database. This can be done using the following command::

    cnx-archive-initdb <your-config>.ini

Then you'll need to add the publishing schema to an existing
cnx-archive database::

    cnx-publishing-initdb <your-config>.ini

Here ``<your-config>.ini`` can be the ``development.ini`` in the project root.
The settings in this config are the same as the development settings used
by cnx-archive.

To run the project you can use the supplied script or configure it as a WSGI
application in your webserver.
::

    pserve <your-config>.ini

Testing
-------

.. image:: https://travis-ci.org/Connexions/cnx-publishing.svg?branch=acceptance-2
   :target: https://travis-ci.org/Connexions/cnx-publishing

::

    python setup.py test

HTTP API
--------

:/contents/{ident_hash}: Location of existing and pending documents.
                         If the document is pending publication, the response
                         will contain information about its publication state.

:/resources/{hash}: Location of existing and pending resources.

:/contents/{uuid}/licensors: Retrieve a list of users that have a license
                             request for this content. This includes those
                             That have also previously accepted.
                             Applications can post to this url in order
                             to create license requests.

:/contents/{uuid}/roles: Retrieve a list of users that have a role request
                         for this content. This includes those that have
                         previously accepted.
                         Applications can post to this url in order
                         to create role requests.

:/contents/{uuid}/permissions: Retrieve a list of users that have a permission
                               to publish this content.
                               Applications can post to this url in order
                               to create additional permission entries.

:/publications: Accepts EPUB files for publication into a *Connexions Archive*.
                Returns a mapping of identifiers, keyed by the identifiers given
                in the EPUB with values that identify where the content will be
                published.

:/publications/{id}: Poll and poke the state of the publication. #main API point

:/publications/{id}/license-acceptances/{uid}: Route for retrieving and posting
    information about a particular user's license acceptance. Only the user
    at ``uid`` can get and post information to on this route.

:/publications/{id}/role-acceptances/{uid}: Route for retrieving and posting
    role acceptance information. Only the user at ``uid`` can get and post
    information to on this route.


License
-------

This software is subject to the provisions of the GNU Affero General
Public License Version 3.0 (AGPL). See license.txt for details.
Copyright (c) 2013 Rice University
