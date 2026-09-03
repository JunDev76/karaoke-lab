from pathlib import Path
import argparse, csv
import numpy as np
import soundfile as sf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--duration", type=float, required=True)
    args = ap.parse_args()

    with args.csv.open() as f:
        notes = [
            (float(r["start_time_s"]), float(r["end_time_s"]), float(r["pitch_midi"]), int(r.get("velocity", 80)))
            for r in csv.DictReader(f)
            if float(r["end_time_s"]) > float(r["start_time_s"])
        ]

    rate = 48000
    audio = np.zeros(round(args.duration * rate), dtype=np.float32)
    for start_s, end_s, pitch, velocity in notes:
        start = max(0, round(start_s * rate))
        end = min(len(audio), round(end_s * rate))
        if end <= start:
            continue
        t = np.arange(end - start, dtype=np.float32) / rate
        frequency = 440 * 2 ** ((pitch - 69) / 12)
        wave = np.sin(2 * np.pi * frequency * t)
        fade = min(round(rate * .005), len(t) // 2)
        envelope = np.ones(len(t), dtype=np.float32)
        if fade:
            envelope[:fade] = np.linspace(0, 1, fade)
            envelope[-fade:] = np.linspace(1, 0, fade)
        gain = .045 * (.65 + .35 * velocity / 127)
        audio[start:end] += wave * envelope * gain

    peak = np.max(np.abs(audio))
    if peak > .95:
        audio *= .95 / peak
    stereo = np.column_stack((audio, audio))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, stereo, rate, subtype="PCM_24")
    assert len(stereo) == round(args.duration * rate) and np.isfinite(stereo).all() and np.max(np.abs(stereo)) > 0
    print(f"rendered {len(notes)} notes to {args.output}")


if __name__ == "__main__":
    main()
