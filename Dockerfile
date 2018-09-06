FROM python:2.7

COPY . /src
WORKDIR /src

RUN set -x \
  && python setup.py install \
  && pip install pyramid_sawing

ENV PYRAMID_INI environ.ini
