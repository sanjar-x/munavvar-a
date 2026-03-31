# Code Review: Безопасность и аутентификация

## Краткая оценка

Система имеет добротную базу безопасности: корректный JWT с HS256, Bcrypt для паролей, гранулярный RBAC через scopes, защита от IDOR в заказах и append-only леджеры на уровне БД. Критических уязвимостей (SQL-инъекции, XSS) не выявлено. Главные риски — отсутствие rate limiting на auth-эндпоинтах, незащищённый вход клиентов (только по номеру телефона без пароля), дублирование роутера в коде, нереализованный blacklist токенов и слабые пароли в `.env`/`.env.example`.

---

## Сильные стороны

- **JWT реализован корректно.** Алгоритм HS256, `SECRET_KEY` через `SecretStr` (не логируется), стандартные claims `exp`, `iat`, `jti`. Декодирование всегда проверяет подпись и истечение срока. Файл: `src/core/security/jwt.py`.
- **Двухуровневая аутентификация** — `get_token_payload` (fast path, без БД) + `get_current_user` (slow path, с проверкой `is_active`). Файл: `src/modules/auth/dependencies.py`.
- **Bcrypt для паролей** через `pwdlib`. Salt генерируется автоматически, хеш необратим. Файл: `src/core/security/password.py`.
- **RBAC через scopes** — все endpoints защищены `Security(get_current_user, scopes=[...])`. Scopes жёстко привязаны к ролям при создании токена (`ROLE_SCOPES`), не передаются клиентом. Файл: `src/core/security/permissions.py`.
- **IDOR защита в заказах** — `get_order_with_details`, `add_product_to_order`, `remove_product_from_order` принимают `requesting_user_id` и бросают `OrderAccessDeniedError`, если пользователь не является владельцем или исполнителем заказа. Файл: `src/modules/orders/services.py`, строки 459–583.
- **Нет утечки деталей ошибок** — `unhandled_exception_handler` возвращает только `INTERNAL_SERVER_ERROR` без stacktrace. Файл: `src/api/exceptions/handlers.py`, строки 86–104.
- **Защита от SQL-инъекций** — весь доступ к БД через SQLAlchemy ORM и параметризованные запросы. Прямых конкатенаций SQL нет.
- **Интегритет данных на уровне БД** — триггеры PostgreSQL блокируют DELETE/UPDATE на финансовом и складском леджерах, обеспечивая неизменяемость записей даже при компрометации application layer.
- **Soft-delete блокировка** — `get_current_user` проверяет `user.is_active` и бросает `ForbiddenError` для заблокированных аккаунтов.
- **Swagger/ReDoc отключены в prod** — `docs_url=None`, `openapi_url=None` при `ENVIRONMENT=prod`. Файл: `src/api/server.py`, строки 37–47.
- **Walk-in пользователь не может входить** — явная проверка `WALKIN_USER_ID` в `client_login`. Файл: `src/modules/auth/services.py`, строки 118–121.

---

## Проблемы и замечания


### [HIGH] Проблема 2: Отсутствие rate limiting на auth-эндпоинтах

**Файл:** `src/api/server.py`, `src/api/v1/auth/login.py`, `src/api/v1/client/login.py`, `src/api/v1/courier/login.py`

**Описание:**
Нет никакого rate limiting ни на уровне middleware, ни на уровне роутеров. Эндпоинты `/auth/login`, `/client/login`, `/courier/login` не защищены от брутфорса. Зависимость `slowapi` или аналог в `pyproject.toml` отсутствует. Bcrypt намеренно медленный (~100 мс), но этого недостаточно против распределённых атак.

**Рекомендация:**
Подключить `slowapi` (FastAPI-совместимый rate limiter на Redis) с лимитом ~5 попыток в минуту на IP для всех login-эндпоинтов. Redis уже присутствует в конфигурации (`REDISHOST`, `REDISPORT`), но не используется в коде приложения.

---

