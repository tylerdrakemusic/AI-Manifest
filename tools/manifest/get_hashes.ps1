$file1 = "F:\.github\agents\⊕workspace-hygiene.agent.md"
$file2 = "F:\.github\instructions\agent-self-regen.instructions.md"

$hash1 = (Get-FileHash $file1 -Algorithm SHA256).Hash
$hash2 = (Get-FileHash $file2 -Algorithm SHA256).Hash

Write-Output "$file1|$hash1"
Write-Output "$file2|$hash2"
