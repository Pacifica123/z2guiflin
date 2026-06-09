# Workspace-профили

`profiles/` хранит пользовательские и проектные профили рабочего пространства. Профиль отвечает на вопрос: **с каким локальным набором данных и какой стратегией владелец сейчас работает**.

На Stage 7 профиль является read-only данными для GUI/CLI:

- он не запускает `make`;
- не вызывает `sudo`;
- не управляет `systemd`, firewall, `nftables` или `iptables`;
- не меняет hostlists автоматически;
- только связывает выбранную стратегию, build target и локальные файлы данных.

Формат намеренно простой JSON, чтобы владелец мог редактировать его вручную и видеть, что именно будет читать будущий GUI.

## v0.4-alpha Stage 4: Discord hostlist alignment

`profiles/hostlists/default.hosts` теперь является общим owner-maintained seed
для двух фиксированных service target preset-ов: `youtube-basic` и
`discord-desktop`. Это не включает скрытый runtime-switch и не гарантирует
одновременную работу сервисов, но устраняет практический разрыв: Discord targets,
проверенные через Blockcheck Lab, присутствуют в hostlist, который Default
workflow передаёт локальному `nfqws2`.

Минимальные Discord entries, добавленные на этой стадии:

```text
gateway.discord.gg
cdn.discordapp.com
media.discordapp.net
```


## v0.4-alpha Stage 7

Default hostlist теперь также покрывает `stable.dl2.discordapp.net`, потому что первая проверка desktop Discord зависла на updater-фазе `Checking for updates`. Этот target нужен для evidence-driven проверки updater/download layer и не включает voice/UDP.
