# Stage 7w — Discord SYN-data edge-flow v2c matrix

Stage 7v confirmed that `community-discord-syndata-edge-flow-v2b` is active when
`default.nfqws2.args` contains `discordapp.com` and `www.discordapp.com` in the
Discord hostlist branches. Owner testing then showed the next blocker:

```text
Flatpak Discord update-check: passed
main URL: https://discordapp.com/app?_=...
edge socket: can reach ESTAB
curl/Discord: times out after TLS ClientHello, before ServerHello/HTTP
```

That means v2b was a valid hostlist correction, but not a final Discord fix. The
next step is not to add more domains blindly. Stage 7w introduces a small
owner-selected matrix of v2c strategies that isolates the phase-zero pieces.

## Matrix variants

### `community-discord-syndata-edge-flow-v2c-send-only`

Keeps the first Discord edge branch:

```text
--payload=empty
--out-range=<s1
--lua-desync=send:tcp_md5:repeats=2
```

It intentionally removes the broad edge `syndata` / `rndsni` branch. Use it to
check whether the `syndata` phase is what prevents TLS ServerHello from coming
back after TCP reaches `ESTAB`.

### `community-discord-syndata-edge-flow-v2c-fixed-sni`

Keeps the v2b structure but changes the edge SYN-data modifier from random SNI to
a deterministic fake SNI:

```text
--lua-desync=syndata:blob=fake_default_tls:tls_mod=rnd,dupsid,sni=google.com
```

Use it to test whether `rndsni` is harmful on the current Linux/nfqws2 path.

### `community-discord-syndata-edge-flow-v2c-no-md5`

Removes `tcp_md5` from Discord-side send/hostfake profiles while keeping the
edge `syndata` branch. Use it to test whether MD5-marked fake packets are unsafe
for this route.

### `community-discord-syndata-edge-flow-v2c-host-first`

Moves `discordapp.com`/`discord.com` hostlist branches before the broad
Cloudflare edge-IP phase-zero branches. Use it to test whether the wide IP branch
shadows the more specific webapp host profile.

## Clean Flatpak note

`flatpak kill com.discordapp.Discord` saying the app is not running is the source
of truth for the Flatpak app. A leftover line such as:

```text
[bwrap] <defunct>
```

is a zombie process that has already exited and is waiting for its parent to reap
it. It is not a live Discord instance. It is still useful to run:

```bash
pgrep -a 'Discord|com.discordapp|zypak|bwrap'
```

but `<defunct>` should be treated as a cleanup artifact, not as proof that
Discord is still active.

## Manual checks for every variant

After selecting one variant and starting Default workflow, verify the actual args
file, not just the GUI strategy label:

```bash
grep -nE 'discordapp\.com|www\.discordapp\.com|hostlist-domains|tcp_md5|rndsni|sni=google' \
  .zap2/runtime/sessions/default.nfqws2.args
```

Then test the webapp host:

```bash
curl -4vk --connect-timeout 8 --max-time 20 \
  --resolve discordapp.com:443:162.159.130.233 \
  https://discordapp.com/app -o /dev/null
```

Interpretation ladder:

```text
SYN-SENT       -> still blocked before TCP establishment
ESTAB          -> TCP progressed
ClientHello    -> TLS started but no response yet
ServerHello    -> first real TLS response observed
HTTP/          -> webapp transport reached HTTP layer
```
