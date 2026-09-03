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
            (float(r["start_time_s"]), float(r["end_time_s"]), round(float(r["pitch_midi"])), int(r.get("velocity", 80)))
            for r in csv.DictReader(f)
            if float(r["end_time_s"]) - float(r["start_time_s"]) >= 0.20 and 45 <= float(r["pitch_midi"]) <= 84
        ]

    # 20ms 단위 skyline으로 화음은 가장 높은 음 하나만 유지한다.
    step = 0.02
    frames = int(np.ceil(args.duration / step))
    melody = np.full(frames, -1, dtype=np.int16)
    selected = np.full(frames, -1, dtype=np.int32)
    for note_id, (start, end, pitch, _) in enumerate(notes):
        a, b = max(0, int(start / step)), min(frames, int(np.ceil(end / step)))
        replace = pitch > melody[a:b]
        melody[a:b][replace] = pitch
        selected[a:b][replace] = note_id

    rate = 48000
    audio = np.zeros(int(args.duration * rate), dtype=np.float32)
    i = 0
    while i < frames:
        note_id = selected[i]
        j = i + 1
        while j < frames and selected[j] == note_id:
            j += 1
        if note_id >= 0 and (j - i) * step >= 0.18:
            _, _, pitch, velocity = notes[note_id]
            start = int(i * step * rate)
            # 노래 전체를 흉내 내지 않고, 각 안정된 음의 앞부분만 짧게 안내한다.
            audible = min((j - i) * step * .65, .32)
            end = min(len(audio), start + int(audible * rate))
            t = np.arange(end - start, dtype=np.float32) / rate
            freq = 440 * 2 ** ((pitch - 69) / 12)
            wave = np.sin(2*np.pi*freq*t)
            attack, release = min(int(rate*.005), len(t)//2), min(int(rate*.025), len(t)//2)
            env = np.ones(len(t), dtype=np.float32)
            if attack: env[:attack] = np.linspace(0, 1, attack)
            if release: env[-release:] = np.linspace(1, 0, release)
            gain = .045 * (.65 + .35 * velocity / 127)
            audio[start:end] += wave * env * gain
        i = j

    stereo = np.column_stack((audio, audio))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, stereo, rate, subtype="PCM_24")
    assert len(stereo) == int(args.duration * rate) and np.max(np.abs(stereo)) > 0
    print(f"rendered {args.output} ({np.count_nonzero(melody >= 0)} voiced frames)")


if __name__ == "__main__":
    main()
