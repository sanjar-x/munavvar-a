# src/api/v1/client/inventory.py
#
# ЭНДПОИНТ /capitalize-deficit УДАЛЕН (Фикс Fraud Risk).
#
# Причина: Клиент мог отправить фейковую корзину на 1000 бутылей,
# получить 1000 тар на баланс и не оформить заказ — бесконтрольная
# накрутка виртуального баланса тары.
#
# Решение: Авто-оприходование дефицита тары теперь происходит
# ИСКЛЮЧИТЕЛЬНО внутри транзакции создания заказа через флаг
# capitalize_missing_tara: true в POST /orders.
#
# Для диспетчеров: POST /backoffice/clients/{id}/inventory/capitalize
# остается без изменений (ручное оприходование под авторизацией).

from fastapi import APIRouter

inventory_router = APIRouter()
