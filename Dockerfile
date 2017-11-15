FROM python:3.6.3-alpine3.6

RUN apk update
RUN apk add build-base python-dev py-pip jpeg-dev zlib-dev
ENV LIBRARY_PATH=/lib:/usr/lib

ADD requirements.txt /usr/src/old/requirements.txt
ADD requirements /usr/src/old/requirements
RUN pip install -r /usr/src/old/requirements/test.txt

ADD . /usr/src/old/
RUN rm /usr/src/old/old.sqlite
RUN pip install -e /usr/src/old/

RUN initialize_old_db /usr/src/old/development.ini

WORKDIR /usr/src/old
ENTRYPOINT pserve development.ini
