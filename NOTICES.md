# Notices

What this program is built from, and on what terms.

**This file is checked by the test suite.** Every dependency declared in
[pyproject.toml](pyproject.toml) — required or optional — must appear in the
table below, or `tests/test_notices.py` fails. A library shipped without its
licence reproduced is the kind of omission nobody notices until somebody else
does, so it is a failing build rather than a note in a review.

The *content* half of the acknowledgements is not here: it is **generated** from
[`twig_bb/packs.json`](twig_bb/packs.json), so a pack added to the
catalogue is credited without anyone having to remember. Run
`python -m twig_bb.notices` to print the whole thing.

## This program

| | |
|---|---|
| **Twitchy GLitchy Bang Bang (`twig-bb`)** | BSD-3-Clause — Mike C. Fletcher · <https://github.com/mcfletch/twig-bb> |

## Libraries it is built on

| Component | Licence | Home | Ships with |
|---|---|---|---|
| OpenGLContext | BSD-3-Clause | <https://github.com/mcfletch/openglcontext> | required |
| PyOpenGL | BSD-3-Clause | <https://github.com/mcfletch/pyopengl> | required |
| pyvrml97 | BSD-3-Clause | <https://github.com/mcfletch/pyvrml97> | required |
| omi_physics | BSD-3-Clause | <https://github.com/mcfletch/omi_physics> | required |
| omi_audio | MIT | <https://github.com/mcfletch/omi_audio> | required |
| numpy | BSD-3-Clause | <https://numpy.org/> | required |
| pillow | MIT-CMU | <https://python-pillow.org/> | required |
| miniaudio | MIT | <https://github.com/irmen/pyminiaudio> | **optional** (`pip install twig-bb[audio]`) |

**miniaudio is optional and the distinction matters here**, because a notice has
to be accurate about what a given install actually contains. It is not a
dependency on most machines and there is nothing to acknowledge when it is
absent. When it *is* installed it brings its own bundled C, all of it
permissively licensed:

| Bundled in miniaudio | Licence | Author |
|---|---|---|
| miniaudio | MIT / public domain | David Reid |
| stb_vorbis | MIT / public domain | Sean Barrett |
| dr_wav, dr_mp3, dr_flac | MIT / public domain | David Reid |

Nothing in that chain is copyleft, which is the reason it is the only audio
package this project takes: the convenient wrappers — `libsndfile`, PyAV,
`pydub` via ffmpeg — are LGPL or worse, and none of them may be a dependency of
a BSD library.

## Art shipped with this program

| | |
|---|---|
| The weapons and what they throw | **BSD-3-Clause** — Mike C. Fletcher, modelled for this project |
| The pickups and the medikit | **BSD-3-Clause** — Mike C. Fletcher, modelled for this project |
| The combatants' bodies, faces and hair | **CC0 1.0** — Quaternius, *Universal Base Characters* · <https://quaternius.com/packs/universalbasecharacters.html> |
| Everything else about the combatants — skeleton, suit, animation, sockets | **BSD-3-Clause** — Mike C. Fletcher, built for this project |

**Nothing here carries an obligation onto anyone who redistributes twig-bb**:
the models are either this project's own or public domain. Both are credited
anyway, because that is the rule for every piece of art here whether or not its
licence demands it — the next person to read those directories should not have
to guess which files carry one. How the models are built, and what makes them
readable in a map that places no lights, is recorded in
[`twig_bb/assets/weapons/CREDITS.md`](twig_bb/assets/weapons/CREDITS.md),
[`twig_bb/assets/items/CREDITS.md`](twig_bb/assets/items/CREDITS.md) and
[`twig_bb/assets/characters/CREDITS.md`](twig_bb/assets/characters/CREDITS.md).

CC0 asks for no attribution and gets it here regardless. Quaternius takes
support at <https://www.patreon.com/quaternius>.

**No audio files ship with this program at all**, and that is a decision rather
than a gap. Every sound a fight makes — the weapons, impacts, deaths and
explosions — is *synthesised* from numbers declared in
[`twig_bb/combatsound.py`](twig_bb/combatsound.py), through
OpenGLContext's own `audio.synth`. Arithmetic has no licence, so the game ships
with a full complement of sound, nothing to credit and nothing to check. A
voice in that table may name a file instead, which is how commissioned or CC0
content would replace a synthesised stand-in; anything that arrives that way is
credited here like the geometry above.

## Content this program can download

Not shipped — fetched to a per-user cache, at the user's request, and never
vendored into this repository. That is what keeps a BSD codebase BSD while
playing content under share-alike terms. The list is generated from the
catalogue; `twig-bb --list-packs` prints it, as does
`python -m twig_bb.notices`.

## Where the format knowledge came from

**No Quake, ioquake3 or Alien Arena engine source was read while writing this.**
Every format constant, layout and behaviour cites a numbered fact in
[`specs/`](specs/), and each of those documents records where its own facts came
from — published documentation, this project's own earlier BSD code, the bytes
of shipped content, or the Reader/Implementer wall of
[`specs/CLEAN-ROOM.md`](specs/CLEAN-ROOM.md). Where a fact could not be
established from a permitted source, the specification says so and marks the
implementation's answer as a **choice** rather than dressing it up as the
original's behaviour.
