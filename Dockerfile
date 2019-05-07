FROM python:2.7

RUN set -x && python -m pip install pyramid_sawing sentry-sdk

COPY . /src
WORKDIR /src

RUN set -x \
    && python -m pip install \
       -r requirements/main.txt \
       -r requirements/test.txt \
       -r requirements/docs.txt \
       -r requirements/lint.txt \
    && python -m pip install -e .

ENV PYRAMID_INI environ.ini
