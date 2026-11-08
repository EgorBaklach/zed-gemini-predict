# zed-gemini-predict

Легковесный FIM-мост (`http://127.0.0.1:8089/v1/completions`) для подключения **Google Gemini 3.5 Flash Lite** (`thinkingLevel: MINIMAL`) к **Zed Edit Predictions** (`open_ai_compatible_api`) с архитектурой **Строгого Синтаксического Детерминизма (Modern PHP 8.2/8.3+)**.

---

## 🎯 Философия: Синтаксический детерминизм против архитектурных галлюцинаций

Стандартные LLM-автодополнения (Copilot, Continue, Supermaven) пытаются угадывать целые блоки бизнес-логики даже тогда, когда программист поставил курсор на пустую строку или только что открыл `if (`. Это приводит к навязыванию чужой архитектуры и постоянному удалению лишнего кода.

**`zed-gemini-predict`** решает противоположную задачу — он работает как **мгновенный локальный синтаксический и идиоматический замыкатель**:

1. **Уровень 1 — Pre-Flight Gatekeeper (`0 мс`, `0 токенов`):**
   - [`should_skip_request`](bridge/php/gatekeeper.py) проверяет текущую строку перед курсором через `OPEN_SEMANTIC_SLOT_RE` **до обращения к API**.
   - Если курсор находится в **«Открытом семантическом слоте»** (пустая строка, одиночные `{`/`}`, голые `if (`, `} elseif (`, `while (`, `foreach (`, `switch (`, `$v = match (`, голые `return `, `throw new `, `$var = `, `$this->prop = `, `$arr['k'] ??= `, незавершённые операторы `->`/`?->`/`::`, комментарии `//`, курсор внутри слова или случайная раскладка `ша()`), а также в конце уже законченной строки (`;`, `{`, `'k' => $v,`), прокси мгновенно возвращает `""` за **~2 мс**, не тратя токены.
2. **Уровень 2 — Keep-Alive TLS + `gemini-3.5-flash-lite` (`thinkingLevel: MINIMAL`):**
   - Постоянное TLS-соединение к `generativelanguage.googleapis.com` экономит 300–400 мс на каждом запросе (среднее время ответа **~500–650 мс**).
   - Специализированная [системная инструкция](bridge/php/prompt.py) под **PHP 8.2/8.3+** (`strict_types`, `readonly`, Backed Enums, Traits, `match`, `fn() =>`, Constructor Property Promotion, `?->`).
3. **Уровень 3 — Упорядоченный конвейер структурных правил ([`bridge/php/__init__.py`](bridge/php/__init__.py)):**
   - 25 маленьких именованных правил: зачистка мусора (FIM-теги, markdown, `<?php`, `)</table>`), стыковка с суффиксом/префиксом, защита от выдумывания (тела классов и `if`, лишние зависимости в конструкторе, новые методы в fluent-цепочке, новые ветки `match`, код после закрытого блока, повтор аргумента), идиомы PHP (`case X = 'x';`, `function () use () { return ...; }`) и финальный баланс скобок с учётом строк и кода после курсора.
   - Каждое сработавшее правило пишется в отладочный лог (`"rules": [...]`), поэтому всегда видно, **почему** ответ выглядит именно так.
4. **Запасной вариант:** если Gemini ничего не вернул, а выражение перед курсором закончено и строка продолжается после него, мост механически закрывает открытые скобки ([`fallback.py`](bridge/php/fallback.py)).

---

## 🧱 Структура

```
zed_fim_proxy.py          # точка входа (systemd ExecStart)
bridge/
  config.py               # переменные окружения
  server.py               # HTTP /v1/completions для Zed, отладочный лог
  fim.py                  # формат FIM: разбор промпта Zed и сборка промпта для Gemini
  gemini.py               # keep-alive клиент Gemini
  pipeline.py             # LanguageProfile + postprocess(): правила по порядку, трассировка, fallback
  rules_common.py         # правила, не зависящие от языка
  php/
    __init__.py           # PHP-профиль: ПОРЯДОК правил
    prompt.py             # системная инструкция
    gatekeeper.py         # открытые семантические слоты
    rules.py              # PHP-правила
    syntax.py             # лексические помощники (строки, скобки, заголовки)
    fallback.py           # механическое закрытие скобок
```

Новый язык = новый пакет `bridge/<lang>/` со своим профилем; общие правила переиспользуются.

---

## ⚙️ Установка и запуск (Linux / WSL 2)

Не требует сторонних pip-пакетов (только стандартная библиотека Python 3.10+, ~11 МБ RAM; собственная обработка запроса ~30 мкс — всё остальное время уходит на сеть и модель).

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

```bash
# 0. Офлайн-тесты детерминированных слоёв (без сети и токенов): гейткипер, пост-процессор,
#    механическое закрытие скобок — на реальных сырых ответах Gemini из логов
python3 tests/test_postprocessor_offline.py

# 1. Эмуляция живого написания ООП MVC-калькулятора в Zed (главный интеграционный тест):
#    8 файлов (Enum, Interface, Trait, Model, Builder, View, Controller, index.php),
#    26 проб «открытых слотов» + 24 точки Alt+\ + проверка после каждого Tab,
#    сборка проекта из ответов моста -> php -l -> запуск -> 15 runtime-ассертов.
#    Покрывает все кейсы из test_determinism / test_php_cases / test_php83_cases.
python3 tests/simulate_mvc_live_coding.py              # одна сессия
python3 tests/simulate_mvc_live_coding.py --runs 3     # проверка нестабильности модели
python3 tests/simulate_mvc_live_coding.py --only model_sprintf,idx_fluent --runs 5  # точечный повтор шагов

# 2. Тест закона детерминизма (16 открытых слотов за ~2 мс + 10 граничных кейсов PHP)
python3 tests/test_determinism.py

# 3. Базовые синтаксические конструкции и рефакторинг PHP (16 кейсов)
python3 tests/test_php_cases.py

# 4. Конструкции современного PHP 8.2/8.3+ (Enums, Traits, Fluent Chains, Nullsafe)
python3 tests/test_php83_cases.py
```

> Эмулятору нужен `php` CLI (8.2+) в WSL. Сгенерированный из ответов моста проект остаётся в `/tmp/zed_mvc_calc`.

## 🛠️ Скрипты разработки (WSL)

```bash
bash scripts/deploy_wsl.sh        # рабочая копия -> runtime-клон ~/zed-gemini-predict + рестарт сервиса
bash scripts/regression.sh [N]    # офлайн-тесты + эмулятор xN (по умолчанию 3) + старые наборы
python3 scripts/debug_log.py 30 sprintf   # последние решения моста: сырой ответ, что ушло в Zed, сработавшие правила
```

Правила работы с репозиторием для AI-агентов — в [AGENTS.md](AGENTS.md).
