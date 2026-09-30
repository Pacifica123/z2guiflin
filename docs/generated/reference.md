# Генерируемый справочник текущих контрактов

Этот документ автоматически получен из исполняемых контрактов, парсера командной строки, схем состояния, требований возможностей и закреплённого происхождения ядра. Ручное изменение справочника запрещено: исправляется соответствующий источник и повторяется генерация. Проверка свежести входит в единый профиль приёмки. Полные структуры находятся в [reference.json](reference.json). Исторические документы описывают только свои этапы и не подменяют текущий контракт.

Версия продукта: `1.1.0`. Команды оболочки установленного пакета `--about`, `--support-bundle FILE`, `--find QUERY`, `--package-preflight` перечислены отдельно от канонического диспетчера.

| Действие | Эффект | Привилегия | CLI aliases |
|---|---|---|---|
| `runtime.contracts.show` | show | none | `--runtime-contracts` |
| `runtime.contracts.validate` | validate | none | `--validate-runtime-contracts` |
| `runtime.plan.start` | plan | none | `--runtime-plan start` |
| `runtime.plan.stop` | plan | none | `--runtime-plan stop` |
| `runtime.plan.status` | plan | none | `--runtime-plan status` |
| `runtime.logs.show` | show | none | `--runtime-log` |
| `runtime.logs.snapshot` | show | none | `--runtime-logs` |
| `runtime.owner-rules.plan.apply` | prepare | none | `--runtime-apply-plan` |
| `runtime.owner-rules.plan.revert` | prepare | none | `--runtime-revert-plan` |
| `runtime.owner-rules.apply` | apply | bounded-root | `--runtime-apply` |
| `runtime.owner-rules.revert` | revert | bounded-root | `--runtime-revert` |
| `runtime.owner-rules.reconcile` | reconcile | none | `--runtime-reconcile` |
| `runtime.session.start` | start | bounded-root | `--runtime-session-start` |
| `runtime.session.status` | show | none | `--runtime-session-status` |
| `runtime.session.stop` | stop | owner | `--runtime-session-stop` |
| `runtime.nft-state.show` | show | none | `--runtime-nft-state` |
| `runtime.kernel.status` | show | none | `--runtime-kernel-status` |
| `default.build.dependencies.inspect` | inspect | none | `--default-build-deps` |
| `default.build.plan` | prepare | none | `--default-build-plan` |
| `default.build.apply` | apply | owner | `--default-build` |
| `default.workflow.plan.start` | prepare | none | `--default-start-plan` |
| `default.workflow.plan.stop` | prepare | none | `--default-stop-plan` |
| `default.workflow.start` | start | bounded-root | `--default-start` |
| `default.workflow.status` | show | none | `--default-status` |
| `default.workflow.stop` | stop | bounded-root | `--default-stop` |
| `privileged.executor.status` | show | none | `--privileged-executor-status` |
| `privileged.executor.install-plan` | plan | none | `--privileged-executor-install-plan` |
| `gui.overview.show` | show | none | `--gui-first-overview` |
| `gui.launch` | launch | owner | `--gui` |
| `build.plan` | plan | none | `--build-plan` |
| `security.blocklist.status` | show | none | `--security-blocklist-status` |
| `security.blocklist.enable` | apply | owner | `--security-blocklist-enable` |
| `security.blocklist.enable-inbound` | apply | owner | `--security-blocklist-enable-inbound` |
| `security.blocklist.disable` | revert | owner | `--security-blocklist-disable` |
| `security.blocklist.update` | apply | owner | `--security-blocklist-update` |
| `security.blocklist.apply` | apply | bounded-root | `--security-blocklist-apply` |
| `security.blocklist.refresh` | apply | bounded-root | `--security-blocklist-refresh` |
| `security.blocklist.timer.plan` | plan | none | `--security-blocklist-timer-plan` |
| `security.blocklist.timer.install` | apply | bounded-root | `--security-blocklist-install-timer` |
| `security.blocklist.timer.remove` | revert | owner | `--security-blocklist-remove-timer` |
| `launch.composer.status` | show | none | `--launch-composer-status` |
| `launch.composer.plan` | plan | none | `--launch-composer-plan` |
| `launch.composer.start` | start | bounded-root | `--launch-composer-start` |
| `launch.composer.stop` | stop | owner | `--launch-composer-stop` |
| `discord.verification.plan` | plan | none | `--discord-verification-plan` |
| `discord.verification.template.create` | prepare | none | `--discord-verification-template` |
| `discord.endpoint.plan` | plan | none | `--discord-endpoint-plan` |
| `discord.endpoint.watch` | probe | none | `--discord-endpoint-watch` |
| `discord.endpoint.report` | show | none | `--discord-endpoint-report` |
| `discord.netlog.plan` | plan | none | `--discord-netlog-plan` |
| `har.plan` | plan | none | `--har-plan` |
| `har.analyze` | inspect | none | `--har-analyze` |
| `har.report` | show | none | `--har-report` |
| `har.workbench` | show | none | `--har-workbench` |
| `har.workbench.report` | show | none | `--har-workbench-report` |
| `har.group.plan` | plan | none | `--har-group-plan` |
| `discord.har.plan` | plan | none | `--discord-har-plan` |
| `discord.har.analyze` | inspect | none | `--discord-har-analyze` |
| `discord.har.report` | show | none | `--discord-har-report` |
| `discord.har.workbench` | show | none | `--discord-har-workbench` |
| `discord.har.workbench.report` | show | none | `--discord-har-workbench-report` |
| `discord.har.group.plan` | plan | none | `--discord-har-group-plan` |
| `discord.voice.profiles` | show | none | `--discord-voice-profiles` |
| `discord.dns.edge.plan` | plan | none | `--discord-dns-edge-plan` |
| `discord.dns.edge.check` | inspect | none | `--discord-dns-edge-check` |
| `external.reference.audit` | inspect | none | `--external-reference-audit` |
| `tunnel.connection.vless.import` | import | owner | `--tunnel-connection-import-vless` |
| `tunnel.connection.list` | show | none | `--tunnel-connections` |
| `tunnel.connection.select` | apply | owner | `--tunnel-select-connection` |
| `tor.backend.plan` | plan | none | `--tor-backend-plan` |
| `tor.backend.start` | start | owner | `--tor-backend-start` |
| `tor.backend.status` | show | none | `--tor-backend-status` |
| `tor.backend.stop` | stop | owner | `--tor-backend-stop` |
| `discord.tunnel.plan` | plan | none | `--discord-tunnel-plan` |
| `discord.tunnel.core.preflight` | inspect | none | `--discord-tunnel-core-preflight` |
| `discord.tunnel.start` | start | bounded-root | `--discord-tunnel-start` |
| `discord.tunnel.stop` | stop | owner | `--discord-tunnel-stop` |
| `discord.tunnel.status` | show | none | `--discord-tunnel-status` |
| `discord.tunnel.probe` | probe | none | `--discord-tunnel-probe` |
| `discord.tunnel.https.probe` | probe | none | `--discord-tunnel-https-probe` |
| `discord.tunnel.route.diagnose` | inspect | none | `--discord-tunnel-route-diagnose` |
| `discord.tunnel.evidence` | show | none | `--discord-tunnel-evidence` |
| `discord.tunnel.guided.run` | probe | none | `--discord-tunnel-guided-run` |
| `discord.tunnel.tun.plan` | plan | none | `--discord-tunnel-tun-plan` |
| `discord.proxy.route.plan` | plan | none | `--discord-proxy-route-plan` |
| `discord.socks.launch` | launch | owner | `--discord-launch-through-socks` |
| `discord.socks.stop` | launch | owner | `--discord-stop-launched` |
| `strategy.parser.preflight` | inspect | none | `--strategy-parser-preflight` |
| `runtime.plan.prepare` | prepare | none | `--runtime-prepare` |
| `runtime.plan.confirm` | confirm | owner | `--runtime-confirm` |
| `runtime.pretls.probe` | probe | none | `--runtime-pretls-probe` |
| `runtime.discord.pretls.guided.probe` | probe | none | `--runtime-discord-pretls-guided-probe` |
| `discord.observation.matrix.plan` | plan | none | `--discord-observation-matrix-plan` |
| `discord.observation.matrix.report` | show | none | `--discord-observation-matrix-report` |
| `discord.observation.matrix.run.row` | probe | none | `--discord-observation-matrix-run-row` |
| `service.plan` | plan | none | `--service-plan` |
| `service.apply` | apply | owner | `--service-apply` |
| `runtime.state.migrate` | apply | owner | `--runtime-migrate-state` |
| `gui.privileged-command.show` | show | none | `--gui-privileged-command` |
| `blockcheck.preflight` | inspect | none | `--blockcheck-preflight` |
| `blockcheck.plan` | plan | none | `--blockcheck-plan` |
| `blockcheck.build.plan` | plan | none | `--blockcheck-build-plan` |
| `blockcheck.build` | apply | bounded-root | `--blockcheck-build` |
| `blockcheck.run` | probe | bounded-root | `--blockcheck-run` |
| `blockcheck.last.log` | show | none | `--blockcheck-last-log` |
| `blockcheck.coverage` | inspect | none | `--blockcheck-coverage` |
| `blockcheck.service.policy` | show | none | `--blockcheck-service-policy` |
| `blockcheck.tournament` | inspect | none | `--blockcheck-tournament` |
| `blockcheck.strategy-validation.plan` | validate | none | `--blockcheck-validate-strategy-plan` |
| `blockcheck.strategy.export` | export | owner | `--blockcheck-export-strategies` |
| `preset.select` | apply | owner | `--select-preset` |
| `strategy.select` | apply | owner | `--select-strategy` |
| `preset.list` | list | none | `--list-presets` |
| `preset.show` | show | none | `--show-preset` |
| `preset.traffic-profile.show` | show | none | `--show-preset-profile` |
| `runtime-context.list` | list | none | `--list-profiles` |
| `runtime-context.show` | show | none | `--show-profile` |
| `strategy.list` | list | none | `--list-strategies` |
| `strategy.show` | show | none | `--show-strategy` |

Возможности: обязательный HTTP для updates.discord.com, discord.com; WebSocket gateway.discord.gg; Electron navigation vesktop-main-window. Отсутствующее доказательство остаётся UNKNOWN/NOT_RUN. Идентификаторы схем и SHA256 происхождения опубликованы в JSON; продукт, upstream, внешний core и evidence являются независимыми осями.
