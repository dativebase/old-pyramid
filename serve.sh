#! /usr/bin/env bash
HOST=${OLD_HOST:-0.0.0.0}
PORT=${OLD_PORT:-6543}
pserve config.ini http_port=$PORT host=$HOST "$@"
