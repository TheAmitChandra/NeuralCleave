/**
 * Voice recording helpers — capture microphone audio via MediaRecorder,
 * stream it to the gateway's binary WebSocket lane, and play back TTS
 * audio replies received as binary frames.
 *
 * Uses the existing gatewayWS singleton (no second socket needed). Text-frame
 * and binary-frame traffic share one connection; the gateway differentiates
 * them by WebSocket opcode.
 */

import { gatewayWS } from "./websocket";

export type AudioReplyHandler = (audio: ArrayBuffer) => void;

// Prefer OGG/Opus — WhisperSTT writes the bytes to a .ogg temp file on the
// gateway side. Fall back to webm/opus (Chrome default) or unspecified.
const MIME_PREFERENCE = [
  "audio/ogg;codecs=opus",
  "audio/webm;codecs=opus",
  "audio/ogg",
  "audio/webm",
];

function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const mime of MIME_PREFERENCE) {
    if (MediaRecorder.isTypeSupported(mime)) return mime;
  }
  return "";
}

export class VoiceRecorder {
  private recorder: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private _recording = false;

  get recording(): boolean {
    return this._recording;
  }

  async start(): Promise<void> {
    if (this._recording) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: false,
    });
    const mimeType = pickMimeType();
    this.recorder = mimeType
      ? new MediaRecorder(this.stream, { mimeType })
      : new MediaRecorder(this.stream);

    this.recorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        gatewayWS.sendBinary(e.data);
      }
    };

    // Emit a chunk every 500 ms for low-latency streaming transcription
    this.recorder.start(500);
    this._recording = true;
  }

  stop(): void {
    if (!this._recording) return;
    this.recorder?.stop();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.recorder = null;
    this.stream = null;
    this._recording = false;
  }

  toggle(): Promise<void> {
    if (this._recording) {
      this.stop();
      return Promise.resolve();
    }
    return this.start();
  }
}

/** Module-level singleton — shared by VoiceButton and any other caller. */
export const voiceRecorder = new VoiceRecorder();

/** Subscribe to binary TTS audio replies from the gateway. */
export function onAudioReply(fn: AudioReplyHandler): () => void {
  return gatewayWS.subscribeBinary(fn);
}

/**
 * Decode and play raw audio bytes using the Web Audio API.
 * Handles MP3, WAV, OGG, and any format the browser supports.
 * Silently no-ops on unsupported formats or decode errors.
 */
export async function playAudioBuffer(data: ArrayBuffer): Promise<void> {
  try {
    const ctx = new AudioContext();
    const decoded = await ctx.decodeAudioData(data.slice(0));
    const source = ctx.createBufferSource();
    source.buffer = decoded;
    source.connect(ctx.destination);
    source.start();
    source.onended = () => void ctx.close();
  } catch {
    // Unsupported audio format — TTS fallback path will have sent a text frame
  }
}
