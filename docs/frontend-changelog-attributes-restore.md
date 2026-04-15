# Изменения API: `attributes` → список + `PATCH /restore`

> [!important] Breaking Change
> Поле `attributes` у продуктов изменило формат. Старый формат **больше не принимается** бэкендом.

## 1. `attributes`: объект → массив

### Было (старый формат)

```json
{
  "attributes": {
    "volume": "19Л",
    "material": "ПК"
  }
}
```

### Стало (новый формат)

```json
{
  "attributes": [
    { "label": "Объём", "value": "19Л" },
    { "label": "Материал", "value": "ПК" }
  ]
}
```

### Зачем

Ключи объекта не могут содержать длинные человекочитаемые
названия вроде _«Мощность двигателя внутреннего сгорания»_.
Новый формат `{ label, value }` снимает это ограничение.

### Что менять на фронте

| Место | Было | Стало |
|-------|------|-------|
| Отправка (`POST / PUT`) | `{ [key]: value }` | `[{ label, value }]` |
| Чтение (`GET`) | `Object.entries(attributes)` | `attributes.map(a => [a.label, a.value])` |
| Типы (TypeScript) | `Record<string, string>` | `Array<{ label: string; value: string }>` |

### Валидация

- `label` — строка, 1–255 символов, **обязательное**
- `value` — строка, 1–255 символов, **обязательное**
- Массив может быть пустым (`[]`)

---

## 2. Новый эндпоинт: восстановление товара

```
PATCH /api/v1/backoffice/catalog/{product_id}/restore
```

| Параметр | Описание |
|----------|----------|
| Метод | `PATCH` |
| Авторизация | Scope `catalog:write` |
| Тело запроса | Нет |
| Успех | `204 No Content` |
| Товар не найден | `404` — `PRODUCT_NOT_FOUND` |
| Тара архивирована | `422` — `INVALID_RETURNABLE_ITEM` |

### Логика

- Восстанавливает архивированный товар (`is_active` → `true`)
- Если у товара есть привязанная тара (`returnable_item_id`)
  и эта тара сама архивирована — возвращает **422**
- Парный эндпоинт к `PATCH /{product_id}/archive`

### Пример вызова

```ts
await fetch(`/api/v1/backoffice/catalog/${productId}/restore`, {
  method: "PATCH",
  headers: { Authorization: `Bearer ${token}` },
});
// 204 — успех, тело ответа пустое
```

### UX-рекомендация

В списке архивированных товаров добавить кнопку **«Восстановить»**.
Если бэкенд вернул `422 INVALID_RETURNABLE_ITEM` — показать
сообщение: _«Сначала восстановите тару, к которой привязан товар»_.
