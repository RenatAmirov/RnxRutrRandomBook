# Случайная книга RuTracker

Фоновое приложение для Windows 10 и 11. Удерживайте **Ctrl** и нажмите **R**, **N**, **D** так, чтобы все четыре клавиши оказались зажаты одновременно. Можно использовать левый или правый Ctrl. Клавиши R, N и D определяются по расположению на клавиатуре и работают в русской раскладке.

Приложение выбирает случайную тему из недавних публикаций в книжных лентах RuTracker и открывает её в браузере по умолчанию. В выборку входят художественная литература, детские познавательные книги, философия, математика и программирование. Иногда тема содержит сборник книг. Нажатия также получает активная программа, поэтому её собственные сочетания могут сработать.

## Установка

Понадобится [Python 3.10 или новее для Windows](https://www.python.org/downloads/windows/). Откройте PowerShell в папке проекта и выполните:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage.ps1 Install
```

Установщик запускает приложение без окна и добавляет запуск при входе текущего пользователя через Планировщик заданий. Windows запускает приложение в пользовательском сеансе, где доступны клавиатура и браузер. Если `python` отсутствует в `PATH`, добавьте `-PythonPath 'C:\путь\к\python.exe'` к команде установки.

## Управление

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage.ps1 Status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage.ps1 Stop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage.ps1 Start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\manage.ps1 Uninstall
```

`Stop` останавливает приложение до следующего ручного запуска или входа в Windows. `Uninstall` удаляет задание автозапуска. После переноса проекта в другую папку повторите установку из новой папки.

Если ленты недоступны или Windows не удаётся открыть браузер, приложение подаёт системный звук и записывает ошибку в `%LOCALAPPDATA%\RnxRutrRandomBook\service.log`. Доступность лент можно проверить отдельно командой `python .\book_service.py --url`.
