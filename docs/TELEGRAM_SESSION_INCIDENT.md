# Telegram session incident runbook

## Scope

Commit `d07a6d95b069976aee9a662e91873905ec7e6b49` added these runtime files:

- `apps/api/sinpes_bot_session.session` (a reusable Telethon authorization database)
- `apps/api/sinpes.db-wal`
- `apps/api/sinpes.db-shm`

Removing them in a new commit does not remove their earlier Git objects. Treat the
Telethon authorization as compromised until Telegram has revoked it.

## 1. Revoke and replace the authorization

Perform this during a short ingestion-bot maintenance window:

1. Stop `sinpes-telethon.service` so it cannot write or recreate the old session.
2. Make an encrypted backup of the production database. Do not back up or reuse the
   exposed Telethon session.
3. From a trusted host holding the current production session, call Telethon
   `client.log_out()` once. This invalidates that authorization key at Telegram.
4. In `@BotFather`, use `/revoke` for the ingestion bot, record the replacement token
   in the production secret store as `TELEGRAM_ORACLE_BOT_TOKEN`, and remove the old
   token everywhere. Do not paste either token into Git or a ticket.
5. Set `TELEGRAM_SESSION_DIR` to a persistent directory outside the checkout, owned by
   the service account with mode `0700` (for example
   `/opt/sinpes/data/telegram-sessions`). Delete the old production session database.
6. Restart `sinpes-telethon.service`. The hardened startup creates a new session with
   mode `0600`. Verify `/start` and one non-publishing ingestion test before reopening
   uploads.
7. Repeat token/session rotation for Writer or SEO only if their own session files or
   tokens were ever copied into Git. Their new sessions must use the same private
   session directory.

If the old session cannot be opened to call `log_out()`, rotate the bot token first,
remove the old session, create a new one, and confirm with Telegram support whether an
additional server-side authorization reset is required.

## 2. Purge the files from Git history

Coordinate a push freeze first. History rewriting changes every affected commit ID and
requires every collaborator and deployment checkout to re-clone.

```sh
git clone --mirror https://github.com/Sacratonis/sinpes.git sinpes-purge.git
cd sinpes-purge.git
git filter-repo --force --invert-paths \
  --path apps/api/sinpes_bot_session.session \
  --path apps/api/sinpes.db-wal \
  --path apps/api/sinpes.db-shm
git rev-list --all --objects | grep -E 'apps/api/(sinpes_bot_session\.session|sinpes\.db-(wal|shm))$'
```

The final verification command must print nothing. Have a second maintainer inspect
the rewritten mirror, temporarily permit force updates on protected branches, then:

```sh
git push --force --mirror origin
```

After the push:

1. Restore branch protection.
2. Ask GitHub Support to purge cached sensitive-data objects and pull-request refs.
3. Re-clone every developer and production checkout; do not merge an old clone back.
4. Confirm the three paths are absent from `git rev-list --all --objects` on a fresh
   clone.
5. Confirm the replacement Telegram token works and the revoked authorization does
   not.

Do not run the force push until the remediation commit is merged, the Telegram
authorization is revoked, backups are verified, and the maintenance window is active.
