# Security

Ascend Media RPC stores provider credentials and device settings locally in
`config.json`. That file is intentionally ignored by Git and must never be
committed.

To set up a new checkout:

1. Copy `config.example.json` to `config.json`.
2. Add credentials locally through the dashboard or the local config file.
3. Keep the dashboard bound to localhost unless you intentionally configure
   authentication and a trusted network.
4. Do not expose Android TV ADB or the dashboard to the public internet.

If a credential has ever been committed, pasted into a public issue, or shared
in logs, revoke or rotate it immediately. Remove the credential from the
repository history before publishing a sanitized replacement.