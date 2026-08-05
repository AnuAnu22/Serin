# DAVE support ≠ receive support

**The one-line summary of the entire voice ordeal: by 2026 nearly every
Discord library advertised DAVE support, but none of them had an actively
maintained, actually-exercised implementation of the *receive* half. The gap
was never encryption — it was that nobody listens.**

## Why every library "supports DAVE"

Discord enforced end-to-end encryption (DAVE) for all voice on March 1st,
2026. Any library that couldn't do the MLS handshake and frame encryption
would leave its bots unable to even *join* voice. So DAVE support was
existential for the **send** path — music bots, soundboards, TTS — and every
maintained library shipped it: discord.py 2.7.1, py-cord, discord.js,
songbird 0.6.

## Why none of them could receive

~99% of voice bots only transmit. The receive path has always been the
ecosystem's unmaintained attic:

- **discord.py** — receive is not in the library at all; it lives in the
  third-party `discord-ext-voice-recv`, whose DAVE-compatible receiving
  existed only as an unmerged pull request (#54) that users pin via git ref.
- **songbird** — receive exists behind the `receive` feature flag and the
  docs say it's supported, but receive-under-DAVE had evidently never been
  run end-to-end upstream: see [[songbird-dave-offset-bug]] (every Opus
  decode fails) and [[songbird-clientconnect-patch]] (inbound audio
  unattributable / silently dropped). Both bugs are unreachable from the
  send path, which is why no music bot ever noticed them.
- **discord.js** — the one mature exception (`@discordjs/voice` receive +
  DAVE), at the cost of a Node runtime on a 50 fps audio path.

When DAVE landed, every library wired the new crypto into the path people
actually use. The receive path got, at best, untested plumbing that
advertised itself as working.

## Consequence for Serin

"Supported" in docs and search results meant *the code exists*, not *the code
runs*. Serin's receiver ([[gateway-less-voice-driver]]) is plausibly among
the first to push real DAVE-encrypted inbound audio through songbird's
receive path — which is why the failures had zero search results and took
days to isolate. The fixes were small; the discovery that they were needed
was the expensive part.

## Rule of thumb

When evaluating a library for voice **receive**, ignore the feature matrix.
Ask instead: *what actively maintained project uses this library's receive
path in production today?* If the answer is "none findable", budget for
debugging the library itself, not just your code.
