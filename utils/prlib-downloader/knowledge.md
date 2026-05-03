# prlib.ru — алгоритм скачивания страниц

## Стек

- Сайт работает на Drupal 7
- Просмотрщик: **DIVA.js** (viewer для манускриптов/книг на тайловой основе)
- Сервер изображений: **IIPImage 1.2** (`iipsrv/1.2`) на поддомене `content.prlib.ru`

---

## Шаг 1 — Получить параметры просмотрщика из HTML страницы

Страница книги (`/item/{node_id}`) содержит Drupal.settings JSON прямо в HTML. В нём хранится конфигурация DIVA:

```
Drupal.settings.diva["1"].options = {
  iipServerURL: "https://content.prlib.ru/fcgi-bin/iipsrv.fcgi",
  imageDir:     "/var/data/scans/public/{UUID}/{filegroup_id}",
  objectData:   "https://content.prlib.ru/metadata/public/{UUID}/{filegroup_id}/{UUID}.json"
}
```

Для извлечения достаточно grep/regex по `"diva"` в HTML-исходнике.

---

## Шаг 2 — Загрузить JSON-манифест (objectData)

`GET {objectData}`

Возвращает структуру:

```json
{
  "item_title": "...",
  "max_zoom": 4,
  "dims": { "max_w": [...], "max_h": [...] },
  "pgs": [
    {
      "f": "5382186_doc1_UUID.tiff",
      "m": 4,
      "d": [
        { "w": 107, "h": 164 },   // zoom 0
        { "w": 214, "h": 328 },   // zoom 1
        { "w": 429, "h": 657 },   // zoom 2
        { "w": 859, "h": 1315 },  // zoom 3
        { "w": 1718, "h": 2631 }  // zoom 4 — максимум
      ]
    },
    ...
  ]
}
```

`pgs[i].f` — имя файла TIFF на сервере.  
`pgs[i].d[zoom]` — пиксельные размеры страницы на данном уровне масштаба.

---

## Шаг 3 — Почему нельзя скачать одним запросом

IIPImage поддерживает параметр `WID=` (ширина выходного JPEG), но сервер prlib.ru ограничивает максимальный размер одного ответа примерно до **1110×1700 px**, даже если исходник 1718×2631.

```
GET iipsrv.fcgi?FIF=...&WID=1718&CVT=JPEG  →  1110×1700 (ограничение сервера)
GET iipsrv.fcgi?FIF=...&CVT=JPEG           →  1110×1700 (то же самое)
GET iipsrv.fcgi?IIIF=.../full/full/0/default.jpg → 1110×1700 (то же самое)
```

**Для получения полного разрешения нужен тайловый метод.**

---

## Шаг 4 — Тайловая загрузка (JTL)

IIPImage отдаёт тайлы 256×256 через параметр `JTL`:

```
GET iipsrv.fcgi?FIF={imageDir}/{filename}&JTL={zoom},{tile_number}
```

Тайлы нумеруются построчно (row-major):

```
tile_number = row * cols + col

cols = ceil(width  / 256)
rows = ceil(height / 256)
```

Для страницы 1718×2631 при zoom=4:
- cols = ceil(1718/256) = **7**
- rows = ceil(2631/256) = **11**
- итого = **77 тайлов**

Последние тайлы в ряду/колонке меньше 256 px — IIPImage обрезает их автоматически.

---

## Шаг 5 — Сборка изображения

```python
canvas = Image.new("RGB", (width, height))
for row in range(rows):
    for col in range(cols):
        tile = download(JTL=zoom, tile_num=row*cols+col)
        canvas.paste(tile, (col*256, row*256))
canvas.save("page.jpg", quality=95)
```

---

## Параметры запросов

| Параметр | Значение |
|---|---|
| `FIF` | абсолютный путь к TIFF на сервере (`imageDir/filename`) |
| `JTL` | `{zoom_level},{tile_number}` |
| `WID` | ширина для одиночного JPEG (ограничен сервером) |
| `CVT` | формат вывода (`JPEG`) |
| `OBJ` | метаинформация: `Max-size`, `Tile-size`, `Resolution-number` |

Пример получения метаданных файла:
```
GET iipsrv.fcgi?FIF=...&OBJ=IIP,1.0&OBJ=Max-size&OBJ=Tile-size&OBJ=Resolution-number
→ Max-size:1718 2631
→ Tile-size:256 256
→ Resolution-number:5
```

---

## Заголовки HTTP

Обязательно передавать `Referer: https://www.prlib.ru/item/{node_id}`.  
CORS открыт (`Access-Control-Allow-Origin: *`), авторизация не требуется для публичных фондов.

---

## Паузы между страницами

5 секунд между страницами (не между тайлами). Тайлы одной страницы можно грузить последовательно без паузы.

---

## Готовый скрипт

`/Users/sergeymishenev/Desktop/Media Labs/книги/Берх, Василий Николаевич/download.py`

Скрипт возобновляем: при повторном запуске пропускает уже существующие `page_NNNN.jpg`.
