//! temp_voice_test — Minimal voice receiver using songbird 0.6.0 + serenity
//!
//! Connects to Discord, joins a voice channel, receives DAVE-decrypted audio,
//! and outputs per-user PCM frames to stdout.
//!
//! Protocol (stdout):
//!   JOIN:{user_id}\n
//!   AUDIO:{user_id}:{pcm_len}\n followed by pcm_len raw bytes
//!   LEAVE:{user_id}\n
//!
//! Commands (stdin):
//!   LEAVE\n  — disconnect and exit
//!
//! Usage:
//!   cargo run --release -- --token TOKEN --guild-id G --channel-id C

use std::collections::HashMap;
use std::env;
use std::io::{self, BufRead, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use dashmap::DashMap;
use serenity::async_trait;
use serenity::client::{Client, Context, EventHandler};
use serenity::model::gateway::Ready;
use serenity::model::id::{ChannelId, GuildId, UserId};
use serenity::prelude::GatewayIntents;
use songbird::driver::DecodeMode;
use songbird::{Config, CoreEvent, Event, EventContext, EventHandler as VoiceEventHandler, SerenityInit};

// ---------------------------------------------------------------------------
// Args
// ---------------------------------------------------------------------------

struct Args {
    token: String,
    guild_id: u64,
    channel_id: u64,
}

fn parse_args() -> Args {
    let args: Vec<String> = env::args().collect();
    let mut token = String::new();
    let mut guild_id = 0u64;
    let mut channel_id = 0u64;

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--token" => { i += 1; token = args[i].clone(); }
            "--guild-id" => { i += 1; guild_id = args[i].parse().expect("invalid guild-id"); }
            "--channel-id" => { i += 1; channel_id = args[i].parse().expect("invalid channel-id"); }
            _ => eprintln!("Unknown arg: {}", args[i]),
        }
        i += 1;
    }

    if token.is_empty() || guild_id == 0 || channel_id == 0 {
        eprintln!("Usage: voice_receiver --token TOKEN --guild-id G --channel-id C");
        std::process::exit(1);
    }

    Args { token, guild_id, channel_id }
}

// ---------------------------------------------------------------------------
// Voice event handler — outputs PCM to stdout
// ---------------------------------------------------------------------------

struct Receiver {
    known_ssrcs: DashMap<u32, UserId>,
    active_users: DashMap<u32, bool>, // track who we've announced as JOIN'd
}

impl Receiver {
    fn new() -> Self {
        Self {
            known_ssrcs: DashMap::new(),
            active_users: DashMap::new(),
        }
    }

    fn stdout() -> io::Stdout {
        io::stdout()
    }

    fn flush_stdout() {
        let _ = io::stdout().flush();
    }
}

#[async_trait]
impl VoiceEventHandler for Receiver {
    async fn act(&self, ctx: &EventContext<'_>) -> Option<Event> {
        use EventContext as Ctx;

        match ctx {
            Ctx::SpeakingStateUpdate(speaking) => {
                if let Some(user_id) = speaking.user_id {
                    self.known_ssrcs.insert(speaking.ssrc, *user_id);
                }
            }

            Ctx::VoiceTick(tick) => {
                for (ssrc, data) in &tick.speaking {
                    // Resolve user_id from SSRC
                    let user_id = match self.known_ssrcs.get(ssrc) {
                        Some(entry) => entry.value().0,
                        None => continue, // unknown SSRC, skip
                    };

                    // Announce user if first time seeing them this tick batch
                    if !self.active_users.contains_key(ssrc) {
                        self.active_users.insert(*ssrc, true);
                        println!("JOIN:{}", user_id);
                        Self::flush_stdout();
                    }

                    // Output decoded PCM
                    if let Some(pcm) = data.decoded_voice.as_ref() {
                        if pcm.is_empty() {
                            continue;
                        }
                        let pcm_bytes = pcm.as_ref();
                        println!("AUDIO:{}:{}", user_id, pcm_bytes.len());
                        Self::flush_stdout();
                        // Write raw PCM bytes
                        io::stdout().write_all(pcm_bytes).ok();
                        Self::flush_stdout();
                    }
                }

                // Detect users who stopped speaking (were active but now in silent list)
                for ssrc in self.active_users.keys() {
                    if !tick.speaking.contains_key(ssrc) {
                        if let Some(user_id) = self.known_ssrcs.get(ssrc) {
                            println!("LEAVE:{}", user_id.0);
                            Self::flush_stdout();
                        }
                        self.active_users.remove(ssrc);
                    }
                }
            }

            Ctx::ClientDisconnect(disc) => {
                // Clean up all state for this user
                let uid = disc.user_id.0;
                self.known_ssrcs.retain(|_, v| v.0 != uid);
                self.active_users.retain(|ssrc, _| {
                    self.known_ssrcs.get(ssrc).is_none() || self.known_ssrcs.get(ssrc).map(|v| v.0) != Some(uid)
                });
            }

            _ => {}
        }

        None
    }
}

