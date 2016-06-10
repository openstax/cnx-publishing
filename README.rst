.. Note that the reStructuredText (rst) 'note' directive is not used,
   because github does not style these in a way that makes them obvious.
   If this document is ever put into a sphinx scroll,
   therefore outside of the github readme,
   the adjustment should be made to make notes use the rst 'note' directive.

.. _cnx-epub: https://github.com/connexions/cnx-epub/
.. _cnx-authoring: https://github.com/connexions/cnx-authoring/

=============================
Connexions Publishing Service
=============================

.. image:: https://travis-ci.org/Connexions/cnx-publishing.svg
   :target: https://travis-ci.org/Connexions/cnx-publishing

.. image:: https://img.shields.io/codecov/c/github/Connexions/cnx-publishing.svg
  :target: https://codecov.io/gh/Connexions/cnx-publishing

Interface for:

- Accepting publication requests
- Previewing publication requests
- Submitting publications to the archive database
- Accepting or denying role requests
- Kicking off post-publication jobs
- Moderating publications for first time publishers

Getting started
---------------

Install using one of the following methods (run within the project root)::

    python setup.py install

Or::

    pip install .

Initialize the database with the archive and publishing schema using the
following command::

    cnx-db init -d cnxarchive -U cnxarchive

To run the project you can use the supplied script or configure it as a WSGI
application in your webserver.
::

    pserve <your-config>.ini

Here ``<your-config>.ini`` can be the ``development.ini`` in the project root.
The settings in this config are the same as the development settings used
by cnx-archive.

If you're using **cnx-authoring** together with **cnx-publishing**, please make sure
your development.ini use the **same openstax_accounts settings**.

Testing
-------

The tests require access to a blank database named ``cnxarchive-testing``
with the user ``cnxarchive`` and password ``cnxarchive``. This can easily
be created using the following commands::

    psql -c "CREATE USER cnxarchive WITH SUPERUSER PASSWORD 'cnxarchive';"
    createdb -O cnxarchive cnxarchive-testing

The tests can then be run using::

    python setup.py test

Permissions
-----------

**Note**: Permissions are assigned to users and groups via
``cnxpublishing.main.RootFactory``. See that class for details about
which permissions users/groups have in this application.

:view: Allows one to view content.
:publish: Allows one to publish content.
:preview: Allows one to view a publication's contents prior
    to persistence to archive.
:moderate: Allows one to moderate, accept or reject, a publication.

:publish.assign-acceptance: Allows one to assign user actions requests.
:publish.remove-acceptance: Allows one to remove user actions requests.
:publish.assign-acl: Allows one to assign access control on documents.
:publish.remove-acl: Allows one to remove access control on documents.
:publish.create-identifier: Allows one to create a content identifier.
    This is primarily used as a sub-permission on actions requests.
:publish.remove-identifier: Allows one to remove a content identifier.

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


API By Example
--------------


Internal versus external usage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The system is designed in a way that allows internal Connexions applications
to communicate with publishing in such a way that is both workflow effective
and less context redundant. In some parts of the code base you will see
this refered to as *trusted and untrustred* communication. That is a simple
way of saying, the apps that are run inside the Connexions network are
considered trusted. Trusted communications require the use of an API key.

An example *trusted app relationship* would be the communications
that happen between a cnx-authoring_ instance and publishing.

Examples that follow...
~~~~~~~~~~~~~~~~~~~~~~~

All the examples that follow use the following imports and base
variables::

    >>> import json
    >>> from pprint import pprint
    >>> import tempfile
    >>> import requests
    >>> import cnxepub

    # As configured in development.ini
    >>> api_key = 'dev'
    >>> base_url = 'http://localhost:6543'

Publishing content
~~~~~~~~~~~~~~~~~~

All publications take a single EPUB file formatted in the internal cnx-epub
format (See also the cnx-epub_ package), specifically it needs to be in
a publishing format, which contains a few required details.

The following is an example publication using some pre-build content::

    # The example content we will publish...
    >>> from cnxpublishing.tests.use_cases import EXAMPLE_BOOK

    # Set up the epub that will be submitted.
    >>> _, epub_filepath = tempfile.mkstemp('.publication.epub')
    >>> publisher = 'ream'
    >>> publication_message = 'Example publication'
    >>> with open(epub_filepath, 'wb') as epub:
    ...     cnxepub.make_publication_epub(EXAMPLE_BOOK, publisher,
    ...                                   publication_message, epub)

    # Send the book for publication.
    >>> url = "http://localhost:6543/publications"
    >>> file_payload = [
    ...     ('epub', ('book.publication.epub', open(epub_filepath, 'rb'),
    ...               'application/octet-stream',),)]
    >>> headers = {'x-api-key': api_key}
    >>> resp = requests.post(url, files=file_payload, headers=headers)
    >>> assert resp.status_code == 200, resp.status_code

    # The info returned from a successful POST looks something like this.
    >>> pprint(resp.json())
    {u'mapping': {u'07509e07-3732-45d9-a102-dd9a4dad5456': u'07509e07-3732-45d9-a102-dd9a4dad5456@1.1',
                  u'de73751b-7a14-4e59-acd9-ba66478e4710': u'de73751b-7a14-4e59-acd9-ba66478e4710@1'},
     u'messages': None,
     u'publication': 1,
     u'state': u'Waiting for acceptance'}

