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
python fixtures/demo/make_demo.py
ICP_SCOUT_CONFIG=config/icp.example.yaml ICP_SCOUT_DATA=data/example ICP_SCOUT_RECORDINGS=fixtures/llm \
  streamlit run app/streamlit_app.py --server.port 8502 --server.headless true
```

Then, in a second shell, take both at 1440x900 and 2x:

```sh
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless --window-size=1440,900 --force-device-scale-factor=2 --hide-scrollbars \
  --virtual-time-budget=10000 --screenshot="$PWD/docs/assets/demo-queue.png" \
  "http://localhost:8502/queue?lead=g900000010"
"$CHROME" --headless --window-size=1440,900 --force-device-scale-factor=2 --hide-scrollbars \
  --virtual-time-budget=10000 --screenshot="$PWD/docs/assets/demo-market.png" \
  "http://localhost:8502/"
```

Some Chrome versions capture only the loading skeleton (a blank page) this way,
because Streamlit renders over a websocket after the page loads. If the PNG is
blank, drive Chrome through the DevTools protocol instead: open the page, wait
about 14 seconds, then call `Page.captureScreenshot`. For the Queue shot, also
scroll the lead pane down by 300 px so the French quote and its English show.

Each screenshot must be 1 MB or less; if one is larger, retake it at
`--force-device-scale-factor=1.5` and note it here. (Both are under 400 KB at 2x.)

## Check before committing an image

- The top bar says "ICP Scout for Helio Desk" (the example config's fictional vendor).
- Every URL on screen ends in `.example`.
- No name from `private/` appears.
- The map is drawn and the funnel shows numbers.
- The lead pane shows the score breakdown and a French quote with its English.
- `bash scripts/leak-check.sh` passes in the main checkout, where `private/leak-terms.txt` exists.
