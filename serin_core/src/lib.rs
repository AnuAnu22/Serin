//! serin_core — High-performance text processing for Serin Bot.
//!
//! Replaces Python hot loops with zero-allocation Rust:
//! - FTS5 query sanitization (single-pass)
//! - Thinking tag filtering (compiled regex)
//! - Natural language contraction replacement (single-pass regex)

use pyo3::prelude::*;
use regex::Regex;
use std::collections::HashMap;
use std::sync::LazyLock;

// ─── FTS5 Query Sanitizer ────────────────────────────────────────────────────

/// Sanitize a query string for SQLite FTS5 in a single pass.
/// Replaces FTS5 special characters with spaces.
#[pyfunction]
fn sanitize_fts_query(query: &str) -> String {
    query
        .chars()
        .map(|c| {
            if matches!(
                c,
                '+' | '-'
                    | '*'
                    | '<'
                    | '>'
                    | '"'
                    | ':'
                    | '('
                    | ')'
                    | '^'
                    | '~'
                    | '{'
                    | '}'
                    | '['
                    | ']'
                    | '\\'
                    | '!'
                    | '?'
                    | '.'
                    | '\''
                    | ','
            ) {
                ' '
            } else {
                c
            }
        })
        .collect()
}

// ─── Thinking Tag Filter ─────────────────────────────────────────────────────

/// Compiled regex patterns for thinking tags (13 patterns, compiled once).
static THINKING_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    let patterns = [
        r"(?s)<\|channel\|>thought\n.*?\n<\|channel\|>",
        r"(?s)<think>.*?</think>",
        r"(?s) reasoning\n.*?\n/end_reasoning",
        r"(?s)<reasoning>.*?</reasoning>",
        r"(?s)<<<thinking>>>.*?<<<</thinking>>>",
        r"(?s)/think\s*\n.*?\n/end",
        r"(?s)\[Thinking\].*?\[/Thinking\]",
        r"(?s)<!-- thinking -->.*?<!-- /thinking -->",
        r"(?s)<tool_call>.*?</tool_call>",
        r"(?s)<\|reserved_special_token_\d+\|>.*?<\|reserved_special_token_\d+\|>",
        r"(?s)\[think\].*?\[/think\]",
        r"(?s)BEGIN_THINKING\n.*?\nEND_THINKING",
        r"(?s)<｜begin▁of▁thinking｜>.*?<｜end▁of▁thinking｜>",
    ];
    patterns
        .iter()
        .filter_map(|p| Regex::new(p).ok())
        .collect()
});

/// Filter thinking tags from LLM output using compiled regex patterns.
#[pyfunction]
fn filter_thinking(text: &str) -> String {
    let mut result = text.to_string();
    for pattern in THINKING_PATTERNS.iter() {
        result = pattern.replace_all(&result, "").to_string();
    }
    result.trim().to_string()
}

// ─── Contraction Replacer ────────────────────────────────────────────────────

static CONTRACTION_MAP: LazyLock<HashMap<&'static str, &'static str>> = LazyLock::new(|| {
    HashMap::from([
        ("I am", "I'm"),
        ("I will", "I'll"),
        ("I would", "I'd"),
        ("I have", "I've"),
        ("I had", "I'd"),
        ("you are", "you're"),
        ("you will", "you'll"),
        ("you would", "you'd"),
        ("you have", "you've"),
        ("he is", "he's"),
        ("he will", "he'll"),
        ("she is", "she's"),
        ("she will", "she'll"),
        ("it is", "it's"),
        ("it will", "it'll"),
        ("we are", "we're"),
        ("we will", "we'll"),
        ("we have", "we've"),
        ("they are", "they're"),
        ("they will", "they'll"),
        ("they have", "they've"),
        ("that is", "that's"),
        ("that will", "that'll"),
        ("there is", "there's"),
        ("here is", "here's"),
        ("what is", "what's"),
        ("who is", "who's"),
        ("cannot", "can't"),
        ("can not", "can't"),
        ("do not", "don't"),
        ("does not", "doesn't"),
        ("did not", "didn't"),
        ("is not", "isn't"),
        ("are not", "aren't"),
        ("was not", "wasn't"),
        ("were not", "weren't"),
        ("have not", "haven't"),
        ("has not", "hasn't"),
        ("had not", "hadn't"),
        ("will not", "won't"),
        ("would not", "wouldn't"),
        ("could not", "couldn't"),
        ("should not", "shouldn't"),
        ("must not", "mustn't"),
        ("let us", "let's"),
        ("going to", "gonna"),
        ("want to", "wanna"),
        ("got to", "gotta"),
        ("kind of", "kinda"),
        ("sort of", "sorta"),
    ])
});

