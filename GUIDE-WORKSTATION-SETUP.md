# Первичная настройка Windows и macOS

## 1. Общие особенности репозитория `avkus-labs/frida`
- Скрипты (`main.py`, `interactive.py`, `setup.py`, `frida.js`) адаптированы под нативный **`adb root`** (заглушка `/system/bin/su` не требуется).
- В `.gitignore` исключены распакованные бинарники `assets/frida-server-*` (>100 МБ), чтобы не блокировался `git push`.

---

## 2. Настройка на Windows
1. **SSH-ключ** (проверьте существующие ключи перед созданием, чтобы не перезаписать ключ GitHub):
   ```powershell
   dir $env:USERPROFILE\.ssh
   # Если ключа нет:
   ssh-keygen -t ed25519
   type $env:USERPROFILE\.ssh\id_ed25519.pub
   ```
   Добавить публичный ключ:
   - на `debian-nested` → `~/.ssh/authorized_keys`
   - на GitHub → *Settings → SSH and GPG keys*

2. **ADB и Python:**
   - `adb.exe` расположен в `C:\platform-tools\` (в `PATH`).
   - Запускать скрипты тем интерпретатором `python`, в котором установлена `frida` (проверка: `python -c "import frida; print(frida.__version__)"`). Не путать `python` и `python3` (если установлен второй Python 3.14 без `frida`).

3. **Если зависает скачивание `frida-server` в `main.py` (`urlretrieve`):**
   Скачать через `curl.exe -4` и распаковать:
   ```powershell
   $ver = python -c "import frida; print(frida.__version__)"
   curl.exe -4 -L --progress-bar -o "E:\frida\assets\frida-server-$ver-android-x86_64.xz" "https://github.com/frida/frida/releases/download/$ver/frida-server-$ver-android-x86_64.xz"
   python -c "import frida, lzma, pathlib; v=frida.__version__; p=pathlib.Path(rf'E:\frida\assets\frida-server-{v}-android-x86_64.xz'); p.with_suffix('').write_bytes(lzma.open(p).read()); print('OK')"
   ```

4. **Конфиг (`E:\frida\config.py`):**
   ```powershell
   copy config.example.py config.py
   ```
   Указать `ADB_SERIAL = "127.0.0.1:15551"`.

5. **Рекомендуемые настройки TightVNC Viewer** (для отзывчивости курсора):
   - *Encoding:* `Tight`, *Color level:* `8-bit color` (или JPEG quality `2–3`, Compression `1–2`)
   - *Mouse:* `Local cursor shape → Small dot`

---

## 3. Настройка на macOS
1. **Git, ADB и Python:**
   ```bash
   xcode-select --install
   brew install --cask android-platform-tools
   brew install python
   ```

2. **SSH-ключ (один и тот же ключ можно использовать для `debian-nested` и GitHub):**
   ```bash
   [ -f ~/.ssh/id_ed25519.pub ] || ssh-keygen -t ed25519
   cat ~/.ssh/id_ed25519.pub
   ```
   Добавить в `~/.ssh/authorized_keys` на `debian-nested` и в GitHub → *SSH and GPG keys*.

3. **Клонирование и установка в `.venv`:**
   ```bash
   git clone git@github.com:avkus-labs/frida.git
   cd ~/frida
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp config.example.py config.py
   ```
   В `config.py` указать `ADB_SERIAL = "127.0.0.1:15551"`.

4. **Фикс SSL в Python на macOS (`CERTIFICATE_VERIFY_FAILED` при загрузке `frida-server`):**
   - Либо запустить установщик сертификатов Python:
     ```bash
     bash /Applications/Python\ 3.*/Install\ Certificates.command
     ```
   - Либо через `certifi` в `.venv`:
     ```bash
     pip install certifi
     export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")
     ```
   - Либо скачать `frida-server` системным `curl`:
     ```bash
     VER=$(python -c "import frida; print(frida.__version__)")
     mkdir -p assets
     curl -L --progress-bar -o "assets/frida-server-${VER}-android-x86_64.xz" \
       "https://github.com/frida/frida/releases/download/${VER}/frida-server-${VER}-android-x86_64.xz"
     python -c "import frida, lzma, pathlib; ver=frida.__version__; p=pathlib.Path(f'assets/frida-server-{ver}-android-x86_64.xz'); p.with_suffix('').write_bytes(lzma.open(p).read()); print('OK')"
     ```
