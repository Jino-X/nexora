# Wake word models

The on-device "Hey Nexora" wake word uses [openWakeWord](https://github.com/dscripka/openWakeWord) models. No
account or key is needed. This folder holds:

| File                   | Where it comes from                                                                                   |
| ---------------------- | ----------------------------------------------------------------------------------------------------- |
| `melspectrogram.onnx`  | `make wake-word-models` (or `pnpm --filter @nexora/web wake-word:models`) downloads it (ignored)      |
| `embedding_model.onnx` | Same command (git-ignored)                                                                            |
| `hey_nexora.onnx`      | Committed. Trained for "hey nexora" with openWakeWord's free Google Colab notebook; retrain to change |

`make wake-word-models ARGS="--test --force"` overwrites `hey_nexora.onnx` with the pre-trained "Hey Jarvis" model
(personal use only: CC BY-NC-SA 4.0); `git checkout` restores the trained model. See `docs/voice.md`.
