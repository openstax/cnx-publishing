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

:/publications: Accepts EPUB files for publication into a *Connexions Archive*.
                Returns a mapping of identifiers, keyed by the identifiers given
                in the EPUB with values that identify where the content will be
                published.

:/publications/{id}: Poll and poke the state of the publication.

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