### [HIGH] Проблема 3: Токен не инвалидируется — blacklist не реализован

**Файл:** `src/core/security/jwt.py`, строки 35–36

**Описание:**
`jti` (JWT ID) генерируется при создании токена с комментарием `# Уникальный ID токена (для Blacklist)`, но механизм blacklist так и не реализован. При блокировке пользователя (`archive(user_id)`) его текущий JWT остаётся валидным до истечения срока (`ACCESS_TOKEN_EXPIRE_MINUTES = 10080` — 7 дней). Пользователь с `is_active=False` будет отклонён только на `get_current_user` (slow path с БД), что правильно, но только если этот path вызывается. Fast path (`get_token_payload`) не проверяет `is_active`.

**Дополнение:** Срок жизни токена — 7 дней. Это долго для B2C-клиентского приложения и особенно критично при компрометации токена (например, через перехват из URL при `client_login`).

**Рекомендация:**
Реализовать Redis-based blacklist: при блокировке пользователя помещать `jti` заблокированного токена в Redis с TTL = оставшийся срок жизни токена. Проверять blacklist в `get_token_payload`. Либо сократить `ACCESS_TOKEN_EXPIRE_MINUTES` до 60–120 минут и ввести refresh tokens.

---

### [HIGH] Проблема 4: `phone` передаётся в query-параметре URL — попадает в логи

**Файл:** `src/api/v1/client/login.py`, строка 22

**Описание:**
```python
async def login(
    phone: str,  # query param — будет виден в URL
    ...
```
Номера телефонов клиентов будут попадать в `AccessLoggerMiddleware` (логируется `path`), в Nginx/Railway access logs, в browser history и CDN-кэш. Это нарушение минимизации персональных данных (PII).

**Рекомендация:**
Переделать эндпоинт на POST с body: `{"phone": "..."}`. Это одно из первых исправлений после внедрения нормальной аутентификации клиентов.

---

### [MEDIUM] Проблема 5: Дублирование роутера в `backoffice/__init__.py`

**Файл:** `src/api/v1/backoffice/__init__.py`, строки 47–52

**Описание:**
`system_router` подключается дважды к одному и тому же prefix `/system`:
```python
backoffice.include_router(
    system_router, prefix="/system", tags=["Backoffice | System"]
)
backoffice.include_router(
    system_router, prefix="/system", tags=["Backoffice | System"]  # дубль!
)
```
Это приведёт к двойной регистрации маршрута `POST /system/seed` в FastAPI. FastAPI не выдаёт ошибку, но в OpenAPI схеме появится дублирующийся путь, и обработчик может вызываться дважды при некоторых конфигурациях.

**Рекомендация:**
Удалить вторую строку include (строки 50–52 в `__init__.py`).

---

### [MEDIUM] Проблема 6: Seed-эндпоинт доступен в production под слабым скопом

**Файл:** `src/api/v1/backoffice/system.py`, строки 12–29

**Описание:**
`POST /backoffice/system/seed` доступен любому пользователю с `USERS_WRITE` scope (в том числе ADMIN). Этот эндпоинт генерирует тестовые данные (продукты, склады, курьеры, клиенты, заказы) и не должен быть доступен в production. Нет проверки `ENVIRONMENT != "prod"`.

**Рекомендация:**
Удалить

---

### [MEDIUM] Проблема 7: `CORS_ORIGINS=[]` по умолчанию — CORS не активируется без явной конфигурации

**Файл:** `src/api/server.py`, строки 50–57; `src/core/config.py`, строка 33

**Описание:**
```python
CORS_ORIGINS: Annotated[list[str] | str, BeforeValidator(parse_cors)] = []
...
if settings.CORS_ORIGINS:  # если пустой список — CORSMiddleware не добавляется
    app.add_middleware(CORSMiddleware, ...)
```
Если `CORS_ORIGINS` не задан в production, CORSMiddleware вообще не подключается, что означает полный запрет cross-origin запросов (браузер будет блокировать). Это может привести к «тихой» неработоспособности frontend в prod без явного понимания причины.

