//! Serin Voice Receiver — standalone songbird Driver binary for voice bridge.
//!
//! This binary is spawned by the Python RustVoiceBridge and communicates via
//! stdin/stdout. It creates a songbird Driver (no gateway — just UDP voice),
//! connects directly to Discord's voice servers, decodes incoming Opus audio
//! to PCM, and sends it to Python for VAD/transcription. It also accepts TTS
//! audio from Python and plays it through the voice channel.
//!
//! ## Architecture
//!
//! ```text
//! Python (RustVoiceBridge)
//!   │
//!   ├── stdin: JSON ConnectionInfo \n SPEAK:{len}\n{bytes} INTERRUPT SHUTDOWN
//!   │
//!   └── stdout: AUDIO:{uid}:{len}\n{bytes} JOIN:{uid} LEAVE:{uid} TTS_DONE
//! ```
//!
//! ## Stdout Event Protocol
//!
//! Events are written to stdout as newline-delimited text, sometimes followed
//! by binary payloads:
//!
//! - `AUDIO:{user_id}:{pcm_len}\n` + `pcm_len` bytes of raw 48kHz stereo i16 PCM
//!   Emitted every 20ms for each speaking user (50 fps). The PCM is decoded
//!   from Opus by songbird's voice tick handler.
//!
//! - `JOIN:{user_id}\n`
//!   Emitted when a user starts speaking (appears in VoiceTick.speaking).
//!
//! - `LEAVE:{user_id}\n`
//!   Emitted when a user stops speaking (disappears from VoiceTick.speaking).
//!
//! - `TTS_DONE\n`
//!   Emitted when a TTS audio track finishes playing (TrackEvent::End fires).
//!   This is the critical signal that tells Python to release the processing lock
//!   so the next user utterance can be transcribed immediately. Without this,
//!   Python would have to guess the TTS playback duration.
//!
//! ## TTS Playback Flow
//!
//! 1. Python sends `SPEAK:{len}\n` + WAV bytes
//! 2. The stdin reader thread receives the command and sends `StdinCommand::Speak`
//! 3. Main loop: writes WAV to `/tmp/serin_tts_output.wav`
//! 4. Creates a songbird File input from the WAV and plays via `driver.play_input()`
//! 5. Attaches a `TtsDoneNotifier` as a TrackEvent::End handler
//! 6. When track finishes: `TtsDoneNotifier.act()` sends `OutEvent::TtsDone`
//! 7. Main loop receives `TtsDone` → writes `TTS_DONE\n` to stdout
//! 8. Python reads `TTS_DONE` → `_release_lock()` on the audio processor
//!
//! ## Interrupt Handling
//!
//! Python can send `INTERRUPT\n` at any time to stop the current TTS track.
//! The main loop calls `handle.stop()` on the current TrackHandle, which
//! immediately silences the voice output.
//!
//! ## Shutdown
//!
//! `SHUTDOWN\n` causes the stdin reader to send `StdinCommand::Shutdown`,
//! which breaks the main loop, disconnects from voice, and exits cleanly.

use std::io::{self, Read, Write};
use std::num::NonZeroU64;
use std::sync::mpsc;

use async_trait::async_trait;
use dashmap::DashMap;
use flume;
use serde::Deserialize;
use songbird::driver::DecodeMode;
use songbird::id::{ChannelId, GuildId, UserId};
use songbird::events::{CoreEvent, Event, EventContext, EventHandler as VoiceEventHandler, TrackEvent};
use songbird::tracks::TrackHandle;
use songbird::{Config, ConnectionInfo};

/// Voice server connection info, deserialized from the first line of stdin (JSON).
#[derive(Debug, Deserialize)]
struct VoiceServerInfo {
    endpoint: String,
    token: String,
    session_id: String,
    guild_id: u64,
    channel_id: u64,
    user_id: u64,
}

// ── Outbound Events (from voice handler → main loop → stdout) ────────────
//
// These events are produced by the VoiceTick/SpeakingStateUpdate handler and
// consumed by the main loop's stdout writer. The channel is flume (unbounded),
// which allows the voice event handler to send without waiting.

/// Events sent from the VoiceTick handler to the main loop for stdout output.
enum OutEvent {
    /// Decoded PCM audio frame for a user (48kHz stereo i16, ~3840 bytes per frame).
    Audio(u64, Vec<u8>),
    /// User started speaking (appeared in VoiceTick.speaking).
    Join(u64),
    /// User stopped speaking (disappeared from VoiceTick.speaking).
    Leave(u64),
    /// TTS track finished playback — trigger processing lock release in Python.
    TtsDone,
}

