# hyper2kvm: Quick Mode Comparison

## One-Page Overview

```mermaid
graph LR
    subgraph CLI["🖥️ CLI Mode"]
        direction TB
        C1["User runs command"] --> C2["Process VM"]
        C2 --> C3["Exit"]

        style C1 fill:#E3F2FD
        style C2 fill:#90CAF9
        style C3 fill:#42A5F5
    end

    subgraph DAEMON["🔄 Daemon Mode"]
        direction TB
        D1["Watch /queue"] --> D2["Auto-detect"]
        D2 --> D3["Process"]
        D3 --> D4["Archive"]
        D4 --> D1

        style D1 fill:#E8F5E9
        style D2 fill:#81C784
        style D3 fill:#66BB6A
        style D4 fill:#4CAF50
    end

    style CLI fill:#2196F3,stroke:#1565C0,color:#fff,stroke-width:3px
    style DAEMON fill:#4CAF50,stroke:#2E7D32,color:#fff,stroke-width:3px
```

---

## Side-by-Side Comparison

| Aspect | CLI Mode | Daemon Mode |
|--------|----------|-------------|
| **Trigger** | Manual command | File drop |
| **Process** | One VM | Continuous |
| **Feedback** | Interactive | Logs |
| **Use Case** | Dev/Testing | Production |
| **Deployment** | Ad-hoc | systemd service |

---

## Quick Commands

### CLI Mode
```bash
# Single VM conversion
hyper2kvm local --source vm.vmdk --output vm.qcow2
```

### Daemon Mode
```bash
# Start daemon
sudo systemctl start hyper2kvm.service

# Drop files → auto-processed
cp *.vmdk /var/lib/hyper2kvm/queue/
```

---

## When to Use

### Use CLI Mode 👨‍💻
- Testing a single VM
- Development work
- Need immediate feedback
- Manual control required

### Use Daemon Mode ⚙️
- Production environment
- Batch processing
- Automated workflows
- Overnight operations
- CI/CD integration
