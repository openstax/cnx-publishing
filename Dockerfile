FROM python:2.7

RUN set -x && python -m pip install pyramid_sawing sentry-sdk

COPY . /src
WORKDIR /src

RUN set -x \
    && python -m pip install -e ".[test]"

ENV PYRAMID_INI environ.ini