In trusted app relationships a *pre-publication* flag can be added to
the request. This flag is synonymous with a *dry-run* publication,
except that it does create active role and license acceptance requests.
The content will not be published even if all the information is verified
and all roles and licenors have accepted.

The response from publication creation will be one of three possiblities.
The first and already examined response is the 200 OK, which contains
the aforementioned JSON. Another option is a 403, which most likely
means their was a failure to authenticate either through the API key
or OpenStax Accounts. The other known possiblity is a 400 Bad Request,
which will only be raised if the payload isn't a valid Connexions EPUB.

Inspecting the publication
~~~~~~~~~~~~~~~~~~~~~~~~~~

After a publication has been created, the first response will be a set
of data. This information contains the identify for the publication,
the state of the publication and a mapping of content identifiers to
their final publication identifier.

The response JSON data of a publication POST is in the same
structure when making a GET request on the publication.

The structure is a single JSON object as follows:

:publication: An integer identifying the publication.
:state:  This value could be one of five values.
    ``Done/Success``, which means the publication has been committed
    to the archive.
    ``Publishing``, which indicates the process of committing.
    ``Processing`` is the default state on creation and generally signifies
    that the publication is being worked on.
    ``Waiting for acceptance`` is a blocking state that means that one
    or more roles and licensors on the content needs to accept the
    the role classification and/or license attributed to them
    on the content.
    ``Failed/Error`` is the end failing state. In the event that
    the failing state it reached, the ``messages`` value of the JSON will
    contain more detailed information about what failed.
:messages: Contains a array of JSON or null. If the publication experienced
    problems validating and/or analyzing any of the content, an error message
    will appear in the array.
:mapping: (Only available in the response to a POST.) The value is
    a mapping of content identifiers keyed by the identifiers
    sent in the epub to the final identifier, which includes id and version
    (a.k.a. ident-hash).

The base structure of error messages looks like this:

:code: An integer that is unique to a specific type of error. For example,
    error code 9 is a missing required metadata error.
:type: A string that represent the error's type. This is typically the
    name of the exception as it appears in the Python code.
:publication_id: The publication this exception belongs to.
    This is not particularly useful to those externally reading the data.
:epub_filename: The name of the document as it appears in the epub file.
    This is usually never supplied, unless the document cannot be read.
:pending_document_id: The identifier used internally by publishing
    that points to the pending document/binder.
    This is not particularly useful to those externally reading the data.
:pending_ident_hash: This is the identifier of the would be published content.
    One can reverse map this identifier to their own using the mapping
    in the publiation POST response.

Additional key value pairs are added to the error message based on type.
For example, a code 8 'NotAllowed' error would also contain
a ``uuid`` and it's value, where the value is the UUID of the would be
published content.

Adjusting publication permissions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As part of the intial publication, the publisher is entered into
the interal permissions system as having the publish permission
for the epub's content(s). Any additions need to be handled
via a separate API call.

