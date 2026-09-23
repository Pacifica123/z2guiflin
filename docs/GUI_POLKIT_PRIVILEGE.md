# GUI-запрос прав: sudo askpass + bounded executor

> **P02 current contract (2026-09-23).** Исторический путь, в котором `sudo -A`
> запускал `python -m zap2_gui.app` из writable workspace, удалён из standard runtime.
> GUI остаётся unprivileged; root выполняет только finite, Plan-bound действия через
> root-owned helper `/usr/local/libexec/zap2-runtime-executor`.

## Текущая цепочка

```text
PyQt button
  -> unprivileged Spec/Plan + owner confirmation
  -> SUDO_ASKPASS (только получение пароля владельца)
  -> sudo -A -- /usr/local/libexec/zap2-runtime-executor --execute --request-hash <hash>
  -> canonical JSON request bytes over stdin
  -> helper revalidates request hash + exact PlanHash/confirmation
  -> finite action
```

`SUDO_ASKPASS` helper находится в `.zap2/runtime/askpass/zap2-sudo-askpass` и
создаётся только непосредственно перед реальным owner-requested execution. Один
preview команды его не создаёт. Askpass запускается от обычного пользователя и
может импортировать `zap2_gui.askpass`; **root executor этот workspace Python не
импортирует**.

Пароль:

- не вводится в терминале;
- не сохраняется в `.zap2`;
- не пишется в runtime logs/receipts;
- используется только стандартным `sudo -A` askpass protocol.

## Что разрешено root executor

Helper принимает только фиксированные action IDs P02:

- observe owned nft table;
- check nft batch, связанный с confirmed Plan;
- execute nft batch, связанный с confirmed Plan;
- start `nfqws2` из exact confirmed Plan после повторной проверки входных bytes.

Он не принимает произвольный shell/argv, `PYTHONPATH`, произвольный executable
или пользовательский Python module. Source helper и установленный helper должны
иметь одинаковый SHA-256; установленный файл должен быть root-owned и не быть
writable для group/world.

## Installation / provenance

Установка helper является отдельным явным owner action и **не выполняется
`devctl start` автоматически**:

```bash
./run.sh --cli --privileged-executor-install-plan
sudo install -D -o root -g root -m 0755 -- \
  tools/privileged/zap2-runtime-executor \
  /usr/local/libexec/zap2-runtime-executor
./run.sh --cli --privileged-executor-status
```

`--privileged-executor-status` должен показать `ready` и одинаковые installed / project SHA-256.

## Privilege drop и runtime inputs

Owner UID/GID, queue selection, executable и runtime input digests входят в
immutable Plan. После подтверждения helper не выводит эти значения заново из
mutable environment. Он проверяет source bytes, копирует подтверждённые bytes в
root-owned `/run/zap2/...` и запускает staged `nfqws2`, который получает
`--uid=<confirmed uid>:<confirmed gid>`.

## Что P02 намеренно не расширяет

- privileged Discord pre-TLS GUI probe — staged/unsupported; используется
  owner-run read-only diagnostic lane;
- systemd/service effects остаются plan-only, пока нет отдельного bounded action;
- blockcheck остаётся отдельной development/experimental поверхностью и не
  расширяет standard root executor.
