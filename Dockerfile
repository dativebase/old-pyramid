FROM ubuntu:16.04

ENV DEBIAN_FRONTEND noninteractive
ENV PYTHONUNBUFFERED 1

RUN set -ex \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        apt-transport-https \
        curl \
        git \
        python-software-properties \
        software-properties-common \
        libldap2-dev \
        libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

# Install OS dependencies
RUN set -ex \
    && add-apt-repository "deb http://archive.ubuntu.com/ubuntu/ xenial multiverse" \
    && add-apt-repository "deb http://archive.ubuntu.com/ubuntu/ xenial-security universe" \
    && add-apt-repository "deb http://archive.ubuntu.com/ubuntu/ xenial-updates multiverse" \
    && add-apt-repository "ppa:jonathonf/ffmpeg-3" \
    && add-apt-repository "ppa:jonathonf/python-3.6" \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        python3.6 \
        python3.6-dev \
        libpython3-dev \
        python3-pip \
        python3.6-venv \
        python3-setuptools \
        ffmpeg \
        libavcodec-ffmpeg56 \
        imagemagick \
        libevent-dev \
        libjansson4 \
        libxml2-utils \
        md5deep \
        rsync \
        tree \
        uuid \
        supervisor \
        flex \
        sqlite3 \
        uwsgi \
        uwsgi-plugin-python \
        libtiff5-dev \
        libjpeg8-dev \
        zlib1g-dev \
        libmysqlcppconn-dev \
        libfreetype6-dev \
        liblcms2-dev \
        libreadline6 \
        libreadline6-dev \
        libwebp-dev \
        tcl8.6-dev \
        tk8.6-dev \
        python-tk \
        libmysqlclient-dev \
        mysql-client-5.7 \
        libmagic-dev \
        tesseract-ocr \
        libssl-dev \
        autoconf \
        automake \
        libtool \
        gfortran \
        autoconf-archive \
        g++ \
    && rm -rf /var/lib/apt/lists/*

# Install foma (FST)
RUN set -ex \
    && curl -L https://bitbucket.org/mhulden/foma/downloads/foma-0.9.18.tar.gz --output foma-0.9.18.tar.gz \
    && tar -xvzf foma-0.9.18.tar.gz \
    && cd foma-0.9.18 \
    && make \
    && make install \
    && cd .. \
    && rm -r foma-0.9.18*

# Install DRUtils (for Tgrep2)
RUN set -ex \
    && curl -L http://tedlab.mit.edu/~dr/DRUtils/drutils.tgz --output drutils.tgz \
    && tar -xvzf drutils.tgz \
    && cd DRUtils \
    && sed -i '/CC = gcc -Wall -O4 -march=i486/c\CC = gcc -Wall -O4' Makefile \
    && make \
    && cd .. \
    && rm drutils.tgz

# Install Tgrep2 (PS tree search)
RUN set -ex \
    && curl -L http://tedlab.mit.edu/~dr/Tgrep2/tgrep2.tgz --output tgrep2.tgz \
    && tar -xvzf tgrep2.tgz \
    && cd TGrep2 \
    && sed -i '/UTIL_DIR= ${HOME}\/DRUtils/c\UTIL_DIR= /DRUtils' Makefile \
    && make \
    && ln -s /TGrep2/tgrep2 /usr/local/sbin/tgrep2 \
    && cd .. \
    && rm tgrep2.tgz

# Install MITLM (LMs)
RUN set -ex \
    && git clone https://github.com/mitlm/mitlm.git \
    && cd mitlm \
    && ./autogen.sh \
    && ./configure \
    && make \
    && make install \
    && rm /usr/local/bin/estimate-ngram \
    && ln -s /mitlm/estimate-ngram /usr/local/bin/estimate-ngram

RUN python3.6 -m venv /venv
RUN /venv/bin/pip install --upgrade pip
RUN /venv/bin/pip install wheel
ADD requirements.txt /usr/src/old/requirements.txt
ADD requirements /usr/src/old/requirements
RUN /venv/bin/pip install -r /usr/src/old/requirements/test.txt

ADD old /usr/src/old/old
ADD config.ini /usr/src/old/config.ini
ADD serve.sh /usr/src/old/serve.sh
ADD setup.py /usr/src/old/setup.py
ADD test.sh /usr/src/old/test.sh
ADD README.rst /usr/src/old/README.rst
ADD CHANGES.txt /usr/src/old/CHANGES.txt
RUN /venv/bin/pip install -e /usr/src/old

WORKDIR /usr/src/old/
CMD ["/venv/bin/pserve", "config.ini", "http_port=8000", "http_host=0.0.0.0"]
