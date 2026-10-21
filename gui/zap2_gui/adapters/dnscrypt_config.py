"""Шифрованный DNS через системный dnscrypt-proxy: готовый конфиг и точные команды.

Свой процесс dnscrypt-proxy программа пока не запускает: чтобы слушать порт 53, нужен root,
а системный пакет dnscrypt-proxy уже умеет это через свою systemd-службу. Программа
готовит минимальный конфиг под выбранный DoH-сервер и показывает команды — пользователь
видит и выполняет их сам. После этого DNS в NetworkManager ставится на 127.0.0.1.
"""

from __future__ import annotations

import shutil

from ..models.dns_catalog import DnsProvider, doh_stamp

SYSTEM_CONFIG = "/etc/dnscrypt-proxy/dnscrypt-proxy.toml"
LISTEN = "127.0.0.1:53"


def dnscrypt_available() -> bool:
    return shutil.which("dnscrypt-proxy") is not None


def dnscrypt_config(provider: DnsProvider) -> str:
    name = "zap2-" + provider.provider_id
    return "\n".join([
        f"# z2guiflin: DoH через {provider.name} ({provider.doh})",
        f"listen_addresses = ['{LISTEN}']",
        f"server_names = ['{name}']",
        "ipv6_servers = false",
        "require_dnssec = false",
        "require_nolog = false",
        "require_nofilter = false",
        "cache = true",
        "# Адрес самого DoH-сервера известен из stamp: системный DNS для старта не нужен.",
        "bootstrap_resolvers = []",
        "ignore_system_dns = true",
        "",
        "[static]",
        f"  [static.'{name}']",
        f"  stamp = '{doh_stamp(provider)}'",
        "",
    ])


def dnscrypt_steps(config_path: str) -> list[str]:
    return [
        f"sudo cp -n {SYSTEM_CONFIG} {SYSTEM_CONFIG}.zap2-backup   # один раз: сохранить исходный конфиг",
        f"sudo install -m 644 {config_path} {SYSTEM_CONFIG}",
        "sudo systemctl enable --now dnscrypt-proxy.service",
        "затем в программе: «Локальный dnscrypt-proxy (127.0.0.1)» → Применить",
        f"откат: sudo install -m 644 {SYSTEM_CONFIG}.zap2-backup {SYSTEM_CONFIG} && sudo systemctl restart dnscrypt-proxy, DNS — «Вернуть»",
    ]


LOCAL_DNSCRYPT = DnsProvider(
    provider_id="local-dnscrypt",
    group="custom",
    name="Локальный dnscrypt-proxy (127.0.0.1)",
    ipv4=("127.0.0.1",),
    note="Работает, только если запущена служба dnscrypt-proxy с конфигом из программы.",
)


__all__ = ["LOCAL_DNSCRYPT", "dnscrypt_available", "dnscrypt_config", "dnscrypt_steps"]
