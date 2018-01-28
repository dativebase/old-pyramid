#! /usr/bin/env bash
OLD_NAME_TESTS=${OLD_NAME_TESTS:-oldtests}
HERE="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
OLD_PERMANENT_STORE=${OLD_PERMANENT_STORE:-"${HERE}/test-store"}
OLD_NAME_TESTS=$OLD_NAME_TESTS \
OLD_PERMANENT_STORE=$OLD_PERMANENT_STORE \
    OLD_TESTING=1 \
    pytest old/tests/ -v
