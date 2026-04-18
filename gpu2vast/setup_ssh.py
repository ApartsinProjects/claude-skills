"""
GPU2Vast SSH Setup
==================
Generates an SSH keypair, registers it with vast.ai, and configures ~/.ssh/config.

Usage:
  python setup_ssh.py

After running, you can SSH to any vast.ai instance with:
  ssh -p <port> root@<host>
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import vastai_manager as vast

KEYS_DIR = Path(__file__).parent / "keys"
SSH_DIR = KEYS_DIR / "ssh"
HOME_SSH = Path.home() / ".ssh"

print("=" * 50)
print("  GPU2Vast SSH Setup")
print("=" * 50)

# 1. Generate keypair
print("\n[1/4] Generating SSH keypair...")
pub_key = vast.ensure_ssh_key()
private_key = SSH_DIR / "gpu2vast_ed25519"
print(f"  Private key: {private_key}")
print(f"  Public key:  {pub_key[:50]}...")

# 2. Copy to ~/.ssh
print("\n[2/4] Copying keys to ~/.ssh/...")
HOME_SSH.mkdir(exist_ok=True)
dest_private = HOME_SSH / "gpu2vast_ed25519"
dest_public = HOME_SSH / "gpu2vast_ed25519.pub"
shutil.copy2(private_key, dest_private)
shutil.copy2(SSH_DIR / "gpu2vast_ed25519.pub", dest_public)
dest_private.chmod(0o600)
print(f"  Copied to {dest_private}")

# 3. Add to ~/.ssh/config
print("\n[3/4] Configuring ~/.ssh/config...")
ssh_config = HOME_SSH / "config"
vast_block = """
Host *.vast.ai
    User root
    IdentityFile "{key_path}"
    IdentitiesOnly yes
    StrictHostKeyChecking no
""".format(key_path=str(dest_private).replace("\\", "/"))

if ssh_config.exists():
    existing = ssh_config.read_text()
    if "vast.ai" in existing:
        print("  vast.ai config already present, skipping")
    else:
        ssh_config.write_text(existing.rstrip() + "\n" + vast_block)
        print("  Added vast.ai entry to config")
else:
    ssh_config.write_text(vast_block.strip() + "\n")
    print("  Created config with vast.ai entry")

# 4. Verify registration
print("\n[4/4] Verifying vast.ai registration...")
keys = vast.list_ssh_keys()
registered = any(pub_key[:30] in str(k) for k in keys)
print(f"  Registered keys: {len(keys)}")
print(f"  Our key registered: {registered}")

print(f"\n{'='*50}")
print("  SSH Setup Complete")
print("  To connect to an instance:")
print("    ssh -p <port> root@<host>.vast.ai")
print(f"{'='*50}")
