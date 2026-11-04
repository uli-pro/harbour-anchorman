# Anchorman

Read and listen to EPUB 3 books with synchronized narration ("readalouds",
EPUB Media Overlays) on Sailfish OS. Read where you want to read, and continue
listening at exactly that sentence when you want to listen.

Readalouds can be created from an EPUB and an audiobook with
[Storyteller](https://storyteller-platform.dev/).

**Status:** early development, not usable yet.

## Building

Requires the [Sailfish SDK](https://docs.sailfishos.org/Tools/Sailfish_SDK/).

```
mkdir -p ~/build/anchorman && cd ~/build/anchorman
sfdk config target=SailfishOS-5.1.0.11-aarch64
sfdk build /path/to/harbour-anchorman
```

## Running tests

The Python modules in `python/anchorman/` (except `bridge.py`) use only the
standard library and are tested without the SDK. They must work with
Python 3.8 (Sailfish OS up to 5.0) and 3.11 (from 5.1).

```
cd /path/to/harbour-anchorman
PYTHONPATH=python python3 -B -m unittest discover -s tests -t .
```

With containers, for the Python versions found on devices:

```
for v in 3.8 3.11; do
  podman run --rm --security-opt label=disable -v "$PWD":/src:ro -w /src \
    -e PYTHONPATH=python docker.io/library/python:$v-slim \
    python -B -m unittest discover -s tests -t .
done
```

## AI assistance

This app is written with the help of an AI assistant (Claude by Anthropic).
All code is reviewed and understood by the human maintainer before it is merged.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
