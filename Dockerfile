FROM python:2.7

RUN set -x \
    && apt-get update \
    && apt-get install netcat --no-install-recommends -qqy \
    && wget -O /usr/bin/wait-for https://raw.githubusercontent.com/eficode/wait-for/828386460d138e418c31a1ebf87d9a40f5cedc32/wait-for \
    && chmod a+x /usr/bin/wait-for \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp*

RUN set -x && python -m pip install pyramid_sawing sentry-sdk

COPY . /src
WORKDIR /src

RUN set -x \
    && python -m pip install -r requirements/main.txt \
    && python -m pip install -r requirements/test.txt \
    && python -m pip install -r requirements/deploy.txt \
    && python -m pip install -e .

ENV PYRAMID_INI environ.ini
