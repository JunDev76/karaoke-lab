from pathlib import Path
import argparse, csv, json
import librosa, mido, numpy as np, onnxruntime as ort


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("model", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()

    cfg = json.loads((args.model / "config.json").read_text())
    sr, step = cfg["samplerate"], cfg["timestep"]
    y, _ = librosa.load(args.audio, sr=sr, mono=True)
    sessions = {n: ort.InferenceSession(str(args.model / f"{n}.onnx")) for n in ("encoder", "segmenter", "estimator", "bd2dur")}
    notes = []

    # ponytail: fixed 20s chunks bound attention memory; replace with GAME's silence slicer if boundary artifacts matter.
    chunk_samples = sr * 20
    for offset in range(0, len(y), chunk_samples):
        wav = y[offset:offset + chunk_samples].astype(np.float32)[None]
        duration = np.array([wav.shape[1] / sr], np.float32)
        x_seg, x_est, mask = sessions["encoder"].run(None, {"waveform": wav, "duration": duration})
        known = np.zeros_like(mask, bool)
        boundaries = known.copy()
        for t in np.arange(8, dtype=np.float32) / 8:
            boundaries, = sessions["segmenter"].run(None, {
                "x_seg": x_seg, "language": np.array([0], np.int64), "known_boundaries": known,
                "prev_boundaries": boundaries, "t": np.array([t], np.float32), "maskT": mask,
                "threshold": np.array(.2, np.float32), "radius": np.array(2, np.int64),
            })
        durations, note_mask = sessions["bd2dur"].run(None, {"boundaries": boundaries, "maskT": mask})
        presence, scores = sessions["estimator"].run(None, {
            "x_est": x_est, "boundaries": boundaries, "maskT": mask, "maskN": note_mask,
            "threshold": np.array(.2, np.float32),
        })
        cursor = offset / sr
        for dur, present, score, valid in zip(durations[0], presence[0], scores[0], note_mask[0]):
            if not valid: break
            end = cursor + float(dur)
            if present and dur >= .08:
                notes.append((cursor, end, float(score)))
            cursor = end
        print(f"{min(offset + len(wav[0]), len(y))/len(y):.0%}", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.with_suffix(".csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(("start_time_s", "end_time_s", "pitch_midi")); w.writerows(notes)
    midi = mido.MidiFile(ticks_per_beat=480); track = mido.MidiTrack(); midi.tracks.append(track)
    tempo = mido.bpm2tempo(120); last_tick = 0
    for start, end, score in notes:
        on = round(mido.second2tick(start, midi.ticks_per_beat, tempo)); off = round(mido.second2tick(end, midi.ticks_per_beat, tempo))
        pitch = max(0, min(127, round(score)))
        track.append(mido.Message("note_on", note=pitch, velocity=80, time=max(0, on-last_tick))); last_tick=on
        track.append(mido.Message("note_off", note=pitch, velocity=0, time=max(1, off-last_tick))); last_tick=off
    midi.save(args.output.with_suffix(".mid"))
    print(f"saved {len(notes)} notes")


if __name__ == "__main__":
    main()