Кроме того, `allow_methods=["*"]` и `allow_headers=["*"]` — слишком широкая конфигурация. В prod следует разрешать только нужные методы и заголовки.

**Рекомендация:**
Требовать явный `CORS_ORIGINS` в prod (ошибка при старте), либо добавить fallback-предупреждение. Сузить `allow_methods` до `["GET", "POST", "PATCH", "DELETE"]`.

---

### [MEDIUM] Проблема 8: `.env` совпадает с `.env.example` — реальный SECRET_KEY в репозитории

**Файл:** `.env` и `.env.example`

**Описание:**
Файлы `.env` и `.env.example` идентичны по содержанию и оба содержат реальный `SECRET_KEY`:
```
SECRET_KEY=7b8b965bc1012353721382583802e3cb98e56117d9171b3127521e6490606d28
```
Если `.env` не исключён из git (а по `git status` видно, что он не помечен как untracked — значит уже трекается или `.gitignore` его скрывает), этот ключ компрометирован. Любой, получивший доступ к репозиторию, сможет подписывать произвольные JWT.

Также `PGPASSWORD=postgres`, `REDISPASSWORD=secret` — слабые пароли, но это dev-окружение.

**Рекомендация:**
1. Добавить `.env` в `.gitignore` (убедиться, что он там есть).
2. Ротировать `SECRET_KEY` в prod.
3. В `.env.example` использовать placeholder: `SECRET_KEY=REPLACE_ME_WITH_RANDOM_64_CHAR_HEX`.

---

### [MEDIUM] Проблема 9: Нет проверки принадлежности заказа при `update_status` от backoffice курьера

**Файл:** `src/api/v1/courier/orders.py`, строки 152–169; `src/modules/orders/services.py`

**Описание:**
Метод `update_order_status` в courier-роутере вызывает `_update_courier_order_status`, который передаёт `requesting_user_id=courier.id`. Это корректно для большинства операций. Однако generic `update_order_status` (`PATCH /{order_id}/status`) принимает произвольный `new_status` из тела запроса. Курьер теоретически может попытаться перевести чужой заказ — но проверяется ли принадлежность в `update_status`? Нужно убедиться, что сервисный метод всегда передаёт `requesting_user_id`.

**Анализ кода:** В `_update_backoffice_order_status` (backoffice) `requesting_user_id` не передаётся (None), что правильно для администратора. В `_update_courier_order_status` — передаётся. Это корректно. Но стоит добавить явный тест, что курьер не может изменить статус чужого заказа через `PATCH /courier/orders/{id}/status`.

**Рекомендация:**
Добавить интеграционный тест: курьер A не может менять статус заказа, назначенного курьеру B.

---

### [LOW] Проблема 10: Argon2 установлен, но не используется — Bcrypt слабее

**Файл:** `src/core/security/password.py`; `pyproject.toml` (зависимость `pwdlib[argon2,bcrypt]`)

**Описание:**
В `pyproject.toml` указана зависимость `pwdlib[argon2,bcrypt]` — оба алгоритма установлены. Однако в коде используется только `BcryptHasher`. Argon2 является более современным и рекомендованным алгоритмом (победитель Password Hashing Competition 2015), особенно устойчивым к GPU-атакам.

Текущий код:
```python
password_hash = PasswordHash((BcryptHasher(),))
```

**Рекомендация:**
Переключить на `Argon2Hasher` как основной, оставив `BcryptHasher` для миграционной совместимости:
```python
from pwdlib.hashers.argon2 import Argon2Hasher
password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))
```
`pwdlib` автоматически выберет первый хашер для новых паролей и проверит старые Bcrypt-хеши при верификации.

---

### [LOW] Проблема 11: `LocalLogin` не валидирует формат телефона

**Файл:** `src/modules/auth/schemas.py`, строка 5; `src/modules/users/schemas.py`, строки 54–57

