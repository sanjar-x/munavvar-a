➜ munavvar-a git:(main) ✗ tree
.
├── Makefile
├── README.md
├── alembic
│   ├── README
│   ├── env.py
│   ├── script.py.mako
│   └── versions
│   ├── 7a064788cae7_add_username_to_users.py
│   ├── aec319431748_add_new_models_and_columns.py
│   ├── cf2a824cf0fb_add_missing_fkey_indexes.py
│   └── e314edc17991_init.py
├── alembic.ini
├── deploy
│   ├── compose.db.yml
│   ├── compose.dev.yml
│   ├── docker
│   │   ├── Dockerfile
│   │   └── Dockerfile.railway
│   └── k8s
├── pyproject.toml
├── railway.toml
├── scripts
│   └── entrypoint.sh
├── src
│   ├── **init**.py
│   ├── api
│   │   ├── **init**.py
│   │   ├── exceptions
│   │   │   ├── **init**.py
│   │   │   └── handlers.py
│   │   ├── middlewares
│   │   │   ├── logger.py
│   │   │   └── request_id.py
│   │   ├── server.py
│   │   └── v1
│   │   ├── **init**.py
│   │   ├── auth
│   │   │   ├── **init**.py
│   │   │   ├── login.py
│   │   │   └── register.py
│   │   ├── backoffice
│   │   │   ├── **init**.py
│   │   │   ├── catalog.py
│   │   │   ├── clients.py
│   │   │   ├── couriers.py
│   │   │   ├── finances.py
│   │   │   ├── inventory.py
│   │   │   ├── orders.py
│   │   │   ├── profile.py
│   │   │   └── users.py
│   │   ├── client
│   │   │   ├── **init**.py
│   │   │   ├── catalog.py
│   │   │   ├── login.py
│   │   │   ├── orders.py
│   │   │   └── profile.py
│   │   └── courier
│   │   ├── **init**.py
│   │   ├── catalog.py
│   │   ├── orders.py
│   │   └── profile.py
│   ├── application
│   │   ├── **init**.py
│   │   ├── client
│   │   │   ├── **init**.py
│   │   │   ├── dependencies.py
│   │   │   ├── exceptions.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── uow.py
│   │   ├── courier
│   │   │   ├── **init**.py
│   │   │   ├── dependencies.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── uow.py
│   │   ├── inventories
│   │   │   ├── **init**.py
│   │   │   ├── dependencies.py
│   │   │   ├── exceptions.py
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── uow.py
│   │   └── order
│   │   ├── **init**.py
│   │   ├── dependencies.py
│   │   ├── service.py
│   │   └── uow.py
│   ├── common
│   │   ├── **init**.py
│   │   ├── pagination.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   └── uow.py
│   ├── core
│   │   ├── **init**.py
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── context.py
│   │   ├── exceptions.py
│   │   ├── init.py
│   │   ├── logger.py
│   │   └── security
│   │   ├── **init**.py
│   │   ├── jwt.py
│   │   ├── password.py
│   │   └── permissions.py
│   ├── infrastructure
│   │   ├── **init**.py
│   │   ├── cache
│   │   ├── clients
│   │   ├── database
│   │   │   ├── **init**.py
│   │   │   ├── base.py
│   │   │   ├── models.py
│   │   │   ├── session.py
│   │   │   └── uow.py
│   │   └── external
│   ├── main.py
│   ├── modules
│   │   ├── **init**.py
│   │   ├── auth
│   │   │   ├── **init**.py
│   │   │   ├── dependencies.py
│   │   │   ├── schemas.py
│   │   │   └── services.py
│   │   ├── catalog
│   │   │   ├── **init**.py
│   │   │   ├── dependencies.py
│   │   │   ├── enums.py
│   │   │   ├── exceptions.py
│   │   │   ├── models.py
│   │   │   ├── repositories.py
│   │   │   ├── schemas.py
│   │   │   ├── services.py
│   │   │   └── uow.py
│   │   ├── finances
│   │   │   ├── **init**.py
│   │   │   ├── dependencies.py
│   │   │   ├── enums.py
│   │   │   ├── exceptions.py
│   │   │   ├── models.py
│   │   │   ├── repositories.py
│   │   │   ├── schemas.py
│   │   │   ├── services.py
│   │   │   └── uow.py
│   │   ├── inventory
│   │   │   ├── **init**.py
│   │   │   ├── dependencies.py
│   │   │   ├── enums.py
│   │   │   ├── exceptions.py
│   │   │   ├── models.py
│   │   │   ├── repositories.py
│   │   │   ├── schemas.py
│   │   │   ├── services.py
│   │   │   └── uow.py
│   │   ├── orders
│   │   │   ├── **init**.py
│   │   │   ├── dependencies.py
│   │   │   ├── enums.py
│   │   │   ├── exceptions.py
│   │   │   ├── models.py
│   │   │   ├── repositories.py
│   │   │   ├── schemas.py
│   │   │   ├── services.py
│   │   │   └── uow.py
│   │   └── users
│   │   ├── **init**.py
│   │   ├── dependencies.py
│   │   ├── events.py
│   │   ├── exceptions.py
│   │   ├── models.py
│   │   ├── queries.py
│   │   ├── repositories.py
│   │   ├── schemas.py
│   │   ├── services.py
│   │   └── uow.py
│   └── workers
├── structure.md
├── tests
│   ├── conftest.py
│   ├── data copy.json
│   ├── data.json
│   ├── factories
│   ├── integration
│   ├── unit
│   └── еуче.txt
└── uv.lock

41 directories, 148 files
➜ munavvar-a git:(main) ✗
