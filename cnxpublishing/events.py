# -*- coding: utf-8 -*-
import json


class ChannelProcessingStartUpEvent(object):
    """An event triggered during channel processing process start up."""


class PGNotifyEvent(object):
    """A base class for a Postgres Notification Event"""

    def __init__(self, notification):
        self._payload = None
        self.notification = notification
        self.channel = notification.channel
        self.payload = notification.payload
        self.pid = notification.pid

    @property
    def payload(self):
        return self._payload

    @payload.setter
    def payload(self, value):
        # It's assumed that all payloads will be in JSON format.
        try:
            self._payload = json.loads(value)
        except (ValueError, TypeError,) as exc:
            if ('No JSON object' in exc.message or
                    'expected string or buffer' in exc.message):
                self._payload = {}
            else:
                raise


class PostPublicationEvent(PGNotifyEvent):
    """Notifications coming from the 'post_publication' Postgres channel."""

    @property
    def module_ident(self):
        return self._payload['module_ident']

    @property
    def ident_hash(self):
        return self._payload['ident_hash']

    @property
    def timestamp(self):
        return self._payload['timestamp']

    def __repr__(self):  # pragma: no cover
        name = type(self).__class__.__name__
        props = []
        for x in ['module_ident', 'ident_hash', 'timestamp']:
            props.append("{}={}".format(x, getattr(self, x)))
        return "<{} {{{}}}>".format(name, ', '.join(props))


# TODO grok all decendents of PGNotifyEvent into a named utility listing.
#      Thus replacing the need for this mapping.
_CHANNEL_MAPPER = {
    'post_publication': PostPublicationEvent,
    None: PGNotifyEvent,
}


def create_pg_notify_event(notif):
    """A factory for creating a Postgres Notification Event
    (an object inheriting from `cnxpublishing.events.PGNotifyEvent`)
    given `notif`, a `psycopg2.extensions.Notify` object.

    """
    # TODO Lookup registered events via getAllUtilitiesRegisteredFor
    #      for class mapping.
    if notif.channel not in _CHANNEL_MAPPER:
        cls = _CHANNEL_MAPPER[None]
    else:
        cls = _CHANNEL_MAPPER[notif.channel]
    return cls(notif)


__all__ = (
    'create_pg_notify_event',
    'ChannelProcessingStartUpEvent',
    'PGNotifyEvent',
    'PostPublicationEvent',
)