// ---------------------------------------------------------------------------
// Serenity event handler
// ---------------------------------------------------------------------------

struct Handler;

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, _ctx: Context, ready: Ready) {
        eprintln!("READY:{}", ready.user.name);
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info".parse().unwrap()),
        )
        .with_target(false)
        .with_writer(io::stderr) // logs go to stderr, audio to stdout
        .init();

    let args = parse_args();
    let guild_id = GuildId::new(args.guild_id);
    let channel_id = ChannelId::new(args.channel_id);

    // Minimal intents — just voice state tracking, no messages
    let intents = GatewayIntents::GUILD_VOICE_STATES;

    // Configure songbird with decode enabled
    let songbird_config = Config::default()
        .decode_mode(DecodeMode::Decode(songbird::driver::DecodeConfig::default()));

    let mut client = Client::builder(&args.token, intents)
        .event_handler(Handler)
        .register_songbird_from_config(songbird_config)
        .await
        .expect("Failed to create Discord client");

    // Join voice channel and register receiver
    let manager = songbird::get(&client.shard_container)
        .await
        .expect("Songbird not registered")
        .clone();

    {
        let handler_lock = manager.get_or_insert(guild_id);
        let mut handler = handler_lock.lock().await;

        let receiver = Arc::new(Receiver::new());
        handler.add_global_event(CoreEvent::SpeakingStateUpdate.into(), receiver.clone());
        handler.add_global_event(CoreEvent::VoiceTick.into(), receiver.clone());
        handler.add_global_event(CoreEvent::ClientDisconnect.into(), receiver.clone());

        eprintln!("JOINING:{}:{}", args.guild_id, args.channel_id);
    }

    // Start gateway in background
    let manager_clone = manager.clone();
    let shard_manager = client.shard_manager.clone();
    tokio::spawn(async move {
        if let Err(e) = client.start().await {
            eprintln!("Gateway error: {:?}", e);
            shard_manager.shutdown_all().await;
        }
    });

    // Wait for gateway to be ready, then join
    tokio::time::sleep(std::time::Duration::from_secs(3)).await;

    match manager_clone.join(guild_id, channel_id).await {
        Ok(_handle) => {
            eprintln!("CONNECTED");
            io::stderr().flush().ok();
        }
        Err(e) => {
            eprintln!("JOIN_FAILED:{}", e);
            std::process::exit(1);
        }
    }

    // Spawn stdin reader for commands (LEAVE)
    let manager_for_stdin = manager_clone.clone();
    let stdin_handle = tokio::spawn(async move {
        let stdin = io::stdin();
        for line in stdin.lock().lines() {
            match line {
                Ok(line) if line.trim() == "LEAVE" => {
                    eprintln!("LEAVING");
                    let _ = manager_for_stdin.remove(guild_id).await;
                    break;
                }
                Ok(_) => {}
                Err(_) => break,
            }
        }
    });

    // Wait for signal or stdin
    let ctrl_c = tokio::signal::ctrl_c();
    tokio::select! {
        _ = ctrl_c => {
            eprintln!("SHUTDOWN");
            let _ = manager_clone.remove(guild_id).await;
        }
        _ = stdin_handle => {
            eprintln!("SHUTDOWN");
        }
    }
}
