# src/core/security/permissions.py
from src.modules.users.enums import Role


class Scope:
    """Полный список разрешений (Permissions/Scopes) в системе по доменам"""

    # --- ПОЛЬЗОВАТЕЛИ И ПРОФИЛИ (Users) ---
    USERS_READ = "users:read"  # Просмотр чужих профилей и списка сотрудников
    USERS_WRITE = "users:write"  # Создание/блокировка сотрудников
    PROFILE_READ = "profile:read"  # Просмотр собственного профиля (Все)
    PROFILE_WRITE = (
        "profile:write"  # Редактирование собственного профиля (Все)
    )

    # --- КАТАЛОГ (Catalog) ---
    CATALOG_READ = "catalog:read"  # Просмотр товаров и цен (Клиенты, Кассиры)
    CATALOG_WRITE = "catalog:write"  # Добавление/изменение товаров (Админ)

    # --- ЗАКАЗЫ (Orders) ---
    ORDERS_READ = (
        "orders:read"  # Просмотр заказов (Своих или всех — решает сервис)
    )
    ORDERS_CREATE = "orders:create"  # Оформление заказа (Клиенты, Кассир)
    ORDERS_EDIT = "orders:edit"  # Изменение состава чужого заказа (Админ)
    ORDERS_DELIVER = (
        "orders:deliver"  # Взятие в доставку и смена статусов (Курьер)
    )
    ORDERS_CANCEL = (
        "orders:cancel"  # Отмена заказа (Клиент - своего, Админ - любого)
    )

    # --- СКЛАД И ЛОГИСТИКА (Logistics & Inventory) ---
    INVENTORY_READ = (
        "inventory:read"  # Просмотр остатков на складе (Кладовщик, Кассир)
    )
    INVENTORY_WRITE = (
        "inventory:write"  # Инвентаризация, ручное списание (Кладовщик)
    )
    LOGISTICS_SUPPLY = (
        "logistics:supply"  # Приемка товара от поставщика (Кладовщик)
    )
    LOGISTICS_TRANSFER = (
        "logistics:transfer"  # Перемещение между складами (Кладовщик)
    )
    ROUTES_READ = "routes:read"  # Просмотр маршрутных листов (Курьер, Админ)

    # --- ФИНАНСЫ И КАССА (Finances) ---
    FINANCES_READ = "finances:read"
    FINANCES_WRITE = "finances:write"
    PAYMENTS_CREATE = (
        "payments:create"  # Прием оплаты, пробитие чека (Кассир, Курьер)
    )
    BILLS_READ = (
        "bills:read"  # Просмотр счетов-фактур и актов (Клиент B2B, Бухгалтер)
    )

    # --- СИСТЕМНЫЕ (System) ---
    SETTINGS_READ = "settings:read"  # Просмотр глобальных настроек системы
    SETTINGS_WRITE = "settings:write"  # Изменение системных настроек (Админ)
    SYSTEM_EXEC = (
        "system:exec"  # Технический scope для фоновых задач (Celery/Cron)
    )


BASE_SCOPES = [
    Scope.PROFILE_READ,
    Scope.PROFILE_WRITE,
    Scope.CATALOG_READ,
]

ROLE_SCOPES: dict[Role, list[str]] = {
    Role.SYSTEM: [
        Scope.SYSTEM_EXEC,
    ],
    # Администратор (Superuser - полный CRUD)
    Role.ADMIN: BASE_SCOPES
    + [
        Scope.USERS_READ,
        Scope.USERS_WRITE,
        Scope.CATALOG_WRITE,
        Scope.ORDERS_READ,
        Scope.ORDERS_EDIT,
        Scope.ORDERS_CANCEL,
        Scope.INVENTORY_READ,
        Scope.ROUTES_READ,
        Scope.FINANCES_READ,
        Scope.FINANCES_WRITE,
        Scope.SETTINGS_READ,
        Scope.SETTINGS_WRITE,
    ],
    # Бухгалтер (Только деньги, документы и персонал)
    Role.ACCOUNTANT: BASE_SCOPES
    + [
        Scope.USERS_READ,
        Scope.FINANCES_READ,
        Scope.FINANCES_WRITE,
        Scope.BILLS_READ,
    ],
    # Кладовщик (Только склад и логистика)
    Role.STOREKEEPER: BASE_SCOPES
    + [
        Scope.ORDERS_READ,
        Scope.INVENTORY_READ,
        Scope.INVENTORY_WRITE,
        Scope.LOGISTICS_SUPPLY,
        Scope.LOGISTICS_TRANSFER,
    ],
    # Кассир (POS-терминал: создание заказов, прием денег, просмотр остатков)
    Role.CASHIER: BASE_SCOPES
    + [
        Scope.ORDERS_READ,
        Scope.ORDERS_CREATE,
        Scope.INVENTORY_READ,
        Scope.PAYMENTS_CREATE,
    ],
    # Курьер (Доставка, маршруты, прием налички у двери)
    Role.COURIER: BASE_SCOPES
    + [
        Scope.ORDERS_READ,
        Scope.ORDERS_DELIVER,
        Scope.ROUTES_READ,
        Scope.PAYMENTS_CREATE,
    ],
    # Физ. лицо (Свои заказы)
    Role.CLIENT_B2C: BASE_SCOPES
    + [
        Scope.ORDERS_READ,
        Scope.ORDERS_CREATE,
        Scope.ORDERS_CANCEL,
    ],
    # Юр. лицо (Свои заказы + финансовые документы)
    Role.CLIENT_B2B: BASE_SCOPES
    + [
        Scope.ORDERS_READ,
        Scope.ORDERS_CREATE,
        Scope.ORDERS_CANCEL,
        Scope.BILLS_READ,
    ],
}
