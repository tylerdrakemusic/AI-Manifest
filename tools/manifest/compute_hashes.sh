#!/bin/bash
cd /f/.github
sha256sum agents/⊕workspace-hygiene.agent.md > /f/hash1.txt
sha256sum instructions/agent-self-regen.instructions.md >> /f/hash1.txt
cat /f/hash1.txt
