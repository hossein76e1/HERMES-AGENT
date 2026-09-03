#!/bin/bash
cd /data/hermes-backup-repo
# Set up credential helper to supply the token
git config credential.helper '!f() { echo "username=hossein76e1"; echo "password=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"; }; f'
GIT_TERMINAL_PROMPT=0 git push -u origin main 2>&1
echo "EXIT_CODE: $?"