// ── TTS Track End Handler ───────────────────────────────────────────────
//
// Songbird fires TrackEvent::End when an audio track finishes playing.
// This handler sends an OutEvent::TtsDone back to the main loop, which
// writes TTS_DONE to stdout. Python reads this and releases the processing
// lock, enabling immediate response to the next user utterance.
//
// Without this handler, Python would need to guess the TTS duration from
// the WAV byte count — fragile and imprecise. The songbird track end event
// fires precisely when the last sample has been mixed and sent to Discord.

/// Track event handler: sends TtsDone to the main loop when TTS playback finishes.
struct TtsDoneNotifier {
    out_tx: flume::Sender<OutEvent>,
}

#[async_trait]
impl VoiceEventHandler for TtsDoneNotifier {
    async fn act(&self, _ctx: &EventContext<'_>) -> Option<Event> {
        let _ = self.out_tx.send_async(OutEvent::TtsDone).await;
        None  // Don't re-register — one-shot handler
    }
}

// ── Voice Event Receiver ────────────────────────────────────────────────
//
// This struct is registered as a global event handler on the songbird Driver.
// It processes SpeakingStateUpdate, VoiceTick, and ClientDisconnect events.
//
// Thread safety: known_ssrcs and active_users use DashMap (lock-free concurrent
// hashmap) so the handler can be called from any songbird thread.

/// Maps Discord SSRCs to user IDs and tracks active speakers.
///
/// SSRC (Synchronization Source) is a 32-bit identifier in RTP that uniquely
/// identifies each audio stream in a Discord voice channel. The SpeakingStateUpdate
/// event tells us which user_id owns which SSRC. The VoiceTick event then gives
/// us decoded PCM audio indexed by SSRC.
#[derive(Clone)]
struct Receiver {
    known_ssrcs: DashMap<u32, u64>,
    active_users: DashMap<u32, bool>,
    out_tx: flume::Sender<OutEvent>,
}

impl Receiver {
    fn new(out_tx: flume::Sender<OutEvent>) -> Self {
        Self {
            known_ssrcs: DashMap::new(),
            active_users: DashMap::new(),
            out_tx,
        }
    }
}

#[async_trait]
impl VoiceEventHandler for Receiver {
    async fn act(&self, ctx: &EventContext<'_>) -> Option<Event> {
        use EventContext as Ctx;

        match ctx {
            // ── Speaking State Update ─────────────────────────────────────
            // Discord fires this when a user starts/stops transmitting.
            // We record the SSRC→UserID mapping for use in VoiceTick.
            Ctx::SpeakingStateUpdate(speaking) => {
                if let Some(user_id) = speaking.user_id {
                    self.known_ssrcs.insert(speaking.ssrc, user_id.0);
                    eprintln!("SPEAKING ssrc={} user={}", speaking.ssrc, user_id.0);
                }
            }

            // ── Voice Tick ────────────────────────────────────────────────
            // This fires every 20ms (50fps) and contains decoded Opus audio
            // for every currently speaking user. We:
            //   1. Iterate the speaking map → send Join + Audio events
            //   2. Track which SSRCs were active this tick
            //   3. SSRCs that were active last tick but not this tick → Leave
            Ctx::VoiceTick(tick) => {
                // Copy current active keys before modification
                let mut active_keys: Vec<u32> =
                    self.active_users.iter().map(|e| *e.key()).collect();

                for (ssrc, data) in &tick.speaking {
                    // Resolve user ID from SSRC mapping (fall back to SSRC as raw ID)
                    let user_id = match self.known_ssrcs.get(ssrc) {
                        Some(entry) => *entry,
                        None => *ssrc as u64,
                    };

                    // First time seeing this SSRC this session → send Join
                    if !self.active_users.contains_key(ssrc) {
                        self.active_users.insert(*ssrc, true);
                        let _ = self.out_tx.send(OutEvent::Join(user_id));
                    }

                    // Remove from active_keys — this SSRC is still speaking
                    active_keys.retain(|k| k != ssrc);

                    // If there's decoded PCM, send it to Python
                    if let Some(pcm) = data.decoded_voice.as_ref() {
                        if pcm.is_empty() {
                            continue;
                        }
                        // SAFETY: songbird provides decoded_voice as &[i16].
                        // We reinterpret the buffer as &[u8] for transmission.
                        // pcm.len() * 2 bytes = total PCM payload length.
                        let pcm_bytes: &[u8] = unsafe {
                            std::slice::from_raw_parts(
                                pcm.as_ptr() as *const u8,
                                pcm.len() * std::mem::size_of::<i16>(),
                            )
                        };
                        let _ = self.out_tx.send(OutEvent::Audio(user_id, pcm_bytes.to_vec()));
                    }
                }

                // SSRCs that were active last tick but not this tick → they stopped speaking
                for ssrc in active_keys {
                    if let Some(user_id) = self.known_ssrcs.get(&ssrc) {
                        let _ = self.out_tx.send(OutEvent::Leave(*user_id));
                    }
                    self.active_users.remove(&ssrc);
                }
            }

            Ctx::RtpPacket(_packet) => {
                // Raw RTP packets — not needed since VoiceTick gives us decoded audio.
                // Keeping this match arm explicit to document that we intentionally skip it.
            }

            Ctx::ClientDisconnect(disc) => {
                let uid = disc.user_id.0;
                eprintln!("DISCONNECT user={}", uid);
                self.known_ssrcs.retain(|_, v| *v != uid);
                // Remove from active_users as well
                let ssrcs_to_remove: Vec<u32> = self
                    .active_users
                    .iter()
                    .filter_map(|entry| {
                        let ssrc = *entry.key();
                        self.known_ssrcs
                            .get(&ssrc)
                            .and_then(|v| if *v == uid { Some(ssrc) } else { None })
                    })
                    .collect();
                for ssrc in ssrcs_to_remove {
                    self.active_users.remove(&ssrc);
                }
            }

            _ => {}
        }

        None  // Keep handlers registered
    }
}

