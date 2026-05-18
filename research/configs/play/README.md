# Play Configs

Local `aerd play` configs are ignored by git by default. They select repo-controlled playbook/component IDs and parameters only; they must not contain inline Python, arbitrary notebook paths, scripts, imports, credentials, play artifact refs, or leaderboard-row refs.