We can take a look at the users that have permissions on a piece of
content using the ``/contents/{id}/permissions`` path. For example::

    >>> uuid = 'de73751b-7a14-4e59-acd9-ba66478e4710'
    >>> url = "{}/contents/{}/permissions".format(base_url, uuid)
    >>> resp = requests.get(url)
    >>> pprint(resp.json())
    [{u'permission': u'publish',
      u'uid': u'ream',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'}]

To give the user 'rings'
the publishing ability on a specific piece of content::

    >>> headers = {'x-api-key': api_key, 'content-type': 'application/json'}
    >>> data = [{'uid': 'rings', 'permission': 'publish'}]
    >>> resp = requests.post(url, headers=headers, data=json.dumps(data))
    >>> assert resp.status_code == 202
    >>> pprint(requests.get(url).json())
    [{u'permission': u'publish',
      u'uid': u'ream',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     {u'permission': u'publish',
      u'uid': u'rings',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'}]

And removal is the opposite of an addition. For example, to remove
publish permission for the user 'rings'::

    >>> resp = requests.delete(url, headers=headers, data=json.dumps(data))
    >>> assert resp.status_code == 200
    >>> pprint(requests.get(url).json())
    [{u'permission': u'publish',
      u'uid': u'ream',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'}]


Checking role and license acceptance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before any publication can be commited to the archive,
the attributed role(s) (e.g. author, illustrator, etc.) must be accepted.
Furthermore, all roles must accept the license.

Only trusted applications can dictate role and license acceptance,
but the viewing of the acceptance list is publically accessible.

To view the current roles and license acceptance use the
``/contents/{id}/roles`` and ``/contents/{id}/licensors``, respectively.

::

    >>> url = "{}/contents/{}/roles".format(base_url, uuid)
    >>> pprint(requests.get(url).json())
    [{u'has_accepted': None,
      u'role': u'Author',
      u'uid': u'charrose',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     {u'has_accepted': None,
      u'role': u'Illustrator',
      u'uid': u'frahablar',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     {u'has_accepted': None,
      u'role': u'Translator',
      u'uid': u'frahablar',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     ...]

    >>> url = "{}/contents/{}/licensors".format(base_url, uuid)
    >>> pprint(requests.get(url).json())
    {u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
     u'licensors': [{u'has_accepted': None,
       u'uid': u'charrose',
       u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
      {u'has_accepted': None,
       u'uid': u'frahablar',
       u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
      ...]}

Adjusting role and license acceptance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The same data format in the response to a GET for role and license
acceptance can be used to create and delete them.

To adjust and add a new role::

    >>> url = "{}/contents/{}/roles".format(base_url, uuid)
    >>> headers = {'x-api-key': api_key, 'content-type': 'application/json'}
    >>> data = [{'uid': 'charrose', 'role': 'Author', 'has_accepted': True}]
    >>> resp = requests.post(url, data=json.dumps(data), headers=headers)
    >>> assert resp.status_code == 202
    >>> pprint(requests.get(url).json())
    [{u'has_accepted': True,
      u'role': u'Author',
      u'uid': u'charrose',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     {u'has_accepted': None,
      u'role': u'Illustrator',
      u'uid': u'frahablar',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     {u'has_accepted': None,
      u'role': u'Translator',
      u'uid': u'frahablar',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     ...]

And deletion is very similar::

    >>> data = [{'uid': 'frahablar', 'role': 'Translator'}]
    >>> resp = requests.delete(url, data=json.dumps(data), headers=headers)
    >>> assert resp.status_code == 200
    >>> pprint(requests.get(url).json())
    [{u'has_accepted': True,
      u'role': u'Author',
      u'uid': u'charrose',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     {u'has_accepted': None,
      u'role': u'Illustrator',
      u'uid': u'frahablar',
      u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
     ...]

Manipulating license accept is very similar to role acceptance.
The only major differences are the wrapping JSON around the acceptances
(found in the ``licensors`` value) and the lack of a role in the acceptance
JSON values. Note, the ``license_url`` value is important, because if it
is changed, it will flush all the acceptances to an unknown state.
Here is an example of how this would look::

    >>> url = "{}/contents/{}/licensors".format(base_url, uuid)
    >>> headers = {'x-api-key': api_key, 'content-type': 'application/json'}
    >>> pprint(requests.get(url).json())
    {u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
     u'licensors': [{u'has_accepted': None,
       u'uid': u'charrose',
       u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
      {u'has_accepted': None,
       u'uid': u'frahablar',
       u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
      ...]}

    >>> data = {
    ...     'license_url': 'http://creativecommons.org/licenses/by/4.0/',
    ...     'licensors': [{'uid': 'frahablar', 'has_accepted': False}]}
    >>> resp = requests.post(url, data=json.dumps(data), headers=headers)
    >>> assert resp.status_code == 202
    >>> data = {'licensors': [{'uid': 'charrose'}]}
    >>> resp = requests.delete(url, data=json.dumps(data), headers=headers)
    >>> assert resp.status_code == 200
    >>> pprint(requests.get(url).json())
    {u'license_url': u'http://creativecommons.org/licenses/by/4.0/',
     u'licensors': [{u'has_accepted': False,
                     u'uid': u'frahablar',
                     u'uuid': u'de73751b-7a14-4e59-acd9-ba66478e4710'},
      ...]}

Creating identifiers on-the-fly
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Only trusted applications, those are applications run within the Connexions
network, are able to create identifiers on-the-fly. This simply means
that if content 'xyz123' doesn't exist at '/contents/xyz123', the application
can create a stub for it.

The roles and license accpetance routes as well as the permissions route can
create identifiers where one previously did not exist.

::

    >>> uuid = '7a268e3a-1e3a-4f4d-aaab-5ecd046187c1'
    >>> url = '{}/contents/{}/permissions'.format(base_url, uuid)
    >>> headers = {
    ...     'x-api-key': 'b07',  # b07 is a trusted app in development.ini
    ...     'content-type': 'application/json'}
    >>> assert requests.get(url).status_code == 404
    >>> data = [{'uid': 'impicky', 'permission': 'publish'}]
    >>> resp = requests.post(url, data=json.dumps(data), headers=headers)
    >>> assert resp.status_code == 202
    >>> pprint(requests.get(url).json())
    [{u'permission': u'publish',
      u'uid': u'impicky',
      u'uuid': u'7a268e3a-1e3a-4f4d-aaab-5ecd046187c1'}]

License
-------

This software is subject to the provisions of the GNU Affero General
Public License Version 3.0 (AGPL). See license.txt for details.
Copyright (c) 2013 Rice University
