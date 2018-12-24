FROM python:2.7

RUN set -x && python -m pip install pyramid_sawing

COPY . /src
WORKDIR /src

RUN set -x \
    && python -m pip install -e ".[test]"
# FIXME: pip doesn't install the collation parts of cnx-epub (i.e. `cnx-epub[collation]`)???
# FIXME: Can we get a release of cssselect2 that doesn't collide with upstream?
RUN set -x \
    && python -m pip install "cnx-epub[collation]" \
    && python -m pip uninstall -y cssselect2 \
    && python -m pip install "git+https://github.com/Connexions/cssselect2.git#egg=cssselect2"

ENV PYRAMID_INI environ.ini
