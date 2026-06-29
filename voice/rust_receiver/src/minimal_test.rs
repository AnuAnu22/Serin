/// Minimal test: spawns songbird Driver, connects, then idles.
/// If this also crashes, the bug is in songbird 0.6.0's driver initialization.
/// If it stays alive, the bug is in our event handlers or main loop.
use std::io::{self, Read};
use std::num::NonZeroU64;

use serde::Deserialize;
use songbird::driver::DecodeMode;
use songbird::id::{ChannelId, GuildId, UserId};
use songbird::{Config, ConnectionInfo};

#[derive(Debug, Deserialize)]
struct VoiceServerInfo {
    endpoint: String,
    token: String,
    session_id: String,
    guild_id: u64,
    channel_id: u64,
    user_id: u64,
}

fn nz(id: u64) -> NonZeroU64 {
    NonZeroU64::new(id).expect("ID must be non-zero")
}

#[tokio::main]
async fn main() {
    eprintln!("minimal-test starting");

    // Read ConnectionInfo from stdin
    let mut input = String::new();
    match io::stdin().read_line(&mut input) {
        Ok(0) => {
            eprintln!("ERROR: stdin closed");
            std::process::exit(1);
        }
        Ok(_) => {}
        Err(e) => {
            eprintln!("ERROR: read failed: {}", e);
            std::process::exit(1);
        }
    }

    let info: VoiceServerInfo = match serde_json::from_str(input.trim()) {
        Ok(info) => info,
        Err(e) => {
            eprintln!("ERROR: JSON parse failed: {}", e);
            std::process::exit(1);
        }
    };

    eprintln!("GOT_INFO guild={} channel={}", info.guild_id, info.channel_id);

    let config = Config::default()
        .decode_mode(DecodeMode::Decrypt)     // minimal mode — no decode
        .driver_timeout(Some(std::time::Duration::from_secs(60)));

    let mut driver = songbird::driver::Driver::new(config);
    eprintln!("DRIVER_CREATED");

    let connection_info = ConnectionInfo {
        channel_id: ChannelId(nz(info.channel_id)),
        endpoint: info.endpoint,
        guild_id: GuildId(nz(info.guild_id)),
        session_id: info.session_id,
        token: info.token,
        user_id: UserId(nz(info.user_id)),
    };

    eprintln!("CONNECTING...");
    match driver.connect(connection_info).await {
        Ok(()) => {
            eprintln!("CONNECTED to voice channel");
        }
        Err(e) => {
            eprintln!("JOIN_FAILED: {}", e);
            std::process::exit(1);
        }
    }

    eprintln!("READY — idling for 30s");
    tokio::time::sleep(std::time::Duration::from_secs(30)).await;

    eprintln!("CLEANUP: disconnect");
    driver.leave();
    eprintln!("DONE");
}
