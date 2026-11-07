#!/bin/sh
# Camera modes (CAMERA_MODE, set in docker/.env by start.ps1):
#   per-trip  every new trip gets the next clip from CLIPS, from the start (rivian_model/klip_po_voznji.py). Default.
#   loop      one clip (VIDEO, a file name in the dataset folder) on a loop, all the time
#   test      a moving test pattern (no dataset needed; the model sees no driver)
#   off       no camera (e.g. the simulator feeds /telemetry instead)
# The dataset folder is mounted read-only at /dataset. Without clips, per-trip and loop fall back to the test pattern.
set -e
HOST="${COORDINATOR_HOST:-coordinator}"
PORT="${COORDINATOR_PORT:-8000}"
URL="ws://$HOST:$PORT/api/v1/camera/ws"
MODE="${CAMERA_MODE:-per-trip}"

SERIES="${MODEL_CAMERA:-05_23}"
has_clips() { ls /dataset/*_video_inCabin.mp4 >/dev/null 2>&1; }

if [ "$MODE" = "per-trip" ] || [ "$MODE" = "loop" ]; then
  if ! has_clips; then
    echo "camera: no *_video_inCabin.mp4 in the dataset folder (DATASET_DIR in docker/.env): test pattern instead"
    MODE=test
  fi
fi

# per-trip: the wanted clips that exist in this dataset, topped up to 3 with other clips of the model's camera series
# (every clip must match the driver zone the model was started with).
pick_clips() {
  picked=""
  for c in $CLIPS; do
    case "$c" in "$SERIES"_*) ;; *) echo "camera: skipping $c (not camera series $SERIES)" >&2; continue ;; esac
    if [ -f "/dataset/${c}_video_inCabin.mp4" ]; then picked="$picked $c"; else echo "camera: clip $c is not in the dataset, skipped" >&2; fi
  done
  count=$(echo $picked | wc -w)
  for f in /dataset/"$SERIES"_*_video_inCabin.mp4; do
    [ "$count" -ge 3 ] && break
    [ -f "$f" ] || continue
    c=$(basename "$f" _video_inCabin.mp4)
    case " $picked " in *" $c "*) continue ;; esac
    picked="$picked $c"
    count=$((count + 1))
  done
  echo $picked
}

case "$MODE" in
  per-trip)
    LIST=$(pick_clips)
    if [ -z "$LIST" ]; then
      echo "camera: no clips of camera series $SERIES in the dataset: test pattern instead"
      exec python tools/camera_stream.py --url "$URL"
    fi
    # shellcheck disable=SC2086  # LIST is a space-separated list on purpose
    exec python rivian_model/klip_po_voznji.py --host "$HOST" --port "$PORT" --dataset /dataset --klipovi $LIST
    ;;
  loop)
    exec python tools/camera_stream.py --url "$URL" --video "/dataset/${VIDEO:?set VIDEO to a clip file name}"
    ;;
  test)
    exec python tools/camera_stream.py --url "$URL"
    ;;
  off)
    echo "camera: off (CAMERA_MODE=off)"
    exec sleep infinity
    ;;
  *)
    echo "camera: unknown CAMERA_MODE '$MODE' (per-trip, loop, test, off)" >&2
    exit 2
    ;;
esac
