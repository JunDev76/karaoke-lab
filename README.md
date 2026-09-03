# Karaoke Lab

A small prototype for testing building blocks of a future karaoke application.

## What it tests

- Pitch extraction with [GAME](https://github.com/openvpi/GAME)
- Melody guide audio generation from extracted notes
- Real-time playback using macOS Audio Toolbox and Rubber Band
- Key, tempo, seek, and per-track volume controls
- A minimal local web interface

This is an experiment, not a production-ready karaoke application.

## Repository setup

Clone the repository with its submodules:

```sh
git clone --recurse-submodules <repository-url>
```

Existing clones can initialize them with:

```sh
git submodule update --init --recursive
```

## Local files

Audio inputs, generated outputs, model weights, virtual environments, and build artifacts are intentionally excluded from Git. Obtain model files from their respective upstream projects and use only audio you are authorized to process.

## Third-party software

- [GAME](https://github.com/openvpi/GAME) is included as a submodule and is licensed under the MIT License.
- [Rubber Band Library](https://github.com/breakfastquay/rubberband) is included as a submodule and is licensed by its upstream project under the GNU GPL unless a commercial license applies.

Review each upstream project's documentation and license before redistribution or commercial use.
