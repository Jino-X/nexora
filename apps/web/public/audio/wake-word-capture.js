/**
 * AudioWorklet for the on-device wake word: collects microphone samples (mono, at the AudioContext's rate) and
 * posts them to the page in blocks of 2,048. The page relays them to the wake word worker. Served as a static file,
 * so it loads under the site's Content Security Policy without blob: URLs.
 */
class WakeWordCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.block = new Float32Array(2048);
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      let offset = 0;
      while (offset < channel.length) {
        const n = Math.min(channel.length - offset, this.block.length - this.filled);
        this.block.set(channel.subarray(offset, offset + n), this.filled);
        this.filled += n;
        offset += n;
        if (this.filled === this.block.length) {
          const out = this.block;
          this.port.postMessage(out, [out.buffer]);
          this.block = new Float32Array(2048);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("nexora-wake-word-capture", WakeWordCapture);