// ── Stdout Writer ───────────────────────────────────────────────────────
//
// Writes OutEvents to stdout in the binary protocol format.
// Audio payloads are written as: header\n + raw bytes
// All other events are written as: PREFIX:payload\n

/// Write an OutEvent to stdout (line + optional binary payload).
fn write_out_event(event: OutEvent) {
    match event {
        OutEvent::Audio(user_id, pcm) => {
            // Format: AUDIO:{user_id}:{pcm_len}\n followed by pcm_len raw PCM bytes
            let header = format!("AUDIO:{}:{}\n", user_id, pcm.len());
            let mut stdout = io::stdout().lock();
            let _ = stdout.write_all(header.as_bytes());
            let _ = stdout.write_all(&pcm);
            let _ = stdout.flush();
        }
        OutEvent::Join(user_id) => {
            let _ = writeln!(io::stdout(), "JOIN:{}", user_id);
        }
        OutEvent::Leave(user_id) => {
            let _ = writeln!(io::stdout(), "LEAVE:{}", user_id);
        }
        OutEvent::TtsDone => {
            // TTS_DONE is a simple line with no payload.
            // Python's RustStdoutReader checks for exact match "TTS_DONE".
            let _ = writeln!(io::stdout(), "TTS_DONE");
        }
    }
}

// ── Stdin Commands (from Python → main loop) ────────────────────────────

/// Commands parsed from the stdin protocol by the stdin reader thread.
enum StdinCommand {
    /// Play TTS audio: SPEAK:{len}\n followed by len bytes of WAV data
    Speak(Vec<u8>),
    /// Stop current TTS playback immediately
    Interrupt,
    /// Graceful shutdown
    Shutdown,
}

