# Images

Every image here is made from the example data and the example config. Nothing
comes from `private/`.

| Image | Source | What it shows |
|---|---|---|
| `pipeline.png` (2560x1280) | `src/pipeline.html` | The six stages, the scoring and the tiers. |
| `demo-queue.png` (2880x1800) | the example demo | The Queue with a lead open. |
| `demo-market.png` (2880x1800) | the example demo | The Market page: funnel and map. |

## Re-render the pipeline image

From the repo root:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --window-size=1280,640 --force-device-scale-factor=2 --hide-scrollbars \
  --screenshot="$PWD/docs/assets/pipeline.png" "file://$PWD/docs/assets/src/pipeline.html"
```

## Re-take the screenshots

```sh
.venv/bin/python fixtures/demo/make_demo.py
ICP_SCOUT_CONFIG=config/icp.example.yaml ICP_SCOUT_DATA=data/example ICP_SCOUT_RECORDINGS=fixtures/llm \
  .venv/bin/streamlit run app/streamlit_app.py --server.port 8502 --server.headless true
```

Then, in a second shell, take both at 1440x900 and 2x with `src/shoot.py`:

```sh
.venv/bin/python docs/assets/src/shoot.py "http://localhost:8502/queue?lead=g900000010" docs/assets/demo-queue.png
.venv/bin/python docs/assets/src/shoot.py "http://localhost:8502/" docs/assets/demo-market.png
```

Why a script and not `chrome --screenshot`: Streamlit renders over a websocket
after the page loads, so plain headless `--screenshot` can capture only the
loading skeleton (a blank page). `shoot.py` drives Chrome through the DevTools
protocol, waits 14 s, then captures. It needs only `websockets`, which the venv
already has. Options: `--scale` (default 2), `--wait` (seconds, default 14), and
`--scroll N` to scroll the lead pane down N px (default 0; the queue shot uses 0,
so the lead's name, score and breakdown show).

Each screenshot must be 1 MB or less; if one is larger, retake it with
`--scale 1.5` and note it here. (Both are under 400 KB at 2x.)

## Check before committing an image

- The top bar says "ICP Scout for Helio Desk" (the example config's fictional vendor).
- Every URL on screen ends in `.example`.
- No name from `private/` appears.
- The map is drawn and the funnel shows numbers.
- The lead pane shows the score breakdown. At `--scroll 0` the first signal's French quote sits just below the fold (its "As quoted / English" header shows); any French text that is on screen has its English next to it.
- `bash scripts/leak-check.sh` passes in the main checkout, where `private/leak-terms.txt` exists.
