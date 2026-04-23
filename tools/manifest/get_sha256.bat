@echo off
cd F:\.github\agents
certutil -hashfile "⊕workspace-hygiene.agent.md" SHA256 > F:\hash1.txt 2>&1
cd F:\.github\instructions
certutil -hashfile "agent-self-regen.instructions.md" SHA256 >> F:\hash1.txt 2>&1
type F:\hash1.txt
