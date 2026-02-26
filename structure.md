├───alembic
│   │   env.py
│   │   README
│   │   script.py.mako
│   │
│   └───versions
├───deploy
│   │   compose.dev.yml
│   │
│   ├───docker
│   │       Dockerfile
│   │
│   └───k8s
├───scripts
│       seed_db.py
│
├───src
│   │   main.py
│   │
│   ├───api
│   │   │   server.py
│   │   │
│   │   ├───dependencies
│   │   │       auth.py
│   │   │       database.py
│   │   │       services.py
│   │   │
│   │   ├───exceptions
│   │   │       handlers.py
│   │   │
│   │   ├───middlewares
│   │   │       logger.py
│   │   │       request_id.py
│   │   │
│   │   └───v1
│   │       │
│   │       ├───admin
│   │       │       users.py
│   │       │
│   │       ├───auth
│   │       │       login.py
│   │       │
│   │       ├───client
│   │       └───courier
│   ├───common
│   │       pagination.py
│   │       repository.py
│   │       service.py
│   │       uow.py
│   │
│   ├───core
│   │   │   config.py
│   │   │   constants.py
│   │   │   context.py
│   │   │   exceptions.py
│   │   │   logger.py
│   │   │
│   │   └───security
│   │           jwt.py
│   │           password.py
│   │           permissions.py
│   │
│   ├───infrastructure
│   │   │
│   │   ├───cache
│   │   ├───clients
│   │   ├───database
│   │   │       base.py
│   │   │       session.py
│   │   │       uow.py
│   │   │
│   │   └───external
│   ├───modules
│   │   │
│   │   ├───auth
│   │   │       schemas.py
│   │   │       services.py
│   │   │
│   │   ├───catalog
│   │   │       models.py
│   │   │       repositories.py
│   │   │       schemas.py
│   │   │       services.py
│   │   │
│   │   ├───finances
│   │   │       enums.py
│   │   │       models.py
│   │   │       repositories.py
│   │   │       schemas.py
│   │   │       services.py
│   │   │
│   │   ├───logistics
│   │   │   │
│   │   │   ├───delivery
│   │   │   │       schemas.py
│   │   │   │       services.py
│   │   │   │
│   │   │   ├───inventory
│   │   │   │       enums.py
│   │   │   │       models.py
│   │   │   │       repositories.py
│   │   │   │       schemas.py
│   │   │   │       services.py
│   │   │   │
│   │   │   └───warehouse
│   │   │           enums.py
│   │   │           models.py
│   │   │           repositories.py
│   │   │           schemas.py
│   │   │           services.py
│   │   │
│   │   ├───orders
│   │   │       enums.py
│   │   │       models.py
│   │   │       repositories.py
│   │   │       schemas.py
│   │   │       services.py
│   │   │
│   │   └───users
│   │           events.py
│   │           exceptions.py
│   │           models.py
│   │           repositories.py
│   │           schemas.py
│   │           services.py
│   │
│   └───workers
└───tests
    │   conftest.py
    │
    ├───factories
    ├───integration
    └───unit