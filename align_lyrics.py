from pathlib import Path
import argparse, json
import stable_whisper


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("lyrics", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--model", default="medium")
    args = ap.parse_args()

    lines = [line.strip() for line in args.lyrics.read_text().splitlines() if line.strip()]
    result = stable_whisper.load_model(args.model).align(
        str(args.audio), "\n".join(lines), language="ko", original_split=True
    )
    if result is None:
        raise RuntimeError("alignment failed")

    segments = []
    for line, segment in zip(lines, result.segments, strict=True):
        words = [
            {"text": word.word.strip(), "start": word.start, "end": word.end}
            for word in segment.words if word.word.strip()
        ]
        if words:
            segments.append({"text": line, "start": words[0]["start"], "end": words[-1]["end"], "words": words})

    if len(segments) != len(lines):
        raise RuntimeError(f"aligned {len(segments)} of {len(lines)} lines")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(segments, ensure_ascii=False, indent=2) + "\n")
    assert all(a["end"] <= b["start"] for a, b in zip(segments, segments[1:]))
    print(f"aligned {len(segments)} lines and {sum(len(x['words']) for x in segments)} words")


if __name__ == "__main__":
    main()