/// Spawn a thread that reads stdin commands in a blocking loop.
///
/// The stdin protocol is line-oriented:
///   - Lines ending with \n are parsed as commands
///   - SPEAK:{len}\n is followed by exactly len bytes of binary audio data
///   - INTERRUPT and SHUTDOWN are standalone lines
///
/// Threading: stdin must be read in a blocking thread because the main
/// async loop can't block on stdin. Commands are sent over an mpsc channel
/// to the main loop.
fn spawn_stdin_reader() -> mpsc::Receiver<StdinCommand> {
    let (tx, rx) = mpsc::channel();

    std::thread::spawn(move || {
        let stdin = io::stdin();
        let mut reader = stdin.lock();

        loop {
            // Read one byte at a time until we hit \n
            let mut line = Vec::new();
            let mut buf = [0u8; 1];
            loop {
                match reader.read(&mut buf) {
                    Ok(0) => {
                        let _ = tx.send(StdinCommand::Shutdown);
                        return;
                    }
                    Ok(_) => {
                        if buf[0] == b'\n' {
                            break;
                        }
                        line.push(buf[0]);
                    }
                    Err(_) => {
                        let _ = tx.send(StdinCommand::Shutdown);
                        return;
                    }
                }
            }

            let line_str = match String::from_utf8(line) {
                Ok(s) => s,
                Err(_) => continue,
            };

            if line_str.starts_with("SPEAK:") {
                // Format: SPEAK:{audio_len}
                // Followed by exactly audio_len bytes of WAV data
                if let Ok(audio_len) = line_str[6..].trim().parse::<usize>() {
                    let mut audio_bytes = vec![0u8; audio_len];
                    let mut total_read = 0;
                    while total_read < audio_len {
                        match reader.read(&mut audio_bytes[total_read..]) {
                            Ok(0) => {
                                let _ = tx.send(StdinCommand::Shutdown);
                                return;
                            }
                            Ok(n) => total_read += n,
                            Err(_) => {
                                let _ = tx.send(StdinCommand::Shutdown);
                                return;
                            }
                        }
                    }
                    let _ = tx.send(StdinCommand::Speak(audio_bytes));
                }
            } else if line_str.trim() == "INTERRUPT" {
                let _ = tx.send(StdinCommand::Interrupt);
            } else if line_str.trim() == "SHUTDOWN" {
                let _ = tx.send(StdinCommand::Shutdown);
                return;
            }
        }
    });

    rx
}

fn nz(id: u64) -> NonZeroU64 {
    NonZeroU64::new(id).expect("ID must be non-zero")
}

// ── Entry Point ─────────────────────────────────────────────────────────

