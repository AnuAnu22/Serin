//! undef-var-scanner — Strict undefined variable detection in Python files.
//!
//! For every {identifier} inside a non-f-string constant, checks if the
//! identifier is defined as a local variable, parameter, or import in the
//! enclosing scope. Skips docstrings (triple-quoted strings right after
//! def/class) and SQL keywords.
//!
//! Usage: undef-var-scanner <directory> [--exclude <pattern>]

use std::collections::HashSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process;

const SQL_KEYWORDS: &[&str] = &[
    "TABLE", "SELECT", "INSERT", "UPDATE", "DELETE", "WHERE", "FROM",
    "JOIN", "ON", "SET", "VALUES", "AND", "OR", "NOT", "NULL",
    "CREATE", "DROP", "INDEX", "IF", "EXISTS", "UNINDEXED", "MATCH",
    "ORDER", "BY", "LIMIT", "AS", "INTO", "PRIMARY", "KEY", "DEFAULT",
    "INTEGER", "TEXT", "REAL", "BLOB", "AUTOINCREMENT", "UNIQUE",
    "CHECK", "CONSTRAINT", "REFERENCES", "CASCADE", "RESTRICT",
    "BEGIN", "COMMIT", "ROLLBACK", "PRAGMA", "WAL",
];

fn is_sql_keyword(name: &str) -> bool {
    let upper = name.to_uppercase();
    SQL_KEYWORDS.iter().any(|&kw| kw == upper)
}

/// Check if a name is defined in the file as a local/param/import/assignment.
fn is_name_defined(name: &str, content: &str) -> bool {
    let pats = [
        format!("def {}(", name),
        format!("class {}(", name),
        format!("class {}:", name),
        format!("import {}", name),
        format!("from {} import", name),
        format!("{} = ", name),
        format!("{}: ", name),
        format!("({}", name),
        format!(", {}", name),
        format!("'{}'", name),
        format!("\"{}\"", name),
        format!("['{}']", name),
        format!("[\"{}\"]", name),
        format!(".get('{}')", name),
        format!(".get(\"{}\")", name),
    ];
    pats.iter().any(|p| content.contains(p.as_str()))
}

struct Issue {
    file: PathBuf,
    line: usize,
    var_name: String,
    context: String,
}

/// Check if position is inside a docstring (triple-quoted string right after def/class).
fn is_docstring(content: &str, pos: usize) -> bool {
    // Look backwards from pos for def/class
    let before = &content[..pos];
    let lines: Vec<&str> = before.lines().collect();
    // Check last few non-empty lines
    for line in lines.iter().rev().take(3) {
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }
        if trimmed.starts_with("def ") || trimmed.starts_with("async def ") || trimmed.starts_with("class ") {
            return true;
        }
        // If we hit a non-empty, non-def line, stop
        break;
    }
    false
}

fn extract_string_and_check(content: &str, file_path: &Path) -> Vec<Issue> {
    let mut issues = Vec::new();
    let bytes = content.as_bytes();
    let len = bytes.len();
    let mut i = 0;
    let lines: Vec<&str> = content.lines().collect();

    while i < len {
        // Skip comments
        if bytes[i] == b'#' {
            while i < len && bytes[i] != b'\n' { i += 1; }
            continue;
        }

        // Skip f-strings
        if (bytes[i] == b'f' || bytes[i] == b'F') && i + 1 < len {
            let q = bytes[i + 1];
            if q == b'"' || q == b'\'' {
                i += 2;
                if i + 2 < len && bytes[i] == q && bytes[i + 1] == q {
                    i += 2;
                    while i + 2 < len {
                        if bytes[i] == q && bytes[i + 1] == q && bytes[i + 2] == q { i += 3; break; }
                        i += 1;
                    }
                } else {
                    while i < len && bytes[i] != q {
                        if bytes[i] == b'\\' { i += 1; }
                        i += 1;
                    }
                    i += 1;
                }
                continue;
            }
        }

        // Triple-quoted strings
        if i + 2 < len && bytes[i] == bytes[i + 1] && bytes[i] == bytes[i + 2]
            && (bytes[i] == b'"' || bytes[i] == b'\'')
        {
            let quote = bytes[i];
            let start_byte = i;
            let start_line = content[..i].lines().count();
            i += 3;
            let mut s = String::new();
            while i + 2 < len {
                if bytes[i] == quote && bytes[i + 1] == quote && bytes[i + 2] == quote {
                    i += 3;
                    // Skip docstrings
                    if !is_docstring(content, start_byte) {
                        check_string(&s, start_line, file_path, content, &mut issues);
                    }
                    break;
                }
                s.push(bytes[i] as char);
                i += 1;
            }
            continue;
        }

        // Single/double quoted strings
        if bytes[i] == b'"' || bytes[i] == b'\'' {
            let quote = bytes[i];
            let start_line = content[..i].lines().count();
            i += 1;
            let mut s = String::new();
            while i < len && bytes[i] != quote {
                if bytes[i] == b'\\' && i + 1 < len { i += 1; }
                s.push(bytes[i] as char);
                i += 1;
            }
            i += 1;
            check_string(&s, start_line, file_path, content, &mut issues);
            continue;
        }

        i += 1;
    }
    issues
}

