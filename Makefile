# Paths for Docker named volumes
OLD_STORE_DATA ?= /tmp/old-store-data

create-volumes:  ## Create external data volumes.
	mkdir -p ${OLD_STORE_DATA}
	docker volume create \
		--opt type=none \
		--opt o=bind \
		--opt device=$(OLD_STORE_DATA) \
			old-store-data

bootstrap: bootstrap-old  ## Full bootstrap.

bootstrap-old:  ## Boostrap OLD (new database).
	docker-compose exec mysql mysql -hlocalhost -uroot -p12345 -e "\
		DROP DATABASE IF EXISTS olddev; \
		CREATE DATABASE oldtests DEFAULT CHARACTER SET utf8 DEFAULT COLLATE utf8_bin; \
		GRANT ALL PRIVILEGES ON olddev.* TO 'old'@'%' IDENTIFIED BY 'demo'"
	docker-compose run \
		--rm \
		--entrypoint initialize_old_db /usr/src/old/config-env.ini \
		old
	docker-compose run \
		--rm \
		--workdir /usr/src/old \
		--entrypoint pserve config-env.ini \
		old

restart-old:  ## Restart OLD
	docker-compose restart old

db:  ## Connect to the MySQL server using the CLI.
	mysql -h127.0.0.1 --port=62001 -uroot -p12345

test-all: test-old  ## Run all tests.

test-old:  ## Run OLD tests.
	docker-compose run \
		--workdir /usr/src/old \
		--rm \
		--entrypoint=pytest /usr/src/old/old/tests/ -v

test-sqlite-part:  ## Run a particular test in a SQLite testing environment.
	OLD_NAME_TESTS=oldtests \
		OLD_PERMANENT_STORE=test-store \
		OLD_TESTING=1 \
		OLD_DB_RDBMS=sqlite \
		OLD_SESSION_TYPE=file \
		SMTP_SERVER_ABSENT=1 \
		pytest $(part) -v -s -x

test-readonly:  ## Run tests for read-only mode
	OLD_NAME_TESTS=oldtests \
		OLD_PERMANENT_STORE=test-store \
		OLD_TESTING=1 \
		OLD_READONLY=1 \
		OLD_DB_RDBMS=sqlite \
		OLD_SESSION_TYPE=file \
		SMTP_SERVER_ABSENT=1 \
		pytest old/tests/functional/test_readonly_mode.py::TestReadonlyMode::test_readonly_mode -v -s -x

help:  ## Print this help message.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'


.DEFAULT_GOAL := help
