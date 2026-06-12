0.0.7 UI Changes\Remove logs from released apps/Add failed-tool recovery: if a command fails, ask the model to correct it instead of finalizing too early.
Put api key in hash 
0.0.8 Add delete conversation.
Add rename conversation.
Add search conversations.
Add “clear current conversation memory.”

0.0.9 Add automatic history summarization for long chats.Add command validator step: model proposes command, Scout validates, then user approves.Add tool-output prompt-injection protection.
0.1.0 Add dedicated Linux tools instead of relying only on shell:
package manager detector
app install/remove tool
disk usage tool
service status/restart tool
desktop environment detector
KDE wallpaper/tooling helper
Add safer tool-specific UI approvals.
Sign release manifests or archives.
Verify signature inside Scout.
Improve updater UI: current version, latest version, changelog, download progress.
Add rollback if update apply fails.
0.1.1 
Block dangerous shell patterns: curl | sh, wget | bash, dd, mkfs, find -delete, broad chmod/chown, destructive home operations.
Add redaction before logging: API keys, SSH keys, tokens, passwords.
0.1.2
Backend selector: OpenRouter / Ollama.
Model selector.
