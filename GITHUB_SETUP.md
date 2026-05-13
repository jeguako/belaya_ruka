# Заливка в GitHub: jeguako/belaya_ruka

Репозиторий: **https://github.com/jeguako/belaya_ruka**

Локальная папка проекта: `/Users/temirkanseudzen/assistant-telegram-bot`

## Remote (уже настроено)

```bash
cd /Users/temirkanseudzen/assistant-telegram-bot
git remote -v
# origin → https://github.com/jeguako/belaya_ruka.git
```

## Push с вашей машины

```bash
cd /Users/temirkanseudzen/assistant-telegram-bot
git push -u origin main
```

Учётная запись должна иметь доступ к **jeguako/belaya_ruka** (логин `jeguako` + Personal Access Token с правом `repo`, или SSH-ключ, добавленный в аккаунт `jeguako`).

### Personal Access Token (HTTPS)

1. Войдите на GitHub как **jeguako**: https://github.com/settings/tokens  
2. Generate new token (classic), scope **repo**.  
3. При `git push` в качестве пароля вставьте токен.

### SSH

```bash
git remote set-url origin git@github.com:jeguako/belaya_ruka.git
git push -u origin main
```

Нужен SSH-ключ, добавленный в профиль **jeguako**.

## Важно

- Файл `.env` в репозиторий **не попадает** (см. `.gitignore`). Секреты только локально на сервере.
