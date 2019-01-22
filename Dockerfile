FROM python:2.7

RUN set -x && python -m pip install pyramid_sawing sentry-sdk

COPY . /src
WORKDIR /src

RUN set -x \
    && python -m pip install -r requirements/main.txt \
    && python -m pip install -r requirements/test.txt \
    && python -m pip install -r requirements/deploy.txt \
    && python -m pip install -e .

ENV PYRAMID_INI environ.ini
