FROM python:2.7

RUN set -x && python -m pip install pyramid_sawing sentry-sdk

COPY . /src
WORKDIR /src

RUN set -x \
    # FIXME: pip still has an issue with dependencies that have requirement
    # extras. It understands the requirement but drops the extras part.
    && python -m pip install "cnx-epub[collation]" \
    && python -m pip install -e ".[test]"

ENV PYRAMID_INI environ.ini
