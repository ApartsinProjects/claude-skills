"""Generate SSH key pair for RunPod access. Run once before first job."""
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent
SSH_DIR = SKILL_DIR / "keys" / "ssh"
KEY_PATH = SSH_DIR / "gpu2runpod_ed25519"


def setup():
    SSH_DIR.mkdir(parents=True, exist_ok=True)

    if KEY_PATH.exists():
        print(f"SSH key already exists: {KEY_PATH}")
        pub = KEY_PATH.with_suffix("").with_name(KEY_PATH.name + ".pub")
        if pub.exists():
            print(f"Public key: {pub.read_text().strip()}")
        return

    print("Generating ED25519 SSH key pair...")
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(KEY_PATH), "-N", "", "-C", "gpu2runpod"],
        check=True,
    )
    KEY_PATH.chmod(0o600)
    print(f"Private key: {KEY_PATH}")
    pub = Path(str(KEY_PATH) + ".pub")
    print(f"Public key:  {pub}")
    print()
    print("The public key is automatically injected into RunPod pods via the PUBLIC_KEY")
    print("environment variable when creating pods with gpu2runpod.")
    print()
    print("Optionally, add it to your RunPod account at:")
    print("  https://www.runpod.io/console/user/settings  (SSH Public Keys section)")
    print()
    print(f"Public key contents:\n{pub.read_text().strip()}")


if __name__ == "__main__":
    setup()
