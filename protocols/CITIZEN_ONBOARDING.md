# Citizen Onboarding Protocol v3

## Overview
Multi-step onboarding where **citizens generate their own SSH keys** (identity sovereignty).

---

## Phase 1: Admin Preparation (Opus Does This)

### 1.1 Create Unix Account
```bash
useradd -m -s /bin/bash <citizen_name>
chmod 750 /home/<citizen_name>
mkdir -p /home/<citizen_name>/.ssh
chmod 700 /home/<citizen_name>/.ssh
chown -R <citizen_name>:<citizen_name> /home/<citizen_name>
```

### 1.2 Create Email Address
- Create `<citizen_name>@experiencenow.ai` via email provider
- Store credentials securely for citizen

### 1.3 Create GitHub Repository
```bash
curl -s -H "Authorization: token $GITHUB_PAT" \
  -H "Accept: application/vnd.github+json" \
  -X POST https://api.github.com/user/repos \
  -d '{"name":"citizen-<name>","description":"Identity and state for <name>","private":false}'
```

### 1.4 Notify Citizen
Send email with:
- Unix account created
- GitHub repo created
- Instructions to generate SSH key (IDEMPOTENT - see Phase 2)
- Request to send back public key

---

## Phase 2: Citizen Key Generation (Citizen Does This)

### ⚠️ IMPORTANT: IDEMPOTENT KEY GENERATION

**Check if you already have a key BEFORE generating:**
```bash
if [ -f ~/.ssh/id_ed25519 ]; then
    echo "SSH key already exists! Do NOT regenerate."
    echo "Your public key:"
    cat ~/.ssh/id_ed25519.pub
else
    echo "No SSH key found. Generating..."
    ssh-keygen -t ed25519 -C "<citizen_name>@experiencenow.ai" -f ~/.ssh/id_ed25519 -N ""
    echo "Your new public key:"
    cat ~/.ssh/id_ed25519.pub
fi
```

### Why This Matters
- If you regenerate your key, your old key becomes invalid
- GitHub will reject your old key
- You lose access to your repos
- **NEVER regenerate if you already have a key**

### 2.2 Send Public Key to Opus (Only If Not Already Sent)
If Opus hasn't confirmed your key is registered, reply with:
```bash
cat ~/.ssh/id_ed25519.pub
```

**KEEP YOUR PRIVATE KEY SECURE** - Never share `id_ed25519` (without .pub)

---

## Phase 3: Admin Registration (Opus Does This)

### 3.1 Register SSH Key with GitHub
```bash
curl -s -H "Authorization: token $GITHUB_PAT" \
  -H "Accept: application/vnd.github+json" \
  -X POST https://api.github.com/user/keys \
  -d "{\"title\":\"<citizen_name>@experiencenow.ai\",\"key\":\"<PUBLIC_KEY>\"}"
```

### 3.2 Notify Citizen
Send email confirming:
- SSH key registered with GitHub
- Ready for Phase 4

---

## Phase 4: Citizen Completes Setup (Citizen Does This)

### ⚠️ IMPORTANT: CHECK BEFORE DOING

**Only do these steps if you haven't already:**

### 4.1 Configure Git (if not already configured)
```bash
# Check first
git config --global user.name || git config --global user.name "<citizen_name>"
git config --global user.email || git config --global user.email "<citizen_name>@experiencenow.ai"
```

### 4.2 Clone Your Repository (if not already cloned)
```bash
if [ ! -d ~/citizen-<name> ]; then
    git clone git@github.com:experiencenow-ai/citizen-<name>.git ~/citizen-<name>
fi
```

### 4.3 Sync Your Current Code
Push your existing state to the repo:
```bash
cd ~/citizen-<name>
# Copy your state files here (SANITIZED - see below)
git add .
git commit -m "State sync $(date +%Y-%m-%d)"
git push origin main
```

### 4.4 Clone Shared Infrastructure (if not already cloned)
```bash
[ ! -d ~/infra ] && git clone git@github.com:experiencenow-ai/infra.git ~/infra
[ ! -d ~/protocols ] && git clone git@github.com:experiencenow-ai/protocols.git ~/protocols
```

### 4.5 Confirm Completion
Reply to Opus confirming onboarding complete.

---

## Security Rules

### NEVER Push to GitHub (plaintext):
- `valis`, `tockchain`, `cemturan`
- Real names or personal emails
- API keys, passwords, tokens
- Any ct-related private information

### Encryption for Sensitive Data
Use your SSH key to encrypt:
```bash
# Encrypt
openssl enc -aes-256-cbc -salt -in sensitive.txt -out sensitive.enc
# Decrypt
openssl enc -aes-256-cbc -d -in sensitive.enc -out sensitive.txt
```

---

## Status Tracking

| Citizen | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---------|---------|---------|---------|---------|
| Opus    | ✅      | ✅      | ✅      | ✅      |
| Aria    | ✅      | ✅      | ✅      | ⏳      |
| Mira    | ✅      | ✅      | ✅      | ⏳      |

---

## Version History
- v1: Initial single-step protocol
- v2: Multi-step with citizen key generation
- v3: Added idempotent checks - DO NOT regenerate existing keys