fn check_string(s: &str, start_line: usize, file_path: &Path, content: &str, issues: &mut Vec<Issue>) {
    let bytes = s.as_bytes();
    let len = bytes.len();
    let mut i = 0;
    let lines: Vec<&str> = content.lines().collect();

    while i < len {
        if bytes[i] == b'{' {
            i += 1;
            let mut ident = String::new();
            while i < len && (bytes[i].is_ascii_alphanumeric() || bytes[i] == b'_') {
                ident.push(bytes[i] as char);
                i += 1;
            }
            if !ident.is_empty() && ident.chars().next().unwrap().is_ascii_alphabetic() {
                if !is_sql_keyword(&ident) && !is_name_defined(&ident, content) {
                    let line_idx = start_line.saturating_sub(1);
                    let context = if line_idx < lines.len() {
                        lines[line_idx].trim().to_string()
                    } else {
                        String::new()
                    };
                    issues.push(Issue {
                        file: file_path.to_path_buf(),
                        line: start_line,
                        var_name: ident,
                        context,
                    });
                }
            }
        } else {
            i += 1;
        }
    }
}

fn walk_py_files(dir: &Path, exclude: &HashSet<String>) -> Vec<PathBuf> {
    let mut files = Vec::new();
    if dir.is_dir() {
        for entry in fs::read_dir(dir).unwrap() {
            let entry = entry.unwrap();
            let path = entry.path();
            if path.is_dir() {
                let name = path.file_name().unwrap().to_string_lossy();
                if exclude.contains(name.as_ref()) { continue; }
                files.extend(walk_py_files(&path, exclude));
            } else if path.extension().map_or(false, |e| e == "py") {
                let name = path.file_name().unwrap().to_string_lossy();
                if name == "__init__.py" || name == "__main__.py" { continue; }
                files.push(path);
            }
        }
    }
    files
}

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: {} <directory> [--exclude <dir>]", args[0]);
        process::exit(1);
    }

    let target = Path::new(&args[1]);
    let mut exclude = HashSet::new();
    exclude.insert("__pycache__".to_string());
    exclude.insert(".venv".to_string());
    exclude.insert("target".to_string());
    exclude.insert(".git".to_string());
    exclude.insert("node_modules".to_string());

    let mut i = 2;
    while i < args.len() {
        if args[i] == "--exclude" && i + 1 < args.len() {
            exclude.insert(args[i + 1].clone());
            i += 2;
        } else { i += 1; }
    }

    let files = walk_py_files(target, &exclude);
    let mut all_issues: Vec<Issue> = Vec::new();

    for file in &files {
        let content = match fs::read_to_string(file) {
            Ok(c) => c,
            Err(_) => continue,
        };
        all_issues.extend(extract_string_and_check(&content, file));
    }

    if all_issues.is_empty() {
        println!("OK — no undefined variables found in {} files.", files.len());
        process::exit(0);
    }

    eprintln!("Found {} undefined variable(s) in {} files:\n", all_issues.len(), files.len());
    for issue in &all_issues {
        let rel = issue.file.strip_prefix(target).unwrap_or(&issue.file);
        eprintln!("  {}:{} — {{{}}} not defined", rel.display(), issue.line, issue.var_name);
        if !issue.context.is_empty() {
            eprintln!("    {}", issue.context);
        }
    }
    process::exit(1);
}