**Описание:**
`LocalLogin.phone: str` — без валидации формата. `UserCreate.phone: str` — аналогично. Нет ни regex, ни проверки длины на входном слое. Это не критично (аутентификация просто не найдёт пользователя), но создаёт возможность для перебора с заведомо некорректными данными, зря нагружая БД.

**Рекомендация:**
Добавить валидацию:
```python
phone: Annotated[str, Field(pattern=r"^\+?[0-9]{8,15}$")]
```

---

### [LOW] Проблема 12: `HTTPException` в `transport.py` вместо доменных исключений

**Файл:** `src/api/v1/backoffice/transport.py`, строки 82–84, 105–107, 127–128

**Описание:**
```python
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Transport not found"
)
```
В трёх местах используется `HTTPException` напрямую, что нарушает архитектурное соглашение проекта (все бизнес-ошибки — через `AppException`). Ответ будет в формате `{"detail": "..."}` вместо `{"error": {"code": ..., "message": ..., "details": {}}}`.

**Рекомендация:**
Заменить на `raise InventoryNotFoundError(...)` или `NotFoundError(...)` из доменного слоя.

---

### [INFO] Проблема 13: Нет CSP и Security Headers

**Файл:** `src/api/server.py`

**Описание:**
Отсутствуют `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security` заголовки. Для API (не HTML) большинство из них нерелевантны, но `X-Content-Type-Options: nosniff` и `Strict-Transport-Security` полезны.

**Рекомендация:**
Добавить middleware для security headers, например через `starlette-exporter` или кастомный middleware.

---

## Обновления документации

| Файл | Изменение |
|------|-----------|
| `docs/codebase/01-api-layer.md` | Исправлены scopes для `POST /transports/` (`TRANSPORTS_READ` → `INVENTORY_WRITE`), `PATCH /transports/{id}` (`TRANSPORTS_READ` → `INVENTORY_WRITE`), `DELETE /transports/{id}` (`TRANSPORTS_READ` → `INVENTORY_WRITE`). Реальный код: `src/api/v1/backoffice/transport.py`, строки 55, 97, 119. |
| `docs/codebase/01-api-layer.md` | Исправлены scopes для CLIENT ROUTER: `POST /orders/{order_id}/items` и `DELETE /orders/{order_id}/items/{product_id}` — `ORDERS_EDIT` → `ORDERS_CREATE`. Реальный код: `src/api/v1/client/orders.py`, строки 70, 91. |
| `docs/codebase/README.md` | Уточнён алгоритм хеширования паролей: `Argon2/Bcrypt` → `Bcrypt (активен), Argon2 (установлен но не используется)`. |
| `docs/codebase/03-application-layer.md` | Добавлено примечание к Password Security: фактически используется только Bcrypt, Argon2 в коде не активирован, несмотря на наличие в зависимостях. |

---

## Итоговые рекомендации

2. **[Срочно]** Ротировать `SECRET_KEY` в production и убедиться, что `.env` не трекается git.
3. **[Срочно]** Перенести `phone` в client login из query-параметра в POST body.
4. **[Высокий приоритет]** Добавить rate limiting (slowapi + Redis) на все auth-эндпоинты.
5. **[Высокий приоритет]** Реализовать JWT blacklist на Redis с использованием уже генерируемого `jti` — особенно важно при блокировке пользователей.
6. **[Средний приоритет]** Удалить дублирующийся `system_router` в `backoffice/__init__.py`.
7. **[Средний приоритет]** Ограничить seed-эндпоинт средой выполнения (`ENVIRONMENT != "prod"`).
8. **[Средний приоритет]** Заменить `HTTPException` в `transport.py` на доменные исключения.
9. **[Низкий приоритет]** Переключить password hasher с Bcrypt на Argon2 (с backward-compat на Bcrypt).
10. **[Низкий приоритет]** Добавить валидацию формата телефона в схемы `LocalLogin` и `UserCreate`.