#[tokio::main]
async fn main() {
    // Initialize tracing to stderr (eprintln! is used for diagnostics).
    // stdout is reserved for the binary protocol events.
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info,serin=debug".parse().unwrap()),
        )
        .with_target(false)
        .with_writer(io::stderr)
        .init();

    eprintln!("serin-voice-receiver v4.0.0 starting (sole voice connection)");

    // ── Read ConnectionInfo from stdin (first and only line of JSON) ────
    let mut input = String::new();
    match io::stdin().read_line(&mut input) {
        Ok(0) => {
            eprintln!("ERROR: stdin closed before ConnectionInfo");
            std::process::exit(1);
        }
        Ok(_) => {}
        Err(e) => {
            eprintln!("ERROR: failed to read ConnectionInfo: {}", e);
            std::process::exit(1);
        }
    }

    let server_info: VoiceServerInfo = match serde_json::from_str(input.trim()) {
        Ok(info) => info,
        Err(e) => {
            eprintln!("ERROR: invalid ConnectionInfo JSON: {}", e);
            eprintln!("  Received: {}", input.trim());
            std::process::exit(1);
        }
    };

    eprintln!(
        "GOT_INFO guild={} channel={} endpoint={}",
        server_info.guild_id, server_info.channel_id, server_info.endpoint
    );

    // ── Songbird Driver Setup ────────────────────────────────────────────
    // The Driver is the core of songbird's voice handling. It manages the
    // UDP voice connection, Opus encode/decode, and audio mixing.
    //
    // DecodeMode::Decode enables Opus → PCM decoding so we get raw audio.
    // driver_timeout(60s) prevents the driver from hanging forever if Discord
    // disconnects.

    let songbird_config = Config::default()
        .decode_mode(DecodeMode::Decode(songbird::driver::DecodeConfig::default()))
        .driver_timeout(Some(std::time::Duration::from_secs(60)));

    let mut driver = songbird::driver::Driver::new(songbird_config);

    // ── Event Channel ────────────────────────────────────────────────────
    // The flume channel connects the voice event handler (Receiver) to the
    // main loop. Events from SpeakingStateUpdate/VoiceTick are sent here.
    let (out_tx, out_rx) = flume::unbounded::<OutEvent>();
    let receiver = Receiver::new(out_tx.clone());
    driver.add_global_event(CoreEvent::SpeakingStateUpdate.into(), receiver.clone());
    driver.add_global_event(CoreEvent::VoiceTick.into(), receiver.clone());
    driver.add_global_event(CoreEvent::ClientDisconnect.into(), receiver.clone());
    eprintln!("EVENTS_REGISTERED");

    // ── Build ConnectionInfo ─────────────────────────────────────────────
    let connection_info = ConnectionInfo {
        channel_id: ChannelId(nz(server_info.channel_id)),
        endpoint: server_info.endpoint,
        guild_id: GuildId(nz(server_info.guild_id)),
        session_id: server_info.session_id,
        token: server_info.token,
        user_id: UserId(nz(server_info.user_id)),
    };

    eprintln!("CONNECTING to voice...");

    // ── Connect to Discord Voice ─────────────────────────────────────────
    // This establishes the UDP voice connection. The driver handles the
    // entire DTLS/SRTP handshake internally.
    match driver.connect(connection_info).await {
        Ok(()) => {
            eprintln!("CONNECTED to voice channel");
        }
        Err(e) => {
            eprintln!("JOIN_FAILED: {}", e);
            std::process::exit(1);
        }
    }

    eprintln!("READY — listening for audio and waiting for TTS commands");

    // ── Main Loop Variables ──────────────────────────────────────────────
    let stdin_rx = spawn_stdin_reader();
    let wav_path = "/tmp/serin_tts_output.wav";
    let mut current_handle: Option<TrackHandle> = None;

    // ── Main Loop ────────────────────────────────────────────────────────
    // Polls two sources:
    //   1. out_rx — events from the voice handler (audio, join, leave)
    //   2. stdin_rx — commands from Python (speak, interrupt, shutdown)
    //
    // The loop runs at ~20Hz (50ms sleep between iterations), which is fast
    // enough for voice frame delivery (every 20ms via the handler) while
    // keeping CPU usage low.

    loop {
        // ── Process outbound events (from voice handler) ───────────────
        // Drain all pending events before checking stdin to ensure timely
        // delivery of audio frames and status changes.
        while let Ok(event) = out_rx.try_recv() {
            write_out_event(event);
        }

        // ── Process stdin commands (from Python) ───────────────────────
        match stdin_rx.try_recv() {
            Ok(StdinCommand::Speak(audio_bytes)) => {
                let len = audio_bytes.len();
                eprintln!("TTS: received {} bytes for playback", len);

                // Stop any currently playing track before starting a new one.
                // This is what enables interrupt-to-replace — a new SPEAK
                // command stops the previous TTS immediately.
                if let Some(handle) = current_handle.take() {
                    let _ = handle.stop();
                }

                // Write the WAV data to a temp file and play it through
                // the songbird Driver. Using a File input is the simplest
                // approach — songbird handles all format detection from the
                // WAV header.
                match std::fs::write(wav_path, &audio_bytes) {
                    Ok(()) => {
                        let input = songbird::input::File::new(wav_path);
                        let handle = driver.play_input(input.into());

                        // ── Track End Handler ──────────────────────────
                        // Attach a TtsDoneNotifier that sends TTS_DONE when
                        // the track finishes playing. This is the critical
                        // signal for the Python processing lock lifecycle.
                        if let Err(e) = handle.add_event(
                            Event::Track(TrackEvent::End),
                            TtsDoneNotifier { out_tx: out_tx.clone() },
                        ) {
                            eprintln!("TTS: failed to add track end handler: {}", e);
                        }
                        current_handle = Some(handle);
                        eprintln!("TTS: playing through voice channel");
                    }
                    Err(e) => {
                        eprintln!("TTS: failed to write WAV file: {}", e);
                    }
                }
            }

            Ok(StdinCommand::Interrupt) => {
                eprintln!("TTS: interrupt received");
                if let Some(handle) = current_handle.take() {
                    let _ = handle.stop();
                    eprintln!("TTS: playback stopped");
                }
                let _ = std::fs::remove_file(wav_path);
            }

            Ok(StdinCommand::Shutdown) | Err(mpsc::TryRecvError::Disconnected) => {
                eprintln!("SHUTDOWN: stdin closed");
                break;
            }

            Err(mpsc::TryRecvError::Empty) => {}
        }

        // Sleep to yield the CPU — the voice handler runs on songbird's
        // internal executor and doesn't block on this loop.
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
    }

    // ── Cleanup ──────────────────────────────────────────────────────────
    if let Some(handle) = current_handle.take() {
        let _ = handle.stop();
    }

    eprintln!("CLEANUP: disconnecting from voice");
    driver.leave();
    let _ = std::fs::remove_file(wav_path);
    eprintln!("DONE");
}