/// Build a combined regex pattern from contraction keys (compiled once).
static CONTRACTION_REGEX: LazyLock<Regex> = LazyLock::new(|| {
    let keys: Vec<String> = CONTRACTION_MAP
        .keys()
        .map(|k| regex::escape(k))
        .collect();
    // Sort by length descending so longer phrases match first
    let mut sorted = keys;
    sorted.sort_by(|a, b| b.len().cmp(&a.len()));
    let pattern = format!(r"(?i)\b({})\b", sorted.join("|"));
    Regex::new(&pattern).expect("invalid contraction regex")
});

/// Apply natural language contractions in a single regex pass.
#[pyfunction]
fn apply_contractions(text: &str) -> String {
    CONTRACTION_REGEX
        .replace_all(text, |caps: &regex::Captures| {
            let matched = caps.get(0).unwrap().as_str();
            // Find the case-insensitive match in the map
            for (key, val) in CONTRACTION_MAP.iter() {
                if matched.to_lowercase() == key.to_lowercase() {
                    // Preserve original case pattern
                    if matched.starts_with(|c: char| c.is_uppercase()) {
                        // Capitalize first letter of replacement
                        let mut chars = val.chars();
                        if let Some(first) = chars.next() {
                            let capitalized: String =
                                first.to_uppercase().collect::<String>() + chars.as_str();
                            return capitalized;
                        }
                    }
                    return val.to_string();
                }
            }
            matched.to_string()
        })
        .to_string()
}

// ─── FTS Merge + Rerank ─────────────────────────────────────────────────────

/// Score and recency-rank search candidates in pure Rust.
///
/// Takes vectors of (score, age_days) pairs and returns indices sorted by
/// combined relevance score (0.7 * normalized_score + 0.3 * recency_decay).
#[pyfunction]
fn rerank_candidates(
    scores: Vec<f64>,
    age_days: Vec<f64>,
) -> PyResult<Vec<(usize, f64)>> {
    if scores.len() != age_days.len() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "scores and age_days must have the same length",
        ));
    }
    if scores.is_empty() {
        return Ok(vec![]);
    }

    let max_score = scores.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let min_score = scores.iter().cloned().fold(f64::INFINITY, f64::min);
    let score_range = (max_score - min_score).max(1e-10);

    let mut indexed: Vec<(usize, f64)> = scores
        .iter()
        .enumerate()
        .map(|(i, &score)| {
            let normalized = (score - min_score) / score_range;
            // Recency decay: exponential, half-life of 30 days
            let recency = (-age_days[i] / 30.0_f64.ln() / 30.0).exp();
            let combined = 0.7 * normalized + 0.3 * recency;
            (i, combined)
        })
        .collect();

    indexed.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    Ok(indexed)
}

// ─── Module Registration ─────────────────────────────────────────────────────

/// The serin_core Python module.
#[pymodule]
fn serin_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(sanitize_fts_query, m)?)?;
    m.add_function(wrap_pyfunction!(filter_thinking, m)?)?;
    m.add_function(wrap_pyfunction!(apply_contractions, m)?)?;
    m.add_function(wrap_pyfunction!(rerank_candidates, m)?)?;
    m.add_function(wrap_pyfunction!(validate_json_fast, m)?)?;
    m.add_function(wrap_pyfunction!(compute_text_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(extract_mentions, m)?)?;
    m.add_function(wrap_pyfunction!(tokenize_words, m)?)?;
    m.add_function(wrap_pyfunction!(sanitize_markdown, m)?)?;
    Ok(())
}

// ─── JSON Validation ────────────────────────────────────────────────────────

/// Fast JSON validation — checks if a string is valid JSON.
/// Returns Ok(true) if valid, Ok(false) if invalid.
#[pyfunction]
fn validate_json_fast(text: &str) -> bool {
    serde_json::from_str::<serde_json::Value>(text).is_ok()
}

// ─── Text Similarity ────────────────────────────────────────────────────────

