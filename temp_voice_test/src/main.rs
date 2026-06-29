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

use std::env;
use std::io::{self, Write};
use std::sync::Arc;

use dashmap::DashMap;
use serenity::async_trait;
use serenity::client::{Client, Context, EventHandler};
use serenity::model::gateway::Ready;
use serenity::model::id::{ChannelId, GuildId};
use serenity::prelude::GatewayIntents;
use songbird::driver::DecodeMode;
use songbird::Songbird;
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

#[derive(Clone)]
struct Receiver {
    known_ssrcs: DashMap<u32, u64>,
    active_users: DashMap<u32, bool>,
}

impl Receiver {
    fn new() -> Self {
        Self {
            known_ssrcs: DashMap::new(),
            active_users: DashMap::new(),
        }
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
                    self.known_ssrcs.insert(speaking.ssrc, user_id.0);
                }
            }

            Ctx::VoiceTick(tick) => {
                let mut active_keys: Vec<u32> = self.active_users.iter().map(|e| *e.key()).collect();

                for (ssrc, data) in &tick.speaking {
                    let user_id = match self.known_ssrcs.get(ssrc) {
                        Some(entry) => *entry,
                        None => continue,
                    };

                    // Announce user if first time seeing them
                    if !self.active_users.contains_key(ssrc) {
                        self.active_users.insert(*ssrc, true);
                        println!("JOIN:{}", user_id);
                        Self::flush_stdout();
                    }

                    // Remove from active_keys (they're still speaking)
                    active_keys.retain(|k| k != ssrc);

                    // Output decoded PCM
                    if let Some(pcm) = data.decoded_voice.as_ref() {
                        if pcm.is_empty() {
                            continue;
                        }
                        // decoded_voice is Vec<i16> (PCM samples), reinterpret as bytes
                        let pcm_bytes: &[u8] = unsafe {
                            std::slice::from_raw_parts(
                                pcm.as_ptr() as *const u8,
                                pcm.len() * std::mem::size_of::<i16>(),
                            )
                        };
                        println!("AUDIO:{}:{}", user_id, pcm_bytes.len());
                        Self::flush_stdout();
                        io::stdout().write_all(pcm_bytes).ok();
                        Self::flush_stdout();
                    }
                }

                // Users in active_keys were speaking last tick but not this tick
                for ssrc in active_keys {
                    if let Some(user_id) = self.known_ssrcs.get(&ssrc) {
                        println!("LEAVE:{}", *user_id);
                        Self::flush_stdout();
                    }
                    self.active_users.remove(&ssrc);
                }
            }

            Ctx::ClientDisconnect(disc) => {
                let uid = disc.user_id.0;
                self.known_ssrcs.retain(|_, v| *v != uid);
                // Clean up active_users for this user
                let ssrcs_to_remove: Vec<u32> = self.active_users.iter()
                    .filter_map(|entry| {
                        let ssrc = *entry.key();
                        self.known_ssrcs.get(&ssrc).map(|v| if *v == uid { Some(ssrc) } else { None }).flatten()
                    })
                    .collect();
                for ssrc in ssrcs_to_remove {
                    self.active_users.remove(&ssrc);
                }
            }

            _ => {}
        }

        None
    }
}

// ---------------------------------------------------------------------------
// Serenity event handler — captures Songbird manager on ready
// ---------------------------------------------------------------------------

struct Handler {
    songbird_holder: Arc<tokio::sync::Mutex<Option<Arc<Songbird>>>>,
}

#[async_trait]
impl EventHandler for Handler {
    async fn ready(&self, ctx: Context, ready: Ready) {
        eprintln!("READY:{}", ready.user.name);
        if let Some(manager) = songbird::get(&ctx).await {
            let mut lock = self.songbird_holder.lock().await;
            *lock = Some(manager);
            eprintln!("SONGBIRD_OK");
        }
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
        .with_writer(io::stderr)
        .init();

    let args = parse_args();
    let guild_id = GuildId::new(args.guild_id);
    let channel_id = ChannelId::new(args.channel_id);

    let intents = GatewayIntents::GUILD_VOICE_STATES;

    let songbird_config = Config::default()
        .decode_mode(DecodeMode::Decode(songbird::driver::DecodeConfig::default()));

    let songbird_holder: Arc<tokio::sync::Mutex<Option<Arc<Songbird>>>> =
        Arc::new(tokio::sync::Mutex::new(None));

    let handler = Handler {
        songbird_holder: songbird_holder.clone(),
    };

    let mut client = Client::builder(&args.token, intents)
        .event_handler(handler)
        .register_songbird_from_config(songbird_config)
        .await
        .expect("Failed to create Discord client");

    // Start gateway in background
    let shard_manager = client.shard_manager.clone();
    tokio::spawn(async move {
        if let Err(e) = client.start().await {
            eprintln!("Gateway error: {:?}", e);
            shard_manager.shutdown_all().await;
        }
    });

    // Wait for Songbird manager to become available
    eprintln!("WAITING_SONGBIRD");
    let manager: Arc<Songbird> = loop {
        {
            let lock = songbird_holder.lock().await;
            if let Some(ref m) = *lock {
                break m.clone();
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
    };

    // Set up voice receive events on the handler
    {
        let handler_lock = manager.get_or_insert(guild_id);
        let mut handler = handler_lock.lock().await;

        let receiver = Receiver::new();
        handler.add_global_event(CoreEvent::SpeakingStateUpdate.into(), receiver.clone());
        handler.add_global_event(CoreEvent::VoiceTick.into(), receiver.clone());
        handler.add_global_event(CoreEvent::ClientDisconnect.into(), receiver.clone());

        eprintln!("EVENTS_REGISTERED");
    }

    // Join voice channel
    eprintln!("JOINING:{}:{}", args.guild_id, args.channel_id);
    match manager.join(guild_id, channel_id).await {
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
    let manager_for_stdin = manager.clone();
    let stdin_handle = tokio::spawn(async move {
        use tokio::io::{AsyncBufReadExt, BufReader};
        let stdin = tokio::io::stdin();
        let mut reader = BufReader::new(stdin);
        let mut line = String::new();
        loop {
            line.clear();
            match reader.read_line(&mut line).await {
                Ok(0) => break,
                Ok(_) if line.trim() == "LEAVE" => {
                    eprintln!("LEAVING");
                    let _ = manager_for_stdin.remove(guild_id).await;
                    break;
                }
                Ok(_) => {}
                Err(_) => break,
            }
        }
    });

    // Wait for Ctrl+C or stdin EOF
    let ctrl_c = tokio::signal::ctrl_c();
    tokio::select! {
        _ = ctrl_c => {
            eprintln!("SHUTDOWN");
            let _ = manager.remove(guild_id).await;
        }
        _ = stdin_handle => {
            eprintln!("SHUTDOWN");
        }
    }
}
