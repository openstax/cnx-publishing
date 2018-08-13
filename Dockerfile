from python:2.7

copy . /code
workdir /code

run python setup.py install && \
  pip install pyramid_sawing

CMD pserve development.ini
