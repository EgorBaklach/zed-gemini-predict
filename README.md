# zed-gemini-predict

Легковесный FIM-мост (`http://127.0.0.1:8089/v1/completions`) для подключения **Google Gemini 3.5 Flash Lite** (`thinkingLevel: MINIMAL`) к **Zed Edit Predictions** (`open_ai_compatible_api`) с архитектурой **Строгого Синтаксического Детерминизма (Modern PHP 8.2/8.3+)**.

---

## 🎯 Философия: Синтаксический детерминизм против архитектурных галлюцинаций

Стандартные LLM-автодополнения (Copilot, Continue, Supermaven) пытаются угадывать целые блоки бизнес-логики даже тогда, когда программист поставил курсор на пустую строку или только что открыл `if (`. Это приводит к навязыванию чужой архитектуры и постоянному удалению лишнего кода.

**`zed-gemini-predict`** решает противоположную задачу — он работает как **мгновенный локальный синтаксический и идиоматический замыкатель**:

1. **Уровень 1 — Pre-Flight Gatekeeper (`0 мс`, `0 токенов`):**
   - Функция `should_skip_request` проверяет текущую строку перед курсором через регулярное выражение `_OPEN_SEMANTIC_SLOT_RE` **до обращения к API**.
   - Если курсор находится в **«Открытом семантическом слоте»** (пустая строка, одиночные `{`/`}`, голые `if (`, `} elseif (`, `while (`, `foreach (`, `switch (`, `$v = match (`, голые `return `, `throw new `, `$var = `, `$this->prop = `, `$arr['k'] ??= `, незавершённые операторы `->`/`?->`/`::`, комментарии `//` или случайная раскладка `ша()`), прокси мгновенно возвращает `""` за **~2 мс**, не тратя токены и не галлюцинируя бизнес-логику.
2. **Уровень 2 — Keep-Alive TLS + `gemini-3.5-flash-lite` (`thinkingLevel: MINIMAL`):**
   - Постоянное TLS-соединение (`http.client.HTTPSConnection`) к `generativelanguage.googleapis.com` экономит 300–400 мс на каждом запросе (среднее время ответа **~500–650 мс**).
   - Специализированная системная инструкция под **PHP 8.2/8.3+** (`strict_types`, `readonly`, Backed Enums, Traits, `match`, стрелочные функции `fn() =>`, Constructor Property Promotion, `?->`).
3. **Уровень 3 — Математический и структурный пост-процессор (`clean_completion`):**
   - Удаляет дублирование суффикса (`strip_suffix_overlap`) и повтор уже набранного префикса (`strip_prefix_repetition`).
   - Считает баланс открытых и закрытых круглых скобок `(` / `)` на текущей строке (`fix_paren_and_semicolon_balance`), автоматически дописывая недостающие `)` или убирая лишние `))`.
   - Срезает выдуманные хвосты `&& ...` / `|| ...` при закрытии заголовка `if (...)` и запрещает дописывать тело внутрь `{ ... }` на следующем шаге.
   - Гарантирует валидный синтаксис PHP при локальном рефакторинге замыканий (`fn() =>` ↔ `function () use () { return ...; }`).

---

## ⚙️ Установка и запуск (Linux / WSL 2)

Не требует сторонних pip-пакетов (работает на стандартной библиотеке Python 3.10+ и потребляет **~1.9 МБ RAM**).

### 1. Клонирование репозитория
```bash
git clone https://github.com/EgorBaklach/zed-gemini-predict.git ~/zed-gemini-predict
cd ~/zed-gemini-predict
```

### 2. Настройка API-ключа
Создайте файл `~/.zed_fim_proxy.env`:
```bash
cp .env.example ~/.zed_fim_proxy.env
chmod 600 ~/.zed_fim_proxy.env
nano ~/.zed_fim_proxy.env
```
Укажите ваш `GEMINI_API_KEY`.

### 3. Автозапуск через systemd (User Service)
```bash
mkdir -p ~/.config/systemd/user
cp systemd/zed-fim-proxy.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now zed-fim-proxy.service
systemctl --user status zed-fim-proxy.service
```

---

## 🛠️ Настройка Zed (`settings.json`)

Добавьте блок `edit_predictions` в настройки Zed (`~/.config/zed/settings.json` или `%APPDATA%\Zed\settings.json` на Windows):

```json
{
  "show_edit_predictions": false,
  "edit_predictions": {
    "provider": "open_ai_compatible_api",
    "mode": "eager",
    "allow_data_collection": "no",
    "open_ai_compatible_api": {
      "api_url": "http://127.0.0.1:8089/v1/completions",
      "model": "gemini-3.5-flash-lite",
      "prompt_format": "qwen",
      "max_output_tokens": 80,
      "prediction_debounce": 400
    }
  }
}
```
> При `"show_edit_predictions": false` подсказки не мешают во время обычного набора и вызываются вручную по хоткею **`Alt+\`**.

---

## 🧪 Запуск тестов

В репозитории содержатся 3 тестовых набора (46 сценариев):

```bash
# 1. Тест закона детерминизма (16 открытых слотов за ~2 мс + 10 граничных кейсов PHP)
python3 tests/test_determinism.py

# 2. Базовые синтаксические конструкции и рефакторинг PHP (16 кейсов)
python3 tests/test_php_cases.py

# 3. Конструкции современного PHP 8.2/8.3+ (Enums, Traits, Fluent Chains, Nullsafe)
python3 tests/test_php83_cases.py
```