/// Compute Levenshtein edit distance between two strings.
/// Normalized to 0.0-1.0 range (1.0 = identical).
#[pyfunction]
fn compute_text_similarity(a: &str, b: &str) -> f64 {
    if a == b {
        return 1.0;
    }
    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();
    let a_len = a_chars.len();
    let b_len = b_chars.len();

    if a_len == 0 && b_len == 0 {
        return 1.0;
    }

    // DP matrix for Levenshtein distance
    let mut prev = vec![0usize; b_len + 1];
    let mut curr = vec![0usize; b_len + 1];

    for j in 0..=b_len {
        prev[j] = j;
    }

    for i in 1..=a_len {
        curr[0] = i;
        for j in 1..=b_len {
            let cost = if a_chars[i - 1] == b_chars[j - 1] { 0 } else { 1 };
            curr[j] = std::cmp::min(
                std::cmp::min(
                    prev[j] + 1,      // deletion
                    curr[j - 1] + 1,  // insertion
                ),
                prev[j - 1] + cost,   // substitution
            );
        }
        std::mem::swap(&mut prev, &mut curr);
    }

    let distance = prev[b_len];
    let max_len = std::cmp::max(a_len, b_len);
    1.0 - (distance as f64 / max_len as f64)
}

// ─── Discord Mention Extraction ──────────────────────────────────────────────

/// Extract Discord user/role/channel mention IDs from text.
/// Returns a list of mention strings (e.g., ["<@123456>", "<@&789012>"]).
#[pyfunction]
fn extract_mentions(text: &str) -> Vec<String> {
    let mut mentions = Vec::new();
    let mut chars = text.char_indices().peekable();

    while let Some((i, c)) = chars.next() {
        if c == '<' {
            // Check for <@...> or <@&...> or <#...>
            if let Some(&(_, next_c)) = chars.peek() {
                if next_c == '@' || next_c == '#' {
                    let start = i;
                    // Find the closing >
                    while let Some((j, jc)) = chars.next() {
                        if jc == '>' {
                            let mention = &text[start..=j];
                            // Validate format
                            if mention.starts_with("<@") || mention.starts_with("<#") {
                                mentions.push(mention.to_string());
                            }
                            break;
                        }
                    }
                }
            }
        }
    }
    mentions
}

// ─── Word Tokenizer ─────────────────────────────────────────────────────────

/// Fast word tokenization — splits text into words, filtering out empty strings.
/// Returns count of words and the words themselves.
#[pyfunction]
fn tokenize_words(text: &str) -> Vec<String> {
    text.split_whitespace()
        .filter(|w| !w.is_empty())
        .map(|w| w.to_string())
        .collect()
}

// ─── Discord Markdown Sanitizer ──────────────────────────────────────────────

/// Strip Discord markdown formatting from text.
/// Handles: **bold**, *italic*, __underline__, ~~strikethrough~~, `code`, ```code blocks```
static MARKDOWN_PATTERNS: LazyLock<Vec<Regex>> = LazyLock::new(|| {
    let patterns = [
        r"(?s)```.*?```",           // code blocks
        r"(?s)`[^`]*`",            // inline code
        r"\*\*(.+?)\*\*",         // bold
        r"\*(.+?)\*",             // italic
        r"__(.+?)__",             // underline
        r"~~(.+?)~~",             // strikethrough
        r"\|\|(.+?)\|\|",        // spoiler
    ];
    patterns
        .iter()
        .filter_map(|p| Regex::new(p).ok())
        .collect()
});

/// Sanitize Discord markdown from text, returning plain text.
#[pyfunction]
fn sanitize_markdown(text: &str) -> String {
    let mut result = text.to_string();
    for pattern in MARKDOWN_PATTERNS.iter() {
        // For capture groups, extract the inner text; for non-capturing, remove entirely
        if let Some(caps) = pattern.captures(&result) {
            if caps.len() > 1 {
                // Has capture group — replace with inner text
                if let Some(inner) = caps.get(1) {
                    let full = caps.get(0).unwrap().as_str();
                    result = result.replace(full, inner.as_str());
                }
            } else {
                // No capture group — remove the match
                result = pattern.replace_all(&result, "").to_string();
            }
        }
    }
    // Clean up Discord-specific mentions
    result = result.replace("\\*", "*");  // unescape
    result = result.replace("\\_", "_");
    result.trim().to_string()
}
