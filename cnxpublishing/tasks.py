# -*- coding: utf-8 -*-
"""\
Implementation of the Celery framework within a Pyramid application.

Use the ``task`` decorator provided by this module where the celery
documentation says to use ``@app.task``. It is used to register a function as
a task without making the celery application a global object.

"""
from __future__ import absolute_import

import celery
import venusian
from kombu import Queue
from pyramid.scripting import prepare


class PyramidAwareTask(celery.Task):
    """A Pyramid aware version of ``celery.task.Task``.
    This sets up the pyramid application within the thread, thus allowing
    ``pyramid.threadlocal`` functions to work as expected.

    """

    def __call__(self, *args, **kwargs):
        # Prepare the pyramid environment.
        if 'pyramid_config' in self.app.conf:
            pyramid_config = self.app.conf['pyramid_config']
            env = prepare(registry=pyramid_config.registry)  # noqa
        # Now run the original...
        return super(PyramidAwareTask, self).__call__(*args, **kwargs)


def task(**kwargs):
    """A function task decorator used in place of ``@celery_app.task``."""

    def wrapper(wrapped):

        def callback(scanner, name, obj):
            celery_app = scanner.config.registry.celery_app
            celery_app.task(**kwargs)(obj)

        venusian.attach(wrapped, callback)
        return wrapped

    return wrapper


def _make_celery_app(config):
    """This exposes the celery app. The app is actually created as part
    of the configuration. However, this does make the celery app functional
    as a stand-alone celery application.

    This puts the pyramid configuration object on the celery app to be
    used for making the registry available to tasks running inside the
    celery worker process pool. See ``CustomTask.__call__``.

    """
    # Tack the pyramid config on the celery app for later use.
    config.registry.celery_app.conf['pyramid_config'] = config
    return config.registry.celery_app


def includeme(config):
    settings = config.registry.settings

    config.registry.celery_app = celery.Celery('tasks')

    config.registry.celery_app.conf.update(
        broker_url=settings['celery.broker'],
        result_backend=settings['celery.backend'],
        result_persistent=True,
        task_track_started=True,
        task_default_queue='default',
        task_queues=(
            Queue('default'),
            Queue('deferred'),
        ),
    )

    # Override the existing Task class.
    config.registry.celery_app.Task = PyramidAwareTask

    # Set the default celery app so that the AsyncResult class is able
    # to assume the celery backend.
    config.registry.celery_app.set_default()

    # Initialize celery database tables early
    from celery.backends.database.session import SessionManager
    session = SessionManager()
    engine = session.get_engine(config.registry.celery_app.backend.url)
    session.prepare_models(engine)

    config.add_directive('make_celery_app', _make_celery_app)
